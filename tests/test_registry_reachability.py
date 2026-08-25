"""Registry claims → HTTP reachability."""
from __future__ import annotations

import json

import pytest
from flask import Flask

from cats.network.cas import CasHttpStore, from_ni, register_cas_routes, to_ni
from cats.network.ldp import BomLdpStore, OrderLdpStore, bom_ldp_uri, order_ldp_uri
from cats.network.ldp.routes import register_ldp_routes
from cats.network.registry import assert_registry_claims_reachable


def _client_http(client, *, base='http://127.0.0.1:5002'):
    def http_get_json(path):
        url = path if str(path).startswith('http') else f'{base}{path}'
        # Flask test client wants path only for local routes.
        local = url
        if local.startswith(base):
            local = local[len(base) :] or '/'
        resp = client.get(local)
        assert resp.status_code == 200, (local, resp.status_code, resp.data)
        return resp.get_json(silent=True) or json.loads(resp.data)

    def http_get(path):
        url = path if str(path).startswith('http') else f'{base}{path}'
        local = url
        if local.startswith(base):
            local = local[len(base) :] or '/'
        resp = client.get(local)
        assert resp.status_code == 200, (local, resp.status_code, resp.data)
        return resp.data

    return http_get_json, http_get


def test_assert_registry_claims_reachable_ok(tmp_path, monkeypatch):
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    home = str(tmp_path)
    store = CasHttpStore(home)
    inv_ni = store.put(json.dumps({
        'order_uri': 'http://127.0.0.1:5002/ldp/orders/placeholder',
        'data_uri': 'http://127.0.0.1:5002/ldp/cas/placeholder',
        'seed_uri': 'http://127.0.0.1:5002/ldp/cas/placeholder',
    }).encode('utf-8'))
    data_ni = store.put(b'egress-bytes')
    seed_ni = store.put(json.dumps({'k': 1}).encode('utf-8'))
    order_obj = {
        'function_uri': 'http://127.0.0.1:5002/ldp/cas/f',
        'structure_uri': 'http://127.0.0.1:5002/ldp/cas/s',
        'invoice_uri': 'http://127.0.0.1:5002/ldp/cas/ii',
    }
    order_ni = store.put(json.dumps(order_obj).encode('utf-8'))
    OrderLdpStore(home).put(order_ni, order_obj)
    order_uri = order_ldp_uri(order_ni, base_url='http://127.0.0.1:5002')

    invoice = {
        'order_uri': order_uri,
        'data_uri': f'http://127.0.0.1:5002/ldp/cas/{from_ni(data_ni)}',
        'seed_uri': f'http://127.0.0.1:5002/ldp/cas/{from_ni(seed_ni)}',
    }
    # Re-put invoice with real order/data/seed URIs.
    inv_ni = store.put(json.dumps(invoice).encode('utf-8'))
    invoice_uri = f'http://127.0.0.1:5002/ldp/cas/{from_ni(inv_ni)}'

    bom = {'invoice_uri': invoice_uri}
    bom_ni = to_ni('b' * 64)
    # Use a real digest path: put signed-like bom bytes under CasHttpStore key
    # and also BomLdpStore under same id for /ldp/boms/.
    bom_bytes = json.dumps(bom).encode('utf-8')
    bom_ni = store.put(bom_bytes)
    BomLdpStore(home).put(bom_ni, bom)
    bom_uri = bom_ldp_uri(bom_ni, base_url='http://127.0.0.1:5002')

    record = {
        'content_id': bom_ni,
        'invoice_uri': invoice_uri,
        'order_uri': order_uri,
        'data_uri': invoice['data_uri'],
        'seed_uri': invoice['seed_uri'],
        'locators': {
            'bom_ldp_uri': bom_uri,
            'invoice_uri': invoice_uri,
            'order_uri': order_uri,
        },
    }

    app = Flask(__name__)
    register_cas_routes(app, cats_home=home)
    register_ldp_routes(app, cats_home=home)
    client = app.test_client()
    http_get_json, http_get = _client_http(client)

    assert_registry_claims_reachable(
        record, http_get_json=http_get_json, http_get=http_get
    )


def test_assert_registry_claims_reachable_404(tmp_path, monkeypatch):
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    home = str(tmp_path)
    app = Flask(__name__)
    register_cas_routes(app, cats_home=home)
    register_ldp_routes(app, cats_home=home)
    client = app.test_client()
    http_get_json, _ = _client_http(client)

    record = {
        'locators': {
            'bom_ldp_uri': 'http://127.0.0.1:5002/ldp/boms/' + ('a' * 64),
        }
    }
    with pytest.raises(AssertionError, match='unreachable|not a JSON'):
        assert_registry_claims_reachable(record, http_get_json=http_get_json)
