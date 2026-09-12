"""P7 allocate view + local RTM Dataset (independent Forward / Backward)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cats.network.bom import (
    allocate_view,
    attach_ebom_stems,
    data_contract,
    project_allocate_view,
    project_data_lot,
    project_sysml_quantum,
)
from cats.network.bom.documents import CONTRACT_CLAUSES, projection_urn
from cats.network.bom.read import require_ni, stem_id
from cats.network.cas import is_ni_or_digest, ref_id
from cats.network.feedback import build_execution_bom, sign_execution_bom
from cats.network.identity import node_did
from tests.test_bom_projectors import FORBIDDEN_BOM_ID, _fixture_graph, _mesh

REPO_ROOT = Path(__file__).resolve().parents[1]
_RTM_IMPORT = (
    'cats.network.bom.rtm',
    'from cats.network.bom.rtm',
    'import rdflib',
    'import pyshacl',
)


def _order_graph(mesh):
    graph = _fixture_graph(mesh)
    graph['order'] = json.loads(mesh.cat(graph['order_id']))
    return graph


def _sysml_and_contract(mesh, graph):
    sysml_id = project_sysml_quantum(
        graph['order'], mesh, order_id=graph['order_id']
    )
    sysml_doc = json.loads(mesh.cat(sysml_id))
    lots = project_data_lot(
        graph['invoice'], mesh, invoice_id=graph['invoice_id']
    )
    contract_doc = json.loads(mesh.cat(lots['data_contract']))
    invoice_dcat = json.loads(mesh.cat(lots['data_dcat']))
    return sysml_doc, contract_doc, invoice_dcat, lots


def _signed_bom(mesh, graph, tmp_path):
    home = str(tmp_path)
    invoice = graph['invoice']
    stages = json.loads(
        mesh.cat(ref_id(invoice, 'data_stages', cats_home=home))
    )
    return sign_execution_bom(
        build_execution_bom(
            log_id=mesh.put_json({'plant_rebuilt': False}),
            invoice_id=graph['invoice_id'],
            node_did=node_did(cats_home=home),
            order_id=graph['order_id'],
            input_data_id=graph['input_lot_id'],
            ingress_data_id=ref_id(stages, 'ingressed_data', cats_home=home),
            integration_data_id=ref_id(
                stages, 'integrated_data', cats_home=home
            ),
            data_id=ref_id(invoice, 'data', cats_home=home),
        ),
        cats_home=home,
    )


def test_allocate_view_clauses_inverse_no_sysml_mutation(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    graph = _order_graph(mesh)
    sysml_doc, contract_doc, _invoice_dcat, _lots = _sysml_and_contract(
        mesh, graph
    )
    before = json.dumps(sysml_doc, sort_keys=True)
    doc = allocate_view(sysml_doc=sysml_doc, contract_doc=contract_doc)
    assert json.dumps(sysml_doc, sort_keys=True) == before
    order_ni = require_ni(graph['order_id'], label='order_id')
    assert doc['@id'] == projection_urn('allocate', order_ni)
    assert doc['@type'] == 'cats:AllocateView'
    assert doc['cats:createdBy'] == 'urn:cats:projector:p7'
    edges = doc['cats:edges']
    targets = doc['cats:targets']
    assert len(edges) == len(CONTRACT_CLAUSES) == 3
    titles = [clause['dct:title'] for clause in contract_doc['cats:clauses']]
    assert titles == [name for name, _alloc, _kind in CONTRACT_CLAUSES]
    process = next(
        item['@id']
        for item in sysml_doc['ownedElement']
        if item.get('name') == 'Process' and item.get('@type') == 'sysml:PartUsage'
    )
    egress = next(edge for edge in edges if edge['@id'].endswith('#egress'))
    assert egress['cats:allocatesTo'] == process
    assert egress['cats:enforced'] is False
    freshness = next(edge for edge in edges if edge['@id'].endswith('#freshness'))
    privacy = next(edge for edge in edges if edge['@id'].endswith('#privacy'))
    assert freshness['cats:allocatesTo'] == 'urn:cats:concern:freshness'
    assert privacy['cats:allocatesTo'] == 'urn:cats:concern:privacy'
    by_from = {item['cats:allocatedFrom']: item for item in targets}
    for edge in edges:
        inverse = by_from[edge['@id']]
        assert inverse['cats:clause'] == edge['@id']
        assert inverse['@id'] == edge['cats:allocatesTo']
    dumped = json.dumps(doc)
    assert FORBIDDEN_BOM_ID not in dumped
    assert 'content_id' not in dumped
    assert 'syft' not in dumped.lower()
    assert 'grype' not in dumped.lower()


def test_project_allocate_view_cas_not_on_project_bom(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    graph = _order_graph(mesh)
    sysml_doc, contract_doc, _invoice_dcat, _lots = _sysml_and_contract(
        mesh, graph
    )
    first = project_allocate_view(sysml_doc, contract_doc, mesh)
    second = project_allocate_view(sysml_doc, contract_doc, mesh)
    assert first == second
    assert is_ni_or_digest(first)
    stored = json.loads(mesh.cat(first))
    assert stored['@type'] == 'cats:AllocateView'
    from cats.network.bom import project_bom

    result = project_bom(graph['envelope'], mesh, record=None)
    assert 'allocate' not in result
    import cats.network as network

    assert not hasattr(network, 'project_allocate_view')
    assert not hasattr(network, 'allocate_view')
    assert not hasattr(network, 'load_rtm')


def test_flag_on_order_and_invoice_share_conforms_to(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    monkeypatch.setenv('CATS_SBOM', '1')
    graph = _order_graph(mesh)
    lots = project_data_lot(
        graph['invoice'], mesh, invoice_id=graph['invoice_id']
    )
    contract = json.loads(mesh.cat(lots['data_contract']))
    invoice_dcat = json.loads(mesh.cat(lots['data_dcat']))
    order: dict = {}
    result = attach_ebom_stems(
        order,
        mesh,
        function=graph['function'],
        function_id=graph['function_id'],
        structure=graph['structure'],
        structure_id=graph['structure_id'],
        data_id=graph['input_lot_id'],
    )
    assert result
    nest = json.loads(mesh.cat(result['input_data_sbom']))
    uri_keys = {key for key in nest if key.endswith('_uri')}
    assert uri_keys == {'dcat_uri', 'spdx_uri'}
    order_dcat = json.loads(
        mesh.cat(ref_id(nest, 'dcat', cats_home=str(tmp_path)))
    )
    assert invoice_dcat['dct:conformsTo'] == contract['@id']
    assert order_dcat['dct:conformsTo'] == contract['@id']
    assert contract['@id'] == projection_urn(
        'odcs', require_ni(graph['input_lot_id'], label='data_id')
    )


def _rtm_docs(mesh, graph, tmp_path, monkeypatch):
    monkeypatch.setenv('CATS_SBOM', '1')
    sysml_doc, contract_doc, invoice_dcat, _lots = _sysml_and_contract(
        mesh, graph
    )
    allocate_doc = allocate_view(sysml_doc=sysml_doc, contract_doc=contract_doc)
    order: dict = {}
    result = attach_ebom_stems(
        order,
        mesh,
        function=graph['function'],
        function_id=graph['function_id'],
        structure=graph['structure'],
        structure_id=graph['structure_id'],
        data_id=graph['input_lot_id'],
    )
    nest = json.loads(mesh.cat(result['input_data_sbom']))
    order_dcat = json.loads(
        mesh.cat(ref_id(nest, 'dcat', cats_home=str(tmp_path)))
    )
    bom = _signed_bom(mesh, graph, tmp_path)
    return {
        'sysml_doc': sysml_doc,
        'allocate_doc': allocate_doc,
        'contract_doc': contract_doc,
        'order_dcat': order_dcat,
        'invoice_dcat': invoice_dcat,
        'bom': bom,
        'runtime_sbom': {'syft_uri': 'http://n/syft', 'nest': {'syft_uri': 'x'}},
    }


def test_forward_backward_green_and_named_fails(tmp_path, monkeypatch):
    rdflib = pytest.importorskip('rdflib')
    pytest.importorskip('pyshacl')
    from cats.network.bom.rtm import (
        GRAPH_IRIS,
        break_backward_copy,
        drop_order_conforms_copy,
        has_attestation,
        has_earl_automatic,
        interrogate,
        load_rtm,
        validate_backward,
        validate_forward,
    )

    mesh = _mesh(tmp_path, monkeypatch)
    graph = _order_graph(mesh)
    docs = _rtm_docs(mesh, graph, tmp_path, monkeypatch)
    dataset = load_rtm(**docs)
    graph_ids = {str(ctx.identifier) for ctx in dataset.graphs()}
    assert graph_ids >= set(GRAPH_IRIS.values())
    forward = validate_forward(dataset)
    backward = validate_backward(dataset)
    assert forward['conforms'], forward['text']
    assert backward['conforms'], backward['text']
    assert has_earl_automatic(dataset)
    assert not has_attestation(dataset)

    fwd_fail = validate_forward(drop_order_conforms_copy(dataset))
    bwd_ok = validate_backward(drop_order_conforms_copy(dataset))
    assert not fwd_fail['conforms']
    assert 'mBOM did not promise' in (fwd_fail['text'] or '')
    assert bwd_ok['conforms'], bwd_ok['text']

    bwd_fail = validate_backward(break_backward_copy(dataset))
    fwd_ok = validate_forward(break_backward_copy(dataset))
    assert not bwd_fail['conforms']
    assert fwd_ok['conforms'], fwd_ok['text']

    steps = interrogate.rerun(docs['bom'], dataset)
    assert steps == [
        'accept',
        'ingress',
        'hotF',
        'egress',
        'sign_execution_bom',
    ]
    assert interrogate.rerun(docs['bom']) == steps
    _ = rdflib


def test_walks_without_rdflib(tmp_path, monkeypatch):
    from cats.network.bom.rtm import walk_backward, walk_forward

    mesh = _mesh(tmp_path, monkeypatch)
    graph = _order_graph(mesh)
    sysml_doc, contract_doc, invoice_dcat, _lots = _sysml_and_contract(
        mesh, graph
    )
    allocate_doc = allocate_view(sysml_doc=sysml_doc, contract_doc=contract_doc)
    order_dcat = {'dct:conformsTo': contract_doc['@id']}
    forward = walk_forward(allocate_doc, order_dcat=order_dcat)
    assert forward['clause'].endswith('#egress')
    assert forward['target'].endswith('#usage:Process')
    assert forward['order_promised'] == contract_doc['@id']
    egress = stem_id(graph['invoice'], 'data', cats_home=str(tmp_path))
    backward = walk_backward(allocate_doc, invoice_dcat, lot=egress)
    assert backward['lot'] == require_ni(egress, label='egress')
    assert backward['contract'] == contract_doc['@id']
    assert backward['clause'].endswith('#egress')


def test_rtm_not_on_network_or_factory():
    import cats.network as network

    assert not hasattr(network, 'load_rtm')
    assert not hasattr(network, 'validate_forward')
    offenders = []
    for package in ('cats/factory', 'cats/executor'):
        root = REPO_ROOT / package
        for path in root.rglob('*.py'):
            text = path.read_text(encoding='utf-8')
            if any(token in text for token in _RTM_IMPORT):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, 'Factory/Executor must not import rtm:\n' + '\n'.join(
        offenders
    )
