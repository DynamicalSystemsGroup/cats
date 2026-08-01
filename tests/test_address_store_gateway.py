"""Phase 2a AddressStore: gateway fetch + only-hash verify + RPC fallback."""
from unittest.mock import MagicMock

import pytest

from cats.network.address_store import (
    AddressStore,
    CidIntegrityError,
    GatewayError,
    IpfsHttpGateway,
    verify_bytes_match_cid,
)
from cats.network.address_store.cid_verify import cids_equal, normalize_cid
import cats.network.address_store.gateway as gateway_mod


def test_normalize_and_cids_equal_string():
    assert normalize_cid('  QmX  ') == 'QmX'
    assert cids_equal('QmX', 'QmX')
    assert not cids_equal('QmX', 'QmY')


def test_cids_equal_via_cid_format():
    client = MagicMock()
    client.cid_format.side_effect = lambda cid, version=1: 'bafySame'
    assert cids_equal('QmOld', 'bafyNew', client)
    assert client.cid_format.call_count == 2


def test_verify_bytes_match_cid_ok():
    client = MagicMock()
    client.only_hash_bytes.return_value = 'QmExact'
    verify_bytes_match_cid(client, 'QmExact', b'payload')
    client.only_hash_bytes.assert_called_once_with(b'payload')


def test_verify_bytes_match_cid_tamper():
    client = MagicMock()
    client.only_hash_bytes.return_value = 'QmOther'
    client.cid_format.side_effect = RuntimeError('no format')
    with pytest.raises(CidIntegrityError) as exc:
        verify_bytes_match_cid(client, 'QmExact', b'tampered')
    assert exc.value.cid == 'QmExact'
    assert exc.value.computed == 'QmOther'


def test_gateway_cat_bytes_success(monkeypatch):
    class _Resp:
        status_code = 200
        content = b'hello'
        text = ''

    sessions = []

    class _Session:
        def get(self, url, timeout=None):
            sessions.append((url, timeout))
            return _Resp()

    monkeypatch.setattr(gateway_mod.requests, 'Session', _Session)
    gw = IpfsHttpGateway('http://127.0.0.1:8080/', timeout=5.0)
    assert gw.cat_bytes('QmABC') == b'hello'
    assert sessions[0][0] == 'http://127.0.0.1:8080/ipfs/QmABC'


def test_gateway_rejects_path_traversal():
    gw = IpfsHttpGateway('http://127.0.0.1:8080')
    with pytest.raises(GatewayError):
        gw.cat_bytes('../etc/passwd')


def test_gateway_http_error(monkeypatch):
    class _Resp:
        status_code = 404
        content = b''
        text = 'not found'

    class _Session:
        def get(self, url, timeout=None):
            return _Resp()

    monkeypatch.setattr(gateway_mod.requests, 'Session', _Session)
    gw = IpfsHttpGateway('http://gw.example')
    with pytest.raises(GatewayError) as exc:
        gw.cat_bytes('QmMissing')
    assert exc.value.status_code == 404


def test_address_store_rpc_when_gateway_unset(monkeypatch):
    monkeypatch.delenv('IPFS_GATEWAY_URL', raising=False)
    monkeypatch.delenv('CATS_CID_VERIFY', raising=False)
    ipfs = MagicMock()
    ipfs.cat_bytes.return_value = b'from-rpc'
    store = AddressStore(ipfs)
    assert store.gateway is None
    assert store.cat_bytes('QmZ') == b'from-rpc'
    ipfs.only_hash_bytes.assert_not_called()


def test_address_store_gateway_first_verifies(monkeypatch):
    monkeypatch.setenv('IPFS_GATEWAY_URL', 'http://127.0.0.1:8080')
    monkeypatch.delenv('CATS_CID_VERIFY', raising=False)
    ipfs = MagicMock()
    ipfs.only_hash_bytes.return_value = 'QmGood'
    store = AddressStore(ipfs)
    store.gateway = MagicMock()
    store.gateway.cat_bytes.return_value = b'payload'
    assert store.cat_bytes('QmGood') == b'payload'
    store.gateway.cat_bytes.assert_called_once_with('QmGood')
    ipfs.cat_bytes.assert_not_called()
    ipfs.only_hash_bytes.assert_called_once_with(b'payload')


def test_address_store_gateway_tamper_raises(monkeypatch):
    monkeypatch.setenv('IPFS_GATEWAY_URL', 'http://127.0.0.1:8080')
    ipfs = MagicMock()
    ipfs.only_hash_bytes.return_value = 'QmEvil'
    ipfs.cid_format.side_effect = RuntimeError('nope')
    store = AddressStore(ipfs)
    store.gateway = MagicMock()
    store.gateway.cat_bytes.return_value = b'tampered'
    with pytest.raises(CidIntegrityError):
        store.cat_bytes('QmGood')


def test_address_store_gateway_fallback_to_rpc(monkeypatch):
    monkeypatch.setenv('IPFS_GATEWAY_URL', 'http://127.0.0.1:8080')
    monkeypatch.delenv('CATS_CID_VERIFY', raising=False)
    ipfs = MagicMock()
    ipfs.cat_bytes.return_value = b'from-rpc'
    store = AddressStore(ipfs)
    store.gateway = MagicMock()
    store.gateway.cat_bytes.side_effect = GatewayError(
        'http://127.0.0.1:8080/ipfs/QmZ', 503, 'down'
    )
    assert store.cat_bytes('QmZ') == b'from-rpc'
    ipfs.only_hash_bytes.assert_not_called()


def test_address_store_rpc_verify_when_flag(monkeypatch):
    monkeypatch.delenv('IPFS_GATEWAY_URL', raising=False)
    monkeypatch.setenv('CATS_CID_VERIFY', '1')
    ipfs = MagicMock()
    ipfs.cat_bytes.return_value = b'data'
    ipfs.only_hash_bytes.return_value = 'QmV'
    store = AddressStore(ipfs)
    assert store.cat_bytes('QmV') == b'data'
    ipfs.only_hash_bytes.assert_called_once_with(b'data')


def test_address_store_cat_and_cat_obj(monkeypatch):
    monkeypatch.delenv('IPFS_GATEWAY_URL', raising=False)
    monkeypatch.delenv('CATS_CID_VERIFY', raising=False)
    ipfs = MagicMock()
    ipfs.cat_bytes.return_value = b'{"a": 1}'
    store = AddressStore(ipfs)
    assert store.cat('QmJ') == '{"a": 1}'
    assert store.cat_obj('QmJ') == {'a': 1}
