"""P4 Order eBOM stems — CATS_SBOM mint / link*, refs only, remint not carry."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from cats.network import ContentMesh
from cats.network.bom import (
    attach_ebom_stems,
    project_input_data,
    strip_ebom_stems,
)
from cats.network.cas import ref_id, sha256_hex, to_ni
from data.input.function.infrafunction import infrafunction_subproc
from data.input.function.process import (
    egress,
    ingress,
    integration_cache,
    process_0,
    process_1,
)


FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        'bomFormat',
        'profileConformance',
        'dcat:dataset',
        'artifacts',
        'spdxVersion',
        'SPDXID',
    }
)


def _mesh(tmp_path, monkeypatch) -> ContentMesh:
    client = ContentMesh(ipfsClient=MagicMock(), CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    return client


def _spy_put_json(client, monkeypatch):
    put_objs = []
    real = client.put_json

    def _spy(obj, **kwargs):
        put_objs.append(obj)
        return real(obj, **kwargs)

    monkeypatch.setattr(client, 'put_json', _spy)
    return put_objs


def _write_function_fixture(input_home: Path):
    process = input_home / 'function' / 'process'
    ifr = input_home / 'function' / 'infrafunction'
    process.mkdir(parents=True)
    ifr.mkdir(parents=True)
    (process / '__init__.py').write_text('# process\n')
    (process / 'callables.py').write_text('def process_0():\n    pass\n')
    (ifr / '__init__.py').write_text('# infrafunction\n')
    (ifr / 'actuator.py').write_text('def infrafunction_subproc():\n    pass\n')


def _order_fixture(tmp_path):
    structure = tmp_path / 'structure'
    (structure / 'plant').mkdir(parents=True)
    (structure / 'infrastructure').mkdir(parents=True)
    (structure / 'main.tf').write_text('module "plant" { source = "./plant" }\n')
    (structure / 'outputs.tf').write_text('output "x" { value = 1 }\n')
    (structure / '.terraform.lock.hcl').write_text('# lock\n')
    (structure / 'plant' / 'x.tf').write_text('x')
    (structure / 'infrastructure' / 'y.tf').write_text('y')
    _write_function_fixture(tmp_path)
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'f.csv').write_text('a\n')
    return structure, data


def _mock_projectors(monkeypatch):
    def _fn_source(function, mesh, *, function_id, **_kwargs):
        return to_ni(sha256_hex(f'function_sbom:{function_id}'.encode()))

    def _st_source(structure, mesh, *, structure_id, **_kwargs):
        return to_ni(sha256_hex(f'structure_sbom:{structure_id}'.encode()))

    def _input_data(mesh, *, data_id, data_uri=None, **_kwargs):
        return {
            'data_dcat': to_ni(sha256_hex(f'dcat:{data_id}'.encode())),
            'data_spdx': to_ni(sha256_hex(f'spdx:{data_id}'.encode())),
        }

    monkeypatch.setattr(
        'cats.network.bom.project.project_function_source', _fn_source
    )
    monkeypatch.setattr(
        'cats.network.bom.project.project_structure_source', _st_source
    )
    monkeypatch.setattr(
        'cats.network.bom.project.project_input_data', _input_data
    )


def _minted_order(put_objs):
    return next(
        obj
        for obj in put_objs
        if isinstance(obj, dict)
        and 'function_uri' in obj
        and 'structure_uri' in obj
        and 'invoice_uri' in obj
        and 'structure_filepath' in obj
    )


def test_project_input_data_emits_dcat_and_spdx(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    data_id = mesh.put_bytes(b'input-lot')
    lots = project_input_data(mesh, data_id=data_id)
    dcat = json.loads(mesh.cat(lots['data_dcat']))
    spdx = json.loads(mesh.cat(lots['data_spdx']))
    assert 'dcat:dataset' in json.dumps(dcat)
    assert spdx.get('specVersion') == '3.0.1' or 'spdx' in json.dumps(spdx).lower()


def test_attach_ebom_stems_flag_off(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    monkeypatch.delenv('CATS_SBOM', raising=False)
    order: dict = {}
    assert (
        attach_ebom_stems(
            order,
            mesh,
            function={},
            function_id=mesh.put_json({}),
            structure={},
            structure_id=mesh.put_json({}),
            data_id=mesh.put_bytes(b'lot'),
        )
        is None
    )
    assert 'function_sbom_uri' not in order
    assert 'structure_sbom_uri' not in order
    assert 'input_data_sbom_uri' not in order


def test_attach_ebom_stems_flag_on_refs_only(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    monkeypatch.setenv('CATS_SBOM', '1')
    function_id = mesh.put_json({})
    structure_id = mesh.put_json({})
    data_id = mesh.put_bytes(b'lot')
    order: dict = {}
    result = attach_ebom_stems(
        order,
        mesh,
        function={},
        function_id=function_id,
        structure={},
        structure_id=structure_id,
        data_id=data_id,
    )
    assert result
    assert order.get('function_sbom_uri')
    assert order.get('structure_sbom_uri')
    assert order.get('input_data_sbom_uri')
    dumped = json.dumps(order)
    assert 'spdxVersion' not in dumped
    assert 'dcat:dataset' not in dumped
    assert 'bomFormat' not in dumped
    keys = set(order)
    assert keys.isdisjoint(FORBIDDEN_PAYLOAD_KEYS)
    nest = json.loads(mesh.cat(result['input_data_sbom']))
    assert nest.get('dcat_uri')
    assert nest.get('spdx_uri')
    assert set(nest).isdisjoint(FORBIDDEN_PAYLOAD_KEYS)


def test_strip_ebom_stems_drops_uri_and_cid():
    order = {
        'function_sbom_uri': 'http://old/fn',
        'function_sbom_cid': 'QmOldFn',
        'structure_sbom_uri': 'http://old/st',
        'input_data_sbom_cid': 'QmOldIn',
        'function_uri': 'http://keep/fn',
    }
    strip_ebom_stems(order)
    assert 'function_sbom_uri' not in order
    assert 'function_sbom_cid' not in order
    assert 'structure_sbom_uri' not in order
    assert 'input_data_sbom_cid' not in order
    assert order['function_uri'] == 'http://keep/fn'


def test_create_order_request_flag_off_no_stems(tmp_path, monkeypatch):
    structure, data = _order_fixture(tmp_path)
    client = _mesh(tmp_path, monkeypatch)
    monkeypatch.delenv('CATS_SBOM', raising=False)

    def _put_dir(path, **_kwargs):
        name = Path(path).name
        return f'Qm{name}', name

    monkeypatch.setattr(client, 'put_dir', _put_dir)
    put_objs = _spy_put_json(client, monkeypatch)
    client.create_order_request(
        ingress_subproc=ingress,
        integrated_subproc=process_0,
        egress_subproc=egress,
        integration_cache_subproc=integration_cache,
        infrafunction_subproc=infrafunction_subproc,
        data_dirpath=str(data),
        structure_filepath=str(structure),
    )
    order = _minted_order(put_objs)
    assert 'function_sbom_uri' not in order
    assert 'structure_sbom_uri' not in order
    assert 'input_data_sbom_uri' not in order


def test_create_order_request_flag_on_sets_uris_before_put(tmp_path, monkeypatch):
    structure, data = _order_fixture(tmp_path)
    client = _mesh(tmp_path, monkeypatch)
    monkeypatch.setenv('CATS_SBOM', '1')
    _mock_projectors(monkeypatch)

    def _put_dir(path, **_kwargs):
        name = Path(path).name
        return f'Qm{name}', name

    monkeypatch.setattr(client, 'put_dir', _put_dir)
    put_objs = _spy_put_json(client, monkeypatch)
    client.create_order_request(
        ingress_subproc=ingress,
        integrated_subproc=process_0,
        egress_subproc=egress,
        integration_cache_subproc=integration_cache,
        infrafunction_subproc=infrafunction_subproc,
        data_dirpath=str(data),
        structure_filepath=str(structure),
    )
    order = _minted_order(put_objs)
    assert order.get('function_sbom_uri')
    assert order.get('structure_sbom_uri')
    assert order.get('input_data_sbom_uri')
    dumped = json.dumps(order)
    assert 'spdxVersion' not in dumped
    assert 'dcat:dataset' not in dumped
    assert 'bomFormat' not in dumped


def test_order_request_from_prior_flag_off_strips_prior_stems(
    tmp_path, monkeypatch
):
    client = _mesh(tmp_path, monkeypatch)
    monkeypatch.delenv('CATS_SBOM', raising=False)
    function_id = client.put_json({'process_source_uri': 'QmProc'})
    structure_id = client.put_json({'root_uri': 'QmRoot'})
    data_id = client.put_bytes(b'lot')
    prior = {
        'function_uri': function_id,
        'structure_uri': structure_id,
        'function_sbom_uri': 'http://old/fn-sbom',
        'function_sbom_cid': 'QmOldFnSbom',
        'structure_sbom_uri': 'http://old/st-sbom',
        'input_data_sbom_uri': 'http://old/in-sbom',
        'structure_filepath': 'structure',
        'flat': {'function_sbom': {'spdxVersion': '3.0.1'}},
    }
    put_objs = _spy_put_json(client, monkeypatch)
    client._order_request_from_prior(
        prior,
        function_id=function_id,
        structure_id=structure_id,
        data_id=data_id,
    )
    order = _minted_order(put_objs)
    assert 'function_sbom_uri' not in order
    assert 'function_sbom_cid' not in order
    assert 'structure_sbom_uri' not in order
    assert 'input_data_sbom_uri' not in order
    assert 'flat' not in order


def test_link_process_remints_function_sbom(tmp_path, monkeypatch):
    monkeypatch.setenv('CATS_SBOM', '1')
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')
    _mock_projectors(monkeypatch)
    client = _mesh(tmp_path, monkeypatch)
    old_fn_sbom = to_ni(sha256_hex(b'prior-function-sbom'))
    prev_process = {
        'ingress_subproc_cid': 'QmIn',
        'integrated_subproc_cid': 'QmInt',
        'egress_subproc_cid': 'QmEg',
        'integration_cache_subproc_cid': 'QmCache',
    }
    prev_infrafunction = {'infrafunction_subproc_cid': 'QmIfr'}
    prev_function = {
        'process_cid': 'QmProcBind',
        'infrafunction_cid': 'QmIfrBind',
        'process_source_cid': 'QmProcSrc',
        'infrafunction_source_cid': 'QmIfrSrc',
    }
    cat_response = {'bom': {'invoice_cid': 'QmInv', 'log_cid': 'QmLog'}}

    def _cat(cid):
        if cid == 'QmInv':
            return json.dumps({'order_cid': 'QmOrder', 'data_cid': 'QmData'})
        if cid == 'QmOrder':
            return json.dumps(
                {
                    'function_cid': 'QmFn',
                    'structure_cid': 'QmStruct',
                    'invoice_cid': 'QmInvOld',
                    'structure_filepath': 'structure',
                    'endpoint': 'http://127.0.0.1:5000/cat/node/init',
                    'function_sbom_uri': old_fn_sbom,
                    'function_sbom_cid': 'QmOldFnSbom',
                    'structure_sbom_uri': 'http://old/st-sbom',
                    'input_data_sbom_uri': 'http://old/in-sbom',
                }
            )
        if cid == 'QmFn':
            return json.dumps(prev_function)
        if cid == 'QmStruct':
            return json.dumps(
                {
                    'root_cid': 'QmRoot',
                    'plant_cid': 'QmPlant',
                    'infrastructure_cid': 'QmInfra',
                }
            )
        if cid == 'QmInvOld':
            return json.dumps({'data_cid': 'QmData'})
        if cid == 'QmProcBind':
            return json.dumps(prev_process)
        if cid == 'QmIfrBind':
            return json.dumps(prev_infrafunction)
        if cid == 'QmLog':
            return json.dumps({})
        return '{}'

    monkeypatch.setattr(client, 'cat', _cat)
    put_objs = _spy_put_json(client, monkeypatch)
    client.linkProcess(cat_response, integrated_subproc=process_1)
    order = _minted_order(put_objs)
    assert order.get('function_sbom_uri')
    assert order['function_sbom_uri'] != old_fn_sbom
    assert 'function_sbom_cid' not in order
    new_fn_id = ref_id(order, 'function', cats_home=str(tmp_path))
    expected = to_ni(sha256_hex(f'function_sbom:{new_fn_id}'.encode()))
    assert ref_id(order, 'function_sbom', cats_home=str(tmp_path)) == expected
