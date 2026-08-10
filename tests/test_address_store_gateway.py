"""Phase 2a AddressStore: gateway fetch + pure UnixFS verify + RPC fallback."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cats.network.address_store import (
    AddressStore,
    CidIntegrityError,
    GatewayError,
    IpfsHttpGateway,
    compute_unixfs_file_cid,
    verify_bytes_match_cid,
)
from cats.network.address_store.cid_verify import cids_equal, normalize_cid
from cats.network.address_store.unixfs_cid import local_cids_equal
import cats.network.address_store.gateway as gateway_mod


def test_normalize_and_cids_equal_string():
    assert normalize_cid('  QmX  ') == 'QmX'
    assert cids_equal('QmX', 'QmX')
    assert not cids_equal('QmX', 'QmY')


def test_local_cids_equal_v0_v1():
    data = b'hello world\n'
    v0 = compute_unixfs_file_cid(data, version=0)
    v1 = compute_unixfs_file_cid(data, version=1)
    assert v0.startswith('Qm')
    assert v1.startswith('bafy')
    assert local_cids_equal(v0, v1)
    assert cids_equal(v0, v1)


def test_compute_unixfs_golden_vectors():
    # Famous IPFS "hello world\\n" CIDv0; empty file CIDv0.
    assert (
        compute_unixfs_file_cid(b'hello world\n')
        == 'QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o'
    )
    assert (
        compute_unixfs_file_cid(b'')
        == 'QmbFMke1KXqnYyBBWxB74N4c5SBnJMVAiMNRcGu6x1AwQH'
    )
    assert compute_unixfs_file_cid(b'hello').startswith('Qm')
    assert compute_unixfs_file_cid(b'{"a": 1}').startswith('Qm')


def test_verify_pure_ok_no_oracle():
    data = b'payload-bytes'
    cid = compute_unixfs_file_cid(data)
    client = MagicMock()
    verify_bytes_match_cid(client, cid, data)
    client.only_hash_bytes.assert_not_called()


def test_verify_pure_ok_without_client():
    data = b'no-client'
    cid = compute_unixfs_file_cid(data)
    verify_bytes_match_cid(None, cid, data)


def test_verify_tamper_raises():
    cid = compute_unixfs_file_cid(b'good')
    client = MagicMock()
    client.only_hash_bytes.return_value = 'QmOther'
    client.cid_format.side_effect = RuntimeError('no format')
    with pytest.raises(CidIntegrityError) as exc:
        verify_bytes_match_cid(client, cid, b'tampered')
    assert exc.value.cid == cid


def test_verify_exotic_layout_falls_back_to_only_hash():
    """Pure default-layout CID ≠ expected → Kubo only-hash may still accept."""
    data = b'y' * 64
    client = MagicMock()
    client.only_hash_bytes.return_value = 'QmExoticLayoutCid'
    client.cid_format.side_effect = RuntimeError('no format')
    verify_bytes_match_cid(client, 'QmExoticLayoutCid', data)
    client.only_hash_bytes.assert_called_once_with(data)


def test_cids_equal_via_cid_format():
    client = MagicMock()
    client.cid_format.side_effect = lambda cid, version=1: 'bafySame'
    # Non-parseable fake CIDs still equal via Kubo format helper.
    assert cids_equal('not-a-cid-a', 'not-a-cid-b', client)
    assert client.cid_format.call_count == 2


def test_gateway_cat_bytes_success(monkeypatch):
    class _Resp:
        status_code = 200
        content = b'hello'
        text = ''
        headers = {}

    sessions = []

    class _Session:
        def get(self, url, timeout=None, headers=None, stream=False):
            sessions.append((url, timeout, headers, stream))
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
        headers = {}

    class _Session:
        def get(self, url, timeout=None, headers=None, stream=False):
            return _Resp()

    monkeypatch.setattr(gateway_mod.requests, 'Session', _Session)
    gw = IpfsHttpGateway('http://gw.example')
    with pytest.raises(GatewayError) as exc:
        gw.cat_bytes('QmMissing')
    assert exc.value.status_code == 404


def test_gateway_dag_export_car(monkeypatch, tmp_path):
    class _Resp:
        status_code = 200
        headers = {'Content-Type': 'application/vnd.ipld.car'}

        def iter_content(self, chunk_size=1024):
            yield b'CAR'
            yield b'data'

    sessions = []

    class _Session:
        def get(self, url, timeout=None, headers=None, stream=False):
            sessions.append((url, headers, stream))
            return _Resp()

    monkeypatch.setattr(gateway_mod.requests, 'Session', _Session)
    gw = IpfsHttpGateway('http://127.0.0.1:8080')
    out = tmp_path / 'x.car'
    gw.dag_export('QmABC', str(out))
    assert out.read_bytes() == b'CARdata'
    assert 'format=car' in sessions[0][0]
    assert sessions[0][1]['Accept'] == 'application/vnd.ipld.car'
    assert sessions[0][2] is True


def test_gateway_get_file_writes(monkeypatch, tmp_path):
    class _Resp:
        status_code = 200
        content = b'file-body'
        text = ''
        headers = {'Content-Type': 'application/octet-stream'}

    class _Session:
        def get(self, url, timeout=None, headers=None, stream=False):
            return _Resp()

    monkeypatch.setattr(gateway_mod.requests, 'Session', _Session)
    gw = IpfsHttpGateway('http://127.0.0.1:8080')
    dest = tmp_path / 'out.bin'
    assert gw.get_file('QmFile', str(dest)) == str(dest)
    assert dest.read_bytes() == b'file-body'


def test_gateway_get_file_rejects_html_directory(monkeypatch, tmp_path):
    class _Resp:
        status_code = 200
        content = b'<html><body>Index</body></html>'
        text = ''
        headers = {'Content-Type': 'text/html; charset=utf-8'}

    class _Session:
        def get(self, url, timeout=None, headers=None, stream=False):
            return _Resp()

    monkeypatch.setattr(gateway_mod.requests, 'Session', _Session)
    gw = IpfsHttpGateway('http://127.0.0.1:8080')
    with pytest.raises(GatewayError):
        gw.get_file('QmDir', str(tmp_path / 'd'))


def test_address_store_rpc_when_gateway_unset(monkeypatch):
    monkeypatch.delenv('IPFS_GATEWAY_URL', raising=False)
    monkeypatch.delenv('CATS_CID_VERIFY', raising=False)
    ipfs = MagicMock()
    ipfs.cat_bytes.return_value = b'from-rpc'
    store = AddressStore(ipfs)
    assert store.gateway is None
    assert store.cat_bytes('QmZ') == b'from-rpc'
    ipfs.only_hash_bytes.assert_not_called()


def test_address_store_gateway_first_verifies_without_oracle(monkeypatch):
    monkeypatch.setenv('IPFS_GATEWAY_URL', 'http://127.0.0.1:8080')
    monkeypatch.delenv('CATS_CID_VERIFY', raising=False)
    data = b'gateway-payload'
    cid = compute_unixfs_file_cid(data)
    ipfs = MagicMock()
    store = AddressStore(ipfs)
    store.gateway = MagicMock()
    store.gateway.cat_bytes.return_value = data
    assert store.cat_bytes(cid) == data
    store.gateway.cat_bytes.assert_called_once_with(cid)
    ipfs.cat_bytes.assert_not_called()
    ipfs.only_hash_bytes.assert_not_called()


def test_address_store_gateway_tamper_raises(monkeypatch):
    monkeypatch.setenv('IPFS_GATEWAY_URL', 'http://127.0.0.1:8080')
    cid = compute_unixfs_file_cid(b'good')
    ipfs = MagicMock()
    ipfs.only_hash_bytes.return_value = 'QmEvil'
    ipfs.cid_format.side_effect = RuntimeError('nope')
    store = AddressStore(ipfs)
    store.gateway = MagicMock()
    store.gateway.cat_bytes.return_value = b'tampered'
    with pytest.raises(CidIntegrityError):
        store.cat_bytes(cid)


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
    data = b'data'
    cid = compute_unixfs_file_cid(data)
    ipfs = MagicMock()
    ipfs.cat_bytes.return_value = data
    store = AddressStore(ipfs)
    assert store.cat_bytes(cid) == data
    ipfs.only_hash_bytes.assert_not_called()


def test_address_store_cat_and_cat_obj(monkeypatch):
    monkeypatch.delenv('IPFS_GATEWAY_URL', raising=False)
    monkeypatch.delenv('CATS_CID_VERIFY', raising=False)
    ipfs = MagicMock()
    ipfs.cat_bytes.return_value = b'{"a": 1}'
    store = AddressStore(ipfs)
    assert store.cat('QmJ') == '{"a": 1}'
    assert store.cat_obj('QmJ') == {'a': 1}


def test_address_store_dag_export_gateway_first(monkeypatch, tmp_path):
    monkeypatch.setenv('IPFS_GATEWAY_URL', 'http://127.0.0.1:8080')
    ipfs = MagicMock()
    store = AddressStore(ipfs)
    store.gateway = MagicMock()
    out = tmp_path / 'b.car'
    store.dag_export('QmC', str(out))
    store.gateway.dag_export.assert_called_once_with('QmC', str(out))
    ipfs.dag_export.assert_not_called()


def test_address_store_dag_export_rpc_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv('IPFS_GATEWAY_URL', 'http://127.0.0.1:8080')
    ipfs = MagicMock()
    store = AddressStore(ipfs)
    store.gateway = MagicMock()
    store.gateway.dag_export.side_effect = GatewayError('u', 503, 'down')
    out = str(tmp_path / 'b.car')
    store.dag_export('QmC', out)
    ipfs.dag_export.assert_called_once_with('QmC', out)


def test_address_store_get_file_via_gateway(monkeypatch, tmp_path):
    monkeypatch.setenv('IPFS_GATEWAY_URL', 'http://127.0.0.1:8080')
    ipfs = MagicMock()
    store = AddressStore(ipfs)
    store.gateway = MagicMock()
    dest = str(tmp_path / 'f.bin')
    store.gateway.get_file.return_value = dest
    assert store.get('QmF', dest) == dest
    store.gateway.get_file.assert_called_once_with('QmF', dest)
    ipfs.get.assert_not_called()


def test_address_store_get_dir_falls_back_to_rpc(monkeypatch, tmp_path):
    """When file GET and CAR extract both fail, use Kubo RPC get."""
    monkeypatch.setenv('IPFS_GATEWAY_URL', 'http://127.0.0.1:8080')
    ipfs = MagicMock()
    dest = str(tmp_path / 'dir')
    ipfs.get.return_value = dest
    store = AddressStore(ipfs)
    store.gateway = MagicMock()
    store.gateway.get_file.side_effect = GatewayError(
        'http://gw/ipfs/QmD', 200, 'directory or HTML listing'
    )
    store.gateway.dag_export.side_effect = GatewayError('u', 503, 'no car')
    assert store.get('QmD', dest) == dest
    ipfs.get.assert_called_once_with('QmD', dest)
