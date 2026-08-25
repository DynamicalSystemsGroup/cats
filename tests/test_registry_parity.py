"""Registry index parity tests — Python APIs ↔ HTTP ``GET /ldp/registry/…``.

**Parity** = the same BomRegistry / LocatorIndex facts agree when read via
on-disk Python APIs and via the Node's ``/ldp/registry/…`` routes (Flask test
client here; live Node in ``notebooks/new_cats_demo.py``).

Goal: catch drift between disk indexes and the HTTP facade used by ``init`` /
``link*``. These tests do **not** validate signed ExecutionBom or Invoice
payloads — only that projected records, by-data / by-order lists, and
by-content locator URI sets match across both access paths.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from flask import Flask

from cats.network.cas import LocatorIndex, to_ni
from cats.network.feedback import build_execution_bom, sign_execution_bom
from cats.network.identity import node_did
from cats.network.registry import (
    BomRegistry,
    assert_locator_index_parity,
    assert_registry_bom_parity,
    assert_registry_by_data_parity,
    assert_registry_by_order_parity,
    assert_registry_index_parity,
    build_record,
    project_record,
    register_registry_routes,
)


def _signed_bom(monkeypatch, tmp_path, *, invoice_id='QmInv'):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    return sign_execution_bom(
        build_execution_bom(
            log_id='QmLog',
            invoice_id=invoice_id,
            node_did=did,
        ),
        cats_home=str(tmp_path),
    )


def _mesh_with_invoice(
    *,
    invoice_id='QmInv',
    order_id='QmOrder',
    data_id='QmDataOut',
    function_id='QmFn',
    structure_id='QmStruct',
    input_data_id='QmDataIn',
):
    mesh = MagicMock()

    def _cat(cid):
        if cid == invoice_id:
            return json.dumps({
                'order_cid': order_id,
                'data_cid': data_id,
                'ingress_data_cid': 'QmIngress',
                'integration_data_cid': 'QmInteg',
                'seed_cid': 'QmSeed',
            })
        if cid == order_id:
            return json.dumps({
                'function_cid': function_id,
                'structure_cid': structure_id,
                'invoice_cid': 'QmInvIn',
            })
        if cid == 'QmInvIn':
            return json.dumps({'data_cid': input_data_id})
        raise KeyError(cid)

    mesh.cat.side_effect = _cat
    return mesh


def _flask_http_get_json(client):
    def http_get_json(path):
        resp = client.get(path)
        assert resp.status_code == 200, (path, resp.status_code, resp.data)
        return resp.get_json()

    return http_get_json


def test_registry_index_parity_python_vs_http(monkeypatch, tmp_path):
    """Full umbrella: disk BomRegistry/LocatorIndex ≡ Flask /ldp/registry maps."""
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice()
    record = build_record(
        bom,
        'QmParity',
        content_mesh=mesh,
        locators={'bom_ldp_uri': 'http://127.0.0.1:5002/ldp/boms/QmParity'},
    )
    reg = BomRegistry(str(tmp_path))
    reg.put(record)

    data_uri = 'http://127.0.0.1:5002/ldp/cas/deadbeef'
    LocatorIndex(str(tmp_path)).put('QmDataOut', uri=data_uri)

    app = Flask(__name__)
    register_registry_routes(app, cats_home=str(tmp_path))
    client = app.test_client()

    out = assert_registry_index_parity(
        registry=reg,
        locator_index=LocatorIndex(str(tmp_path)),
        bom_id='QmParity',
        http_get_json=_flask_http_get_json(client),
        allow_ambiguous=False,
    )
    assert out['data_id'] == 'QmDataOut'
    assert out['order_id'] == 'QmOrder'
    assert out['unique_bom'] == 'QmParity'
    assert data_uri in out['data_locators']


def test_registry_index_parity_allow_ambiguous(monkeypatch, tmp_path):
    """Parity still holds when by-data lists multiple BOMs (demo-style)."""
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice()
    for bom_id in ('QmAmbA', 'QmAmbB'):
        record = build_record(
            bom,
            bom_id,
            content_mesh=mesh,
            locators={'bom_ldp_uri': f'http://127.0.0.1:5002/ldp/boms/{bom_id}'},
        )
        BomRegistry(str(tmp_path)).put(record)

    LocatorIndex(str(tmp_path)).put(
        'QmDataOut', uri='http://127.0.0.1:5002/ldp/cas/x'
    )

    app = Flask(__name__)
    register_registry_routes(app, cats_home=str(tmp_path))
    client = app.test_client()
    reg = BomRegistry(str(tmp_path))

    with pytest.raises(Exception):
        assert_registry_index_parity(
            registry=reg,
            locator_index=LocatorIndex(str(tmp_path)),
            bom_id='QmAmbA',
            http_get_json=_flask_http_get_json(client),
            allow_ambiguous=False,
        )

    out = assert_registry_index_parity(
        registry=reg,
        locator_index=LocatorIndex(str(tmp_path)),
        bom_id='QmAmbA',
        http_get_json=_flask_http_get_json(client),
        allow_ambiguous=True,
    )
    assert out['unique_bom'] == 'QmAmbA'
    assert 'QmAmbA' in out['bom_ids_by_data']


def test_granular_parity_helpers(monkeypatch, tmp_path):
    """Each parity helper: one Python index read vs one HTTP registry GET."""
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice()
    record = build_record(
        bom,
        'QmGran',
        content_mesh=mesh,
        locators={'bom_ldp_uri': 'http://127.0.0.1:5002/ldp/boms/QmGran'},
    )
    BomRegistry(str(tmp_path)).put(record)
    LocatorIndex(str(tmp_path)).put(
        'QmDataOut', uri='http://127.0.0.1:5002/ldp/cas/y'
    )

    app = Flask(__name__)
    register_registry_routes(app, cats_home=str(tmp_path))
    client = app.test_client()
    http = _flask_http_get_json(client)
    reg = BomRegistry(str(tmp_path))

    assert_registry_bom_parity(
        record, http('/ldp/registry/boms/QmGran'), bom_id='QmGran'
    )
    assert_registry_by_data_parity(
        reg.lookup_bom('QmDataOut'),
        http('/ldp/registry/by-data/QmDataOut'),
        data_id='QmDataOut',
    )
    assert_registry_by_order_parity(
        reg.lookup_by_order('QmOrder'),
        http('/ldp/registry/by-order/QmOrder'),
        order_id='QmOrder',
        bom_id='QmGran',
    )
    assert_locator_index_parity(
        LocatorIndex(str(tmp_path)).lookup_uris('QmDataOut'),
        http('/ldp/registry/by-content/QmDataOut'),
    )


def test_locator_parity_with_digest(tmp_path):
    """LocatorIndex URIs ≡ by-content for ni:/hex digests (not only legacy CIDs)."""
    digest = 'a' * 64
    ni = to_ni(digest)
    uri = f'http://127.0.0.1:5002/ldp/cas/{digest}'
    LocatorIndex(str(tmp_path)).put(ni, uri=uri)

    app = Flask(__name__)
    register_registry_routes(app, cats_home=str(tmp_path))
    client = app.test_client()
    resp = client.get(f'/ldp/registry/by-content/{digest}')
    assert resp.status_code == 200
    assert_locator_index_parity(
        LocatorIndex(str(tmp_path)).lookup_uris(ni),
        resp.get_json(),
    )


def test_project_record_matches_http_shape(monkeypatch, tmp_path):
    """BOM parity depends on route body == project_record (shared projection)."""
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice()
    record = build_record(
        bom,
        'QmShape',
        content_mesh=mesh,
        locators={'bom_ldp_uri': 'http://n/ldp/boms/QmShape'},
    )
    BomRegistry(str(tmp_path)).put(record)
    app = Flask(__name__)
    register_registry_routes(app, cats_home=str(tmp_path))
    body = app.test_client().get('/ldp/registry/boms/QmShape').get_json()
    assert project_record(record) == body
