"""Post-execute handoff projection completeness."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from flask import Flask

from cats.network.cas import (
    CasHttpStore,
    LocatorIndex,
    from_ni,
    register_cas_routes,
    set_ref,
    to_ni,
)
from cats.network.feedback import build_execution_bom, sign_execution_bom
from cats.network.identity import node_did
from cats.network.ldp import BomLdpStore, bom_ldp_uri, register_ldp_routes
from cats.network.registry import (
    BomRegistry,
    assert_handoff_projection_complete,
    assert_registry_claims_reachable,
    build_record,
)


def _digest(n: int) -> str:
    return to_ni(f'{n:x}'.zfill(64))


def _signed_bom(monkeypatch, tmp_path, *, invoice_id: str, log_id: str):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    return sign_execution_bom(
        build_execution_bom(
            log_id=log_id,
            invoice_id=invoice_id,
            node_did=did,
        ),
        cats_home=str(tmp_path),
    )


def test_assert_handoff_projection_complete_ok(monkeypatch, tmp_path):
    home = str(tmp_path)
    inv = _digest(1)
    order = _digest(2)
    data = _digest(3)
    seed = _digest(4)
    log = _digest(5)
    bom_id = _digest(6)
    fn = _digest(7)
    struct = _digest(8)
    inv_in = _digest(9)

    invoice = {}
    set_ref(invoice, 'order', order)
    set_ref(invoice, 'data', data)
    set_ref(invoice, 'seed', seed)
    order_obj = {}
    set_ref(order_obj, 'function', fn)
    set_ref(order_obj, 'structure', struct)
    set_ref(order_obj, 'invoice', inv_in)
    input_inv = {}
    set_ref(input_inv, 'data', _digest(10))

    mesh = MagicMock()
    mesh.CATS_HOME = home

    def _cat(key):
        if key in (inv, invoice.get('order_uri')):
            return json.dumps(invoice)
        # ref_uri may return http; also accept equality ids
        if key in (order, invoice.get('order_uri')) or key == order:
            return json.dumps(order_obj)
        if key == inv_in or key == order_obj.get('invoice_uri'):
            return json.dumps(input_inv)
        # build_record cats invoice via invoice locator from bom
        if key == inv:
            return json.dumps(invoice)
        raise KeyError(key)

    def _cat2(key):
        # Normalize: accept uri path hex or ni
        raw = key
        mapping = {
            inv: invoice,
            order: order_obj,
            inv_in: input_inv,
        }
        if raw in mapping:
            return json.dumps(mapping[raw])
        for cid, obj in mapping.items():
            if isinstance(raw, str) and from_ni(cid) in raw:
                return json.dumps(obj)
        raise KeyError(key)

    mesh.cat.side_effect = _cat2

    bom = _signed_bom(monkeypatch, tmp_path, invoice_id=inv, log_id=log)
    # Rebuild bom with set_ref invoice for uri consistency
    from cats.network.cas import set_ref as _set_ref

    bom_body = {
        k: v for k, v in bom.items() if k not in ('proof',)
    }
    # signed bom already has invoice ref from build_execution_bom

    record = build_record(
        bom,
        bom_id,
        content_mesh=mesh,
        locators={
            'bom_ldp_uri': bom_ldp_uri(bom_id, base_url='http://127.0.0.1:5002'),
            'invoice_uri': f'http://127.0.0.1:5002/ldp/cas/{from_ni(inv)}',
            'order_uri': f'http://127.0.0.1:5002/ldp/orders/{from_ni(order)}',
        },
    )
    reg = BomRegistry(home)
    reg.put(record)

    loc = LocatorIndex(home)
    for stage_id in (bom_id, inv, order, data, seed, log):
        loc.put_cas_node_locator(stage_id, base_url='http://127.0.0.1:5002')

    out = assert_handoff_projection_complete(
        reg, loc, bom_id=bom_id, require_stage_locators=True
    )
    assert out['data'] == data
    assert out['order'] == order


def test_assert_handoff_projection_complete_missing_locator(monkeypatch, tmp_path):
    home = str(tmp_path)
    inv = _digest(1)
    order = _digest(2)
    data = _digest(3)
    log = _digest(5)
    bom_id = _digest(6)

    invoice = {}
    set_ref(invoice, 'order', order)
    set_ref(invoice, 'data', data)
    mesh = MagicMock()
    mesh.CATS_HOME = home
    mesh.cat.side_effect = lambda key: json.dumps(invoice)

    bom = _signed_bom(monkeypatch, tmp_path, invoice_id=inv, log_id=log)
    record = build_record(
        bom,
        bom_id,
        content_mesh=mesh,
        locators={
            'bom_ldp_uri': bom_ldp_uri(bom_id, base_url='http://127.0.0.1:5002'),
            'invoice_uri': f'http://127.0.0.1:5002/ldp/cas/{from_ni(inv)}',
        },
    )
    reg = BomRegistry(home)
    reg.put(record)
    loc = LocatorIndex(home)
    # Only register bom — data locator missing → fail when require_stage_locators
    loc.put_cas_node_locator(bom_id, base_url='http://127.0.0.1:5002')

    with pytest.raises(AssertionError, match='LocatorIndex missing'):
        assert_handoff_projection_complete(
            reg, loc, bom_id=bom_id, require_stage_locators=True
        )


def test_projection_then_reachability_chain(monkeypatch, tmp_path):
    home = str(tmp_path)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')

    store = CasHttpStore(home)
    inv = _digest(1)
    order = _digest(2)
    data = _digest(3)
    seed = _digest(4)
    log = _digest(5)
    bom_id = _digest(6)

    order_obj = {
        'function_uri': 'http://127.0.0.1:5002/ldp/cas/f',
        'structure_uri': 'http://127.0.0.1:5002/ldp/cas/s',
        'invoice_uri': 'http://127.0.0.1:5002/ldp/cas/ii',
    }
    store.put(json.dumps(order_obj).encode())  # unused equality
    data_uri = f'http://127.0.0.1:5002/ldp/cas/{from_ni(store.put(b"out"))}'
    seed_uri = (
        f'http://127.0.0.1:5002/ldp/cas/'
        f'{from_ni(store.put(json.dumps({"s": 1}).encode()))}'
    )
    # Force known digests into CAS for invoice/order bodies under inv/order ids
    # by putting exact bytes — digests won't match inv/order ni unless we use
    # store paths. Simpler: put invoice JSON at arbitrary CAS and point URIs.
    invoice = {
        'order_uri': f'http://127.0.0.1:5002/ldp/cas/{from_ni(store.put(json.dumps(order_obj).encode()))}',
        'data_uri': data_uri,
        'seed_uri': seed_uri,
    }
    inv_bytes = json.dumps(invoice).encode()
    inv_ni = store.put(inv_bytes)
    invoice_uri = f'http://127.0.0.1:5002/ldp/cas/{from_ni(inv_ni)}'

    bom = {'invoice_uri': invoice_uri}
    bom_ni = store.put(json.dumps(bom).encode())
    BomLdpStore(home).put(bom_ni, bom)
    bom_uri = bom_ldp_uri(bom_ni, base_url='http://127.0.0.1:5002')

    # Registry record with equality ids matching what we will locator-index
    record = {
        'content_id': bom_ni,
        'data': data,
        'order': order,
        'invoice_uri': invoice_uri,
        'data_uri': data_uri,
        'seed_uri': seed_uri,
        'locators': {
            'bom_ldp_uri': bom_uri,
            'invoice_uri': invoice_uri,
            'order_uri': invoice['order_uri'],
        },
    }
    reg = BomRegistry(home)
    reg.put(record)
    loc = LocatorIndex(home)
    for stage_id in (bom_ni, data, order, inv_ni):
        loc.put_cas_node_locator(stage_id, base_url='http://127.0.0.1:5002')

    assert_handoff_projection_complete(
        reg,
        loc,
        bom_id=bom_ni,
        require_stage_locators=True,
        stage_ids=[bom_ni, data, order, inv_ni],
    )

    app = Flask(__name__)
    register_cas_routes(app, cats_home=home)
    register_ldp_routes(app, cats_home=home)
    client = app.test_client()
    base = 'http://127.0.0.1:5002'

    def http_get_json(path):
        local = path[len(base) :] if str(path).startswith(base) else path
        resp = client.get(local)
        assert resp.status_code == 200
        return resp.get_json(silent=True) or json.loads(resp.data)

    def http_get(path):
        local = path[len(base) :] if str(path).startswith(base) else path
        resp = client.get(local)
        assert resp.status_code == 200
        return resp.data

    assert_registry_claims_reachable(
        record, http_get_json=http_get_json, http_get=http_get
    )
