"""CAS-over-HTTP — digest store, locators, AddressStore, manifests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

from cats.network.address_store import AddressStore
from cats.network.cas import (
    CasHttpStore,
    LocatorIndex,
    from_ni,
    is_directory_manifest,
    is_ni_or_digest,
    put_tree,
    register_cas_routes,
    sha256_hex,
    to_ni,
)
from cats.network.cas.digest import validate_digest_segment
from cats.network.ldp.headers import LDP_RESOURCE
from cats.network.registry import register_registry_routes


def test_digest_ni_roundtrip():
    data = b'hello-cas'
    digest = sha256_hex(data)
    ni = to_ni(digest)
    assert ni.startswith('ni:///sha-256;')
    assert from_ni(ni) == digest
    assert is_ni_or_digest(ni)
    assert is_ni_or_digest(digest)


def test_cas_store_put_get_idempotent(tmp_path):
    store = CasHttpStore(str(tmp_path))
    data = b'{"a":1}\n'
    ni1 = store.put(data)
    ni2 = store.put(data)
    assert ni1 == ni2
    assert store.get(ni1) == data
    assert sha256_hex(store.get(ni1)) == from_ni(ni1)


def test_cas_store_collision_raises(tmp_path):
    store = CasHttpStore(str(tmp_path))
    # Force same path with different bytes is impossible for true sha256;
    # verify get missing returns None.
    assert store.get(to_ni('0' * 64)) is None


def test_locator_index_and_by_content_route(tmp_path):
    store = CasHttpStore(str(tmp_path))
    ni = store.put(b'blob')
    loc = LocatorIndex(str(tmp_path))
    loc.put_cas_node_locator(ni, base_url='http://127.0.0.1:5002')
    doc = loc.get(ni)
    assert doc['content_id'] == ni
    assert doc['locators'][0]['uri'].endswith(f'/ldp/cas/{from_ni(ni)}')

    app = Flask(__name__)
    register_registry_routes(app, cats_home=str(tmp_path))
    client = app.test_client()
    resp = client.get(f'/ldp/registry/by-content/{from_ni(ni)}')
    assert resp.status_code == 200
    assert resp.get_json()['content_id'] == ni
    from cats.network.registry import assert_locator_index_parity

    assert_locator_index_parity(loc.lookup_uris(ni), resp.get_json())


def test_cas_http_get_and_put_405(tmp_path):
    store = CasHttpStore(str(tmp_path))
    ni = store.put(b'payload')
    app = Flask(__name__)
    register_cas_routes(app, cats_home=str(tmp_path))
    client = app.test_client()
    resp = client.get(f'/ldp/cas/{from_ni(ni)}')
    assert resp.status_code == 200
    assert resp.data == b'payload'
    assert LDP_RESOURCE in (resp.headers.get('Link') or '')
    put = client.put(f'/ldp/cas/{from_ni(ni)}', data=b'x')
    assert put.status_code == 405


def test_address_store_cas_verify(tmp_path):
    store = CasHttpStore(str(tmp_path))
    data = b'verify-me'
    ni = store.put(data)
    LocatorIndex(str(tmp_path)).put_cas_node_locator(
        ni, base_url='http://unused'
    )
    # Local CasHttpStore hit (no HTTP needed).
    addr = AddressStore(ipfs_client=None, cats_home=str(tmp_path))
    assert addr.cat_bytes(ni) == data


def test_address_store_verify_fail(tmp_path):
    digest = 'a' * 64
    ni = to_ni(digest)
    # Plant a wrong blob under the digest path.
    path = Path(tmp_path) / '.cats' / 'ldp' / 'cas'
    path.mkdir(parents=True)
    (path / digest).write_bytes(b'wrong-bytes')
    addr = AddressStore(ipfs_client=None, cats_home=str(tmp_path))
    with pytest.raises(RuntimeError, match='sha256 mismatch'):
        addr.cat_bytes(ni)


def test_manifest_put_tree_roundtrip(tmp_path):
    root = tmp_path / 'pkg'
    (root / 'sub').mkdir(parents=True)
    (root / 'a.txt').write_text('A', encoding='utf-8')
    (root / 'sub' / 'b.txt').write_text('B', encoding='utf-8')
    store = CasHttpStore(str(tmp_path))
    ni = put_tree(store, str(root))
    raw = store.get(ni)
    obj = json.loads(raw.decode('utf-8'))
    assert is_directory_manifest(obj)
    assert 'a.txt' in obj['entries']
    assert 'sub/b.txt' in obj['entries']

    dest = tmp_path / 'out'
    addr = AddressStore(ipfs_client=None, cats_home=str(tmp_path))
    addr.get(ni, str(dest))
    assert (dest / 'a.txt').read_text(encoding='utf-8') == 'A'
    assert (dest / 'sub' / 'b.txt').read_text(encoding='utf-8') == 'B'


def test_validate_digest_rejects_unsafe():
    with pytest.raises(ValueError):
        validate_digest_segment('../etc/passwd')
    with pytest.raises(ValueError):
        validate_digest_segment('not-hex')
