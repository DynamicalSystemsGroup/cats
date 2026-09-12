"""P2 out-of-loop projectors — ABI read, CAS GET, byte-stable re-run."""
from __future__ import annotations

import copy
import json
from unittest.mock import MagicMock

import pytest
from flask import Flask

from cats.network.bom import (
    fru_purl,
    project_bom,
    project_data_lot,
    project_function_source,
    project_structure_runtime,
    project_structure_source,
)
from cats.network.bom.documents import FIXED_CREATED
from cats.network.bom.project import MEDIA_CDX, MEDIA_DCAT, MEDIA_SPDX, parse_uv_lock
from cats.network.bom.read import invoice_uri_from_response, require_ni
from cats.network.cas import (
    LocatorIndex,
    build_manifest_entries,
    from_ni,
    is_ni_or_digest,
    register_cas_routes,
    set_ref,
    sha256_hex,
    to_ni,
)
from cats.network.content_mesh import ContentMesh


FORBIDDEN_BOM_ID = 'FORBIDDEN_BOM_CONTENT_ID'
_IMAGE_HEX = sha256_hex(b'p2-oci-image')
_IMAGE_REF = f'kindest/node@sha256:{_IMAGE_HEX}'
_UV_LOCK = b'''version = 1

[[package]]
name = "numpy"
version = "2.1.0"
'''


