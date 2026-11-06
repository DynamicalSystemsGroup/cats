"""P6 data-contract spec node — cite on DCAT, no envelope stem."""
from __future__ import annotations

import json
from pathlib import Path

from cats.network.bom import (
    attach_ebom_stems,
    data_contract,
    project_data_lot,
    project_input_data,
    put_input_data_sbom_nest,
)
from cats.network.bom.documents import CONTRACT_CLAUSES, projection_urn
from cats.network.bom.read import require_ni
from cats.network.cas import is_ni_or_digest
from cats.network.feedback import build_execution_bom, sign_execution_bom
from cats.network.identity import node_did
from cats.network.registry import assert_order_content_equiv
from tests.test_bom_projectors import FORBIDDEN_BOM_ID, _fixture_graph, _mesh
from tests.test_content_equiv_order import _http, _mesh as _equiv_mesh

REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT_IMPORT = (
    'cats.network.bom.documents',
    'from cats.network.bom.documents',
    'from cats.network.bom import data_contract',
)


def test_data_contract_urn_and_clauses(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    graph = _fixture_graph(mesh)
    invoice_ni = require_ni(graph['invoice_id'], label='invoice_id')
    doc = data_contract(subject_id=graph['invoice_id'])
    assert doc['@id'] == projection_urn('odcs', invoice_ni)
    assert doc['@type'] == 'odcs:DataContract'
    assert doc['cats:subject'] == invoice_ni
    assert doc['cats:createdBy'] == 'urn:cats:projector:p6'
    titles = [clause['dct:title'] for clause in doc['cats:clauses']]
    assert titles == [name for name, _alloc, _kind in CONTRACT_CLAUSES]
    for clause in doc['cats:clauses']:
        assert clause['cats:enforced'] is False
    dumped = json.dumps(doc)
    assert FORBIDDEN_BOM_ID not in dumped
    assert 'content_id' not in dumped


def test_project_data_lot_cites_contract_byte_stable(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    graph = _fixture_graph(mesh)
    first = project_data_lot(
        graph['invoice'], mesh, invoice_id=graph['invoice_id']
    )
    second = project_data_lot(
        graph['invoice'], mesh, invoice_id=graph['invoice_id']
    )
    assert first == second
    assert is_ni_or_digest(first['data_contract'])
    contract = json.loads(mesh.cat(first['data_contract']))
    dcat = json.loads(mesh.cat(first['data_dcat']))
    spdx = json.loads(mesh.cat(first['data_spdx']))
    assert dcat['dct:conformsTo'] == contract['@id']
    assert contract['cats:subject'] == require_ni(
        graph['input_lot_id'], label='data_id'
    )
    assert 'dct:conformsTo' not in json.dumps(spdx)
    assert FORBIDDEN_BOM_ID not in json.dumps(contract)
    assert FORBIDDEN_BOM_ID not in json.dumps(dcat)
    assert 'contract_uri' not in graph['invoice']
    assert 'odcs_uri' not in graph['invoice']
    assert 'output_data_sbom_uri' not in graph['invoice']


def test_default_input_data_uncited_ebom_cites_shared_urn(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    monkeypatch.setenv('CATS_SBOM', '1')
    data_id = mesh.put_bytes(b'input-lot')
    lots = project_input_data(mesh, data_id=data_id)
    dcat = json.loads(mesh.cat(lots['data_dcat']))
    assert 'dct:conformsTo' not in dcat
    order: dict = {}
    result = attach_ebom_stems(
        order,
        mesh,
        function={},
        function_id=mesh.put_json({}),
        structure={},
        structure_id=mesh.put_json({}),
        data_id=data_id,
    )
    assert result
    nest = json.loads(mesh.cat(result['input_data_sbom']))
    uri_keys = {key for key in nest if key.endswith('_uri')}
    assert uri_keys == {'dcat_uri', 'spdx_uri'}
    from cats.network.cas import ref_id

    attached_dcat = json.loads(
        mesh.cat(ref_id(nest, 'dcat', cats_home=str(tmp_path)))
    )
    want = projection_urn('odcs', require_ni(data_id, label='data_id'))
    assert attached_dcat['dct:conformsTo'] == want
    assert 'contract_uri' not in order
    assert 'odcs_uri' not in order


def test_project_data_lot_fallback_without_input_lot(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    invoice: dict = {}
    invoice_id = mesh.put_json(invoice)
    lots = project_data_lot(invoice, mesh, invoice_id=invoice_id)
    contract = json.loads(mesh.cat(lots['data_contract']))
    invoice_ni = require_ni(invoice_id, label='invoice_id')
    assert contract['cats:subject'] == invoice_ni
    assert contract['@id'] == projection_urn('odcs', invoice_ni)


def test_project_input_data_optional_conforms_to_keeps_nest(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    data_id = mesh.put_bytes(b'input-lot')
    urn = 'urn:cats:projection:odcs:ni:///sha-256;demo'
    lots = project_input_data(mesh, data_id=data_id, conforms_to=urn)
    nest_id = put_input_data_sbom_nest(mesh, lots)
    nest = json.loads(mesh.cat(nest_id))
    uri_keys = {key for key in nest if key.endswith('_uri')}
    assert uri_keys == {'dcat_uri', 'spdx_uri'}
    dcat = json.loads(mesh.cat(lots['data_dcat']))
    spdx = json.loads(mesh.cat(lots['data_spdx']))
    assert dcat['dct:conformsTo'] == urn
    order = {'input_data_sbom_uri': 'http://n/ldp/cas/indatasbom'}
    bodies = {
        'http://n/ldp/cas/indatasbom': nest,
        nest['dcat_uri']: dcat,
        nest['spdx_uri']: spdx,
    }
    equiv_mesh = _equiv_mesh(bodies)
    http_get_json, http_get = _http(bodies)
    assert_order_content_equiv(
        order,
        content_mesh=equiv_mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )


def test_signed_bom_has_no_contract_keys(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    signed = sign_execution_bom(
        build_execution_bom(
            log_id='QmLog',
            invoice_id='QmInv',
            node_did=did,
        ),
        cats_home=str(tmp_path),
    )
    dumped = json.dumps(signed)
    assert 'odcs:DataContract' not in dumped
    assert 'contract_uri' not in dumped
    assert 'dct:conformsTo' not in dumped


def test_contract_not_on_network():
    import cats.network as network

    assert not hasattr(network, 'data_contract')
    assert not hasattr(network, 'project_data_lot')


def test_factory_executor_do_not_import_contract():
    offenders = []
    for package in ('cats/factory', 'cats/executor'):
        root = REPO_ROOT / package
        for path in root.rglob('*.py'):
            text = path.read_text(encoding='utf-8')
            if any(token in text for token in _CONTRACT_IMPORT):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, 'Factory/Executor must not import contract:\n' + '\n'.join(
        offenders
    )
