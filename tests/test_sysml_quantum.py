"""P5 SysML v2 eBOM view — compile from Order, validate, Factory stays off."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cats.network.bom import (
    project_sysml_quantum,
    quantum_sysml,
    validate_sysml_quantum,
)
from cats.network.bom.project import make_fetch
from cats.network.bom.read import require_ni, stem_id
from cats.network.bom.sysml import PART_DEFS, PORT_DEFS, USAGE_ROLES
from cats.network.cas import is_ni_or_digest
from cats.network.feedback import build_execution_bom, sign_execution_bom
from cats.network.identity import node_did
from tests.test_bom_projectors import FORBIDDEN_BOM_ID, _fixture_graph, _mesh

REPO_ROOT = Path(__file__).resolve().parents[1]
_SYSML_IMPORT = ('cats.network.bom.sysml', 'from cats.network.bom.sysml')


def _usages(doc: dict) -> dict:
    return {
        item['name']: item
        for item in doc.get('ownedElement') or []
        if item.get('@type') == 'sysml:PartUsage'
    }


def _order_graph(mesh):
    graph = _fixture_graph(mesh)
    order = json.loads(mesh.cat(graph['order_id']))
    graph['order'] = order
    return graph


def test_quantum_sysml_catalog_and_order_usage(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    graph = _order_graph(mesh)
    home = str(tmp_path)
    fn = graph['function']
    st = graph['structure']
    doc = quantum_sysml(
        order_id=graph['order_id'],
        function_id=graph['function_id'],
        process_id=stem_id(fn, 'process', cats_home=home),
        infrafunction_id=stem_id(fn, 'infrafunction', cats_home=home),
        structure_id=graph['structure_id'],
        plant_id=stem_id(st, 'plant', cats_home=home),
        infrastructure_id=stem_id(st, 'infrastructure', cats_home=home),
    )
    parts = {
        item['name']
        for item in doc['ownedElement']
        if item.get('@type') == 'sysml:PartDefinition'
    }
    ports = {
        item['name']
        for item in doc['ownedElement']
        if item.get('@type') == 'sysml:PortDefinition'
    }
    assert parts == set(PART_DEFS)
    assert ports == {name for name, _owner, _side in PORT_DEFS}
    usages = _usages(doc)
    assert set(usages) == set(USAGE_ROLES)
    order_ni = require_ni(graph['order_id'], label='order_id')
    assert usages['ArchitecturalQuantum']['contentId'] == order_ni
    assert usages['Function']['contentId'] == require_ni(
        graph['function_id'], label='function_id'
    )
    assert usages['Structure']['contentId'] == require_ni(
        graph['structure_id'], label='structure_id'
    )
    assert FORBIDDEN_BOM_ID not in json.dumps(doc)
    assert 'content_id' not in json.dumps(doc)


def test_project_sysml_quantum_byte_stable_and_validate(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    graph = _order_graph(mesh)
    first = project_sysml_quantum(
        graph['order'], mesh, order_id=graph['order_id']
    )
    second = project_sysml_quantum(
        graph['order'], mesh, order_id=graph['order_id']
    )
    assert first == second
    assert is_ni_or_digest(first)
    doc = json.loads(mesh.cat(first))
    validate_sysml_quantum(
        doc,
        graph['order'],
        order_id=graph['order_id'],
        function=graph['function'],
        structure=graph['structure'],
        fetch=make_fetch(mesh),
        cats_home=str(tmp_path),
    )
    usages = _usages(doc)
    home = str(tmp_path)
    assert usages['Process']['contentId'] == require_ni(
        stem_id(graph['function'], 'process', cats_home=home), label='process'
    )
    assert usages['Plant']['contentId'] == require_ni(
        stem_id(graph['structure'], 'plant', cats_home=home), label='plant'
    )


def test_validate_stale_function_fails(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    graph = _order_graph(mesh)
    ni = project_sysml_quantum(
        graph['order'], mesh, order_id=graph['order_id']
    )
    doc = json.loads(mesh.cat(ni))
    stale = dict(graph['order'])
    other = mesh.put_json({'process_uri': 'http://n/other'})
    from cats.network.cas import set_ref

    set_ref(stale, 'function', other)
    with pytest.raises(ValueError, match='stale Function'):
        validate_sysml_quantum(
            doc,
            stale,
            order_id=graph['order_id'],
            function=graph['function'],
            structure=graph['structure'],
            cats_home=str(tmp_path),
        )


def test_validate_missing_plant_fails(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    graph = _order_graph(mesh)
    home = str(tmp_path)
    fn = graph['function']
    doc = quantum_sysml(
        order_id=graph['order_id'],
        function_id=graph['function_id'],
        process_id=stem_id(fn, 'process', cats_home=home),
        infrafunction_id=stem_id(fn, 'infrafunction', cats_home=home),
        structure_id=graph['structure_id'],
        plant_id=None,
        infrastructure_id=stem_id(
            graph['structure'], 'infrastructure', cats_home=home
        ),
    )
    with pytest.raises(ValueError, match='missing contentId for Plant'):
        validate_sysml_quantum(
            doc,
            graph['order'],
            order_id=graph['order_id'],
            function=graph['function'],
            structure=graph['structure'],
            cats_home=home,
        )


def test_signed_bom_has_no_sysml_keys(monkeypatch, tmp_path):
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
    assert 'sysml:Package' not in dumped
    assert 'sysml_uri' not in dumped
    assert 'PartDefinition' not in dumped


def test_project_sysml_not_on_network_or_project_bom(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    graph = _order_graph(mesh)
    from cats.network.bom import project_bom

    result = project_bom(graph['envelope'], mesh, record=None)
    assert 'sysml' not in result
    import cats.network as network

    assert not hasattr(network, 'project_sysml_quantum')
    assert not hasattr(network, 'quantum_sysml')
    assert not hasattr(network, 'validate_sysml_quantum')


def test_factory_executor_do_not_import_sysml():
    offenders = []
    for package in ('cats/factory', 'cats/executor'):
        root = REPO_ROOT / package
        for path in root.rglob('*.py'):
            text = path.read_text(encoding='utf-8')
            if any(token in text for token in _SYSML_IMPORT):
                offenders.append(str(path.relative_to(REPO_ROOT)))
            if '.sysml' in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, 'Factory/Executor must not import SysML:\n' + '\n'.join(
        offenders
    )
