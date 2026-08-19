"""Phase 2b — URI address of record + ni: proof (+ optional hl: emit)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

from cats.network.address_store import AddressStore
from cats.network.cas import (
    CasHttpStore,
    LocatorIndex,
    build_content_ref,
    content_uri,
    from_hl,
    from_ni,
    set_cid_uri,
    sha256_hex,
    to_hl,
    to_ni,
)
from cats.network.feedback.envelope import (
    build_execution_bom,
    sign_execution_bom,
    verify_execution_bom,
)
from cats.network.ldp import (
    InvoiceLdpStore,
    OrderLdpStore,
    invoice_ldp_uri,
    register_ldp_routes,
)
from cats.network.ldp.headers import LDP_RESOURCE


class _NoIpfs:
    def cat_bytes(self, content_id):
        raise AssertionError(f'unexpected IPFS cat: {content_id}')

    def get(self, content_id, dest_path):
        raise AssertionError(f'unexpected IPFS get: {content_id}')

    def dag_export(self, cid, filepath):
        raise AssertionError(f'unexpected IPFS dag_export: {cid}')


def test_content_ref_and_set_cid_uri(tmp_path, monkeypatch):
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5099')
    store = CasHttpStore(str(tmp_path))
    ni = store.put(b'{"x":1}\n')
    ref = build_content_ref(ni, base_url='http://127.0.0.1:5099')
    assert ref['content_id'] == ni
    assert ref['uri'].endswith(f'/ldp/cas/{from_ni(ni)}')
    assert content_uri(ni, base_url='http://127.0.0.1:5099') == ref['uri']

    obj: dict = {}
    set_cid_uri(obj, 'data_cid', ni, base_url='http://127.0.0.1:5099')
    assert 'data_cid' not in obj
    assert obj['data_uri'] == ref['uri']


def test_hl_emit_roundtrip():
    digest = sha256_hex(b'hl-bytes')
    ni = to_ni(digest)
    hl = to_hl(ni, 'https://example.test/ldp/cas/' + digest)
    got_ni, uris = from_hl(hl)
    assert got_ni == ni
    assert uris == ['https://example.test/ldp/cas/' + digest]
    assert to_hl(ni).startswith('hl:')


def test_invoice_order_ldp_routes(tmp_path):
    inv = InvoiceLdpStore(str(tmp_path))
    ord_store = OrderLdpStore(str(tmp_path))
    invoice = {'data_cid': 'ni:///sha-256;aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}
    # Use a real CAS-shaped id
    cas = CasHttpStore(str(tmp_path))
    inv_cid = cas.put((json.dumps({'data_cid': 'x'}) + '\n').encode())
    order_cid = cas.put((json.dumps({'invoice_cid': inv_cid}) + '\n').encode())
    inv.put(inv_cid, {'data_cid': 'x'})
    ord_store.put(order_cid, {'invoice_cid': inv_cid})

    app = Flask(__name__)
    register_ldp_routes(app, cats_home=str(tmp_path))
    client = app.test_client()

    r = client.get(f'/ldp/invoices/{from_ni(inv_cid)}')
    assert r.status_code == 200
    assert r.get_json()['data_cid'] == 'x'
    assert LDP_RESOURCE in (r.headers.get('Link') or '')

    r = client.put(f'/ldp/invoices/{from_ni(inv_cid)}', json={})
    assert r.status_code == 405

    r = client.get(f'/ldp/orders/{from_ni(order_cid)}')
    assert r.status_code == 200
    assert r.get_json()['invoice_cid'] == inv_cid

    r = client.get('/ldp/invoices/')
    assert r.status_code == 200
    assert 'contains' in r.get_json()


def test_addressstore_uri_verify(tmp_path, monkeypatch):
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5099')
    cas = CasHttpStore(str(tmp_path))
    payload = b'uri-proof\n'
    ni = cas.put(payload)
    digest = from_ni(ni)
    uri = f'http://127.0.0.1:5099/ldp/cas/{digest}'
    LocatorIndex(str(tmp_path)).put(ni, uri=uri)

    store = AddressStore(_NoIpfs(), cats_home=str(tmp_path))
    assert store.cat_bytes(uri) == payload
    assert store.cat_bytes(uri, expect_digest=ni) == payload

    # Tamper on-disk CAS bytes under wrong expectation
    with pytest.raises(RuntimeError, match='sha256 mismatch'):
        store.cat_bytes(uri, expect_digest=to_ni('0' * 64))


def test_envelope_prefers_uri_id(tmp_path, monkeypatch):
    monkeypatch.setenv('CATS_HOME', str(tmp_path))
    inv_uri = 'http://127.0.0.1:5099/ldp/invoices/' + ('a' * 64)
    data_uri = 'http://127.0.0.1:5099/ldp/cas/' + ('b' * 64)
    bom = build_execution_bom(
        log_id=to_ni('c' * 64),
        invoice_id=to_ni('a' * 64),
        invoice_uri=inv_uri,
        data_id=to_ni('b' * 64),
        data_uri=data_uri,
        ingress_data_id=to_ni('d' * 64),
        integration_data_id=to_ni('e' * 64),
        node_did=None,
    )
    assert bom['invoice_uri'] == inv_uri
    assert 'invoice_cid' not in bom
    assert 'log_cid' not in bom
    assert bom['stageLineage'][-1]['@id'] == data_uri
    assert bom['stageLineage'][-1]['contentId'] == to_ni('b' * 64)
    signed = sign_execution_bom(bom, cats_home=str(tmp_path))
    verify_execution_bom(signed)


def test_locator_reverse_uri(tmp_path):
    cas = CasHttpStore(str(tmp_path))
    ni = cas.put(b'z')
    uri = invoice_ldp_uri(ni, base_url='http://127.0.0.1:5000')
    loc = LocatorIndex(str(tmp_path))
    loc.put(ni, uri=uri)
    assert loc.find_content_id_for_uri(uri) == ni
    assert loc.find_content_id_for_uri('http://nope') is None