def _mesh(tmp_path, monkeypatch) -> ContentMesh:
    client = ContentMesh(ipfsClient=MagicMock(), CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    return client


def _put_sorted(mesh: ContentMesh, obj: dict) -> str:
    return mesh.put_bytes(
        (json.dumps(obj, sort_keys=True) + '\n').encode('utf-8')
    )


def _fixture_graph(mesh: ContentMesh) -> dict:
    src_file = mesh.put_bytes(b'def process_0():\n    return 0\n')
    lock_id = mesh.put_bytes(_UV_LOCK)
    proc_src = _put_sorted(
        mesh,
        build_manifest_entries(
            {'callables.py': src_file, 'uv.lock': lock_id}
        ),
    )
    infra_src = _put_sorted(
        mesh, build_manifest_entries({'actuator.py': src_file})
    )
    function = {}
    set_ref(function, 'process_source', proc_src)
    set_ref(function, 'infrafunction_source', infra_src)
    set_ref(function, 'process', mesh.put_bytes(b'{"ingress_subproc_uri":"x"}\n'))
    set_ref(function, 'infrafunction', mesh.put_bytes(b'{}\n'))
    function_id = _put_sorted(mesh, function)

    plant_tf = mesh.put_bytes(b'variable "node_image" {}\n')
    plant_src = _put_sorted(mesh, build_manifest_entries({'main.tf': plant_tf}))
    infra_tree = _put_sorted(
        mesh, build_manifest_entries({'outputs.tf': plant_tf})
    )
    root_tree = _put_sorted(mesh, build_manifest_entries({'main.tf': plant_tf}))
    structure = {}
    set_ref(structure, 'root', root_tree)
    set_ref(structure, 'plant', plant_src)
    set_ref(structure, 'infrastructure', infra_tree)
    structure_id = _put_sorted(mesh, structure)

    plant_sae = _put_sorted(mesh, {'rebuilt': False, 'kind_cluster_name': 'c'})
    infra_sae = _put_sorted(mesh, {'object_store_as_executed_uri': 'http://x'})
    sae = {}
    set_ref(sae, 'plant_as_executed', plant_sae)
    set_ref(sae, 'infrastructure_as_executed', infra_sae)
    sae_id = _put_sorted(mesh, sae)

    egress = mesh.put_bytes(b'{"lot":"egress"}\n')
    integ = mesh.put_bytes(b'{"lot":"integ"}\n')
    ingres = mesh.put_bytes(b'{"lot":"in"}\n')
    stages = {}
    set_ref(stages, 'egressed_data', egress)
    set_ref(stages, 'integrated_data', integ)
    set_ref(stages, 'ingressed_data', ingres)
    stages_id = _put_sorted(mesh, stages)
    seed_id = _put_sorted(mesh, {'seed': 'abc', 'rng_seed': 1, 'num_partitions': 1})
    input_lot = mesh.put_bytes(b'{"lot":"input"}\n')
    input_invoice = {}
    set_ref(input_invoice, 'data', input_lot)
    input_invoice_id = _put_sorted(mesh, input_invoice)

    order = {}
    set_ref(order, 'function', function_id)
    set_ref(order, 'structure', structure_id)
    set_ref(order, 'invoice', input_invoice_id)
    order_id = _put_sorted(mesh, order)

    invoice = {}
    set_ref(invoice, 'order', order_id)
    set_ref(invoice, 'data', egress)
    set_ref(invoice, 'data_stages', stages_id)
    set_ref(invoice, 'seed', seed_id)
    set_ref(invoice, 'structure_as_executed', sae_id)
    invoice_id = _put_sorted(mesh, invoice)

    log_id = _put_sorted(mesh, {'plant_rebuilt': False})
    bom = {}
    set_ref(bom, 'invoice', invoice_id)
    set_ref(bom, 'log', log_id)
    envelope = {
        'content_id': FORBIDDEN_BOM_ID,
        'invoice_uri': 'http://n/inv-resp-ignored',
        'bom': bom,
    }
    return {
        'envelope': envelope,
        'invoice_id': invoice_id,
        'function_id': function_id,
        'structure_id': structure_id,
        'sae_id': sae_id,
        'order_id': order_id,
        'input_lot_id': input_lot,
        'function': json.loads(mesh.cat(function_id)),
        'structure': json.loads(mesh.cat(structure_id)),
        'invoice': json.loads(mesh.cat(invoice_id)),
    }


def test_invoice_uri_ignores_top_level_execute_field():
    record = {'invoice_uri': 'http://n/inv-rec'}
    assert (
        invoice_uri_from_response(
            {'invoice_uri': 'http://n/inv-resp'}, record
        )
        == 'http://n/inv-rec'
    )
    assert (
        invoice_uri_from_response(
            {'bom': {'invoice_uri': 'http://n/inv-bom'}, 'invoice_uri': 'x'},
            record,
        )
        == 'http://n/inv-bom'
    )


def test_parse_uv_lock_packages():
    assert parse_uv_lock(_UV_LOCK) == [('numpy', '2.1.0')]
    assert parse_uv_lock(b'not toml {') == []


def test_project_bom_cas_get_stable_and_no_bom_id(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    monkeypatch.setattr(
        'cats.network.bom.syft.syft_binary', lambda explicit=None: None
    )
    monkeypatch.setattr(
        'cats.network.bom.syft.docker_image_digest',
        lambda ref, timeout=15: (
            _IMAGE_HEX if ref == _IMAGE_REF else None
        ),
    )
    graph = _fixture_graph(mesh)
    before = copy.deepcopy(graph['envelope'])

    first = project_bom(
        graph['envelope'],
        mesh,
        image_refs=[_IMAGE_REF],
        created=FIXED_CREATED,
    )
    assert graph['envelope'] == before
    second = project_bom(
        graph['envelope'],
        mesh,
        image_refs=[_IMAGE_REF],
        created=FIXED_CREATED,
    )
    for key in (
        'function_spdx',
        'structure_spdx',
        'runtime_cdx',
        'data_contract',
        'data_dcat',
        'data_spdx',
    ):
        assert is_ni_or_digest(first[key])
        assert first[key] == second[key]
    assert first.get('runtime_syft') is None

    app = Flask(__name__)
    register_cas_routes(app, cats_home=str(tmp_path))
    client = app.test_client()
    loc = LocatorIndex(str(tmp_path))
    media = {
        'function_spdx': MEDIA_SPDX,
        'structure_spdx': MEDIA_SPDX,
        'runtime_cdx': MEDIA_CDX,
        'data_contract': MEDIA_DCAT,
        'data_dcat': MEDIA_DCAT,
        'data_spdx': MEDIA_SPDX,
    }
    for key, media_type in media.items():
        ni = first[key]
        hex_digest = from_ni(ni)
        resp = client.get(f'/ldp/cas/{hex_digest}')
        assert resp.status_code == 200
        stored = mesh.catObj(ni)
        assert resp.data == stored
        body = json.loads(resp.data.decode('utf-8'))
        dumped = json.dumps(body)
        assert FORBIDDEN_BOM_ID not in dumped
        locators = loc.get(ni)
        assert locators is not None
        assert locators['locators'][0]['uri'].endswith(f'/ldp/cas/{hex_digest}')
        assert locators['locators'][0].get('media_type') == media_type

    function_doc = json.loads(mesh.cat(first['function_spdx']))
    assert fru_purl('function', graph['function_id']) in json.dumps(function_doc)
    assert fru_purl('pypi', name='numpy', version='2.1.0') in json.dumps(
        function_doc
    )
    structure_doc = json.loads(mesh.cat(first['structure_spdx']))
    assert fru_purl('structure', graph['structure_id']) in json.dumps(
        structure_doc
    )
    cdx = json.loads(mesh.cat(first['runtime_cdx']))
    assert cdx['bomFormat'] == 'CycloneDX'
    assert cdx['specVersion'] == '1.6'
    assert fru_purl('oci', _IMAGE_HEX, name='kindest/node') in json.dumps(cdx)
    dcat = json.loads(mesh.cat(first['data_dcat']))
    assert dcat['@type'] == 'dcat:Catalog'
    contract = json.loads(mesh.cat(first['data_contract']))
    assert contract['@type'] == 'odcs:DataContract'
    assert dcat.get('dct:conformsTo') == contract['@id']
    assert contract['cats:subject'] == require_ni(
        graph['input_lot_id'], label='data_id'
    )
    dataset = json.loads(mesh.cat(first['data_spdx']))
    assert 'dataset' in dataset['profileConformance']


def test_syft_missing_still_emits_cdx(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    monkeypatch.setattr(
        'cats.network.bom.syft.syft_binary', lambda explicit=None: None
    )
    monkeypatch.setattr(
        'cats.network.bom.syft.docker_image_digest', lambda ref, timeout=15: None
    )
    sae_id = mesh.put_bytes(b'{"rebuilt":false}\n')
    result = project_structure_runtime(
        {},
        mesh,
        structure_as_executed_id=sae_id,
        image_refs=['missing.example/img:latest'],
    )
    assert is_ni_or_digest(result['runtime_cdx'])
    assert result.get('runtime_syft') is None
    doc = json.loads(mesh.cat(result['runtime_cdx']))
    assert doc['components'] == []


def test_individual_projectors_and_network_not_exported(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    monkeypatch.setattr(
        'cats.network.bom.syft.syft_binary', lambda explicit=None: None
    )
    graph = _fixture_graph(mesh)
    fn = project_function_source(
        graph['function'], mesh, function_id=graph['function_id']
    )
    st = project_structure_source(
        graph['structure'], mesh, structure_id=graph['structure_id']
    )
    lots = project_data_lot(
        graph['invoice'], mesh, invoice_id=graph['invoice_id']
    )
    assert is_ni_or_digest(fn)
    assert is_ni_or_digest(st)
    assert is_ni_or_digest(lots['data_dcat'])
    assert is_ni_or_digest(lots['data_contract'])
    import cats.network as network

    assert not hasattr(network, 'project_bom')
    assert not hasattr(network, 'fru_purl')
    assert not hasattr(network, 'attach_runtime_sbom')
    assert not hasattr(network, 'attach_ebom_stems')
    assert not hasattr(network, 'project_input_data')
    assert not hasattr(network, 'project_sysml_quantum')
    assert not hasattr(network, 'project_allocate_view')


def test_require_signed_invoice_uri(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='invoice_uri'):
        project_bom({'invoice_uri': 'http://n/inv-resp', 'bom': {}}, mesh)
