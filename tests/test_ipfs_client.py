"""Unit / smoke tests for the thin Kubo RPC CatsIPFSClient."""
import json
import tempfile
from pathlib import Path

import pytest
import requests

from cats.network.clients.ipfs_client import CatsIPFSClient, KuboRpcClient, connect


def _kubo_up() -> bool:
    try:
        response = requests.post('http://127.0.0.1:5001/api/v0/id', timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


requires_kubo = pytest.mark.skipif(not _kubo_up(), reason='Kubo daemon not reachable on :5001')


@requires_kubo
def test_connect_id():
    """Smoke: connect(validate=True) returns a peer id from live Kubo."""
    client = connect(validate=True)
    peer = client.id()
    assert 'ID' in peer


@requires_kubo
def test_add_str_roundtrip_via_rpc_cat():
    """Smoke: add_str content round-trips through cat / cat_bytes."""
    client = connect()
    cid = client.add_str(json.dumps({'hello': 'cats'}))
    raw = client.cat(cid)
    assert json.loads(raw) == {'hello': 'cats'}
    assert json.loads(client.cat_bytes(cid).decode()) == {'hello': 'cats'}


def _picklable_probe(value):
    return value


@requires_kubo
def test_add_json_and_pyobj():
    """Smoke: add_json and add_pyobj return CIDs."""
    client = connect()
    cid = client.add_json({'a': 1})
    assert isinstance(cid, str) and cid.startswith('Qm')

    cid2 = client.add_pyobj(_picklable_probe)
    assert isinstance(cid2, str) and cid2.startswith('Qm')


@requires_kubo
def test_add_directory_recursive_names_match_put_dir():
    """Smoke: recursive add returns named entries including the root directory CID."""
    client = connect()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / 'plant_mod'
        root.mkdir()
        (root / 'main.tf').write_text('resource "null" "x" {}')
        (root / 'outputs.tf').write_text('output "y" { value = 1 }')
        entries = client.add(str(root), recursive=True)
        assert isinstance(entries, list)
        names = {e['Name'] for e in entries}
        assert 'plant_mod' in names
        assert 'plant_mod/main.tf' in names
        root_entry = [e for e in entries if e['Name'] == 'plant_mod'][-1]
        assert root_entry['Hash'].startswith('Qm')


@requires_kubo
def test_get_file_and_directory(tmp_path):
    """Smoke: get materializes both single-file and directory CIDs to disk."""
    client = connect()
    cid = client.add_str('file-body')
    dest_file = tmp_path / 'out.txt'
    client.get(cid, str(dest_file))
    assert dest_file.read_text() == 'file-body'

    root = tmp_path / 'mod'
    root.mkdir()
    (root / 'a.txt').write_text('a')
    entries = client.add(str(root), recursive=True)
    dir_cid = [e for e in entries if e['Name'] == 'mod'][-1]['Hash']
    dest_dir = tmp_path / 'got_mod'
    client.get(dir_cid, str(dest_dir))
    assert (dest_dir / 'a.txt').read_text() == 'a'


@requires_kubo
def test_ls_and_dag_export(tmp_path):
    """Smoke: ls lists directory links and dag_export writes a non-empty CAR."""
    client = connect()
    root = tmp_path / 'tree'
    root.mkdir()
    (root / 'outputs').mkdir()
    (root / 'outputs' / 'x.csv').write_text('1\n')
    entries = client.add(str(root), recursive=True)
    dir_cid = [e for e in entries if e['Name'] == 'tree'][-1]['Hash']
    links = client.ls(dir_cid)
    names = {link['Name'] for link in links}
    assert 'outputs' in names

    car_path = tmp_path / 'tree.car'
    client.dag_export(dir_cid, str(car_path))
    assert car_path.stat().st_size > 0


@requires_kubo
def test_post_upload_single_file():
    """Smoke: post_upload adds a single file and returns its CID."""
    client = connect()
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as handle:
        handle.write('{"bom": true}')
        path = handle.name
    try:
        cid = client.post_upload(path)
        assert cid.startswith('Qm')
    finally:
        Path(path).unlink(missing_ok=True)


def test_kubo_rpc_error_on_bad_port():
    """CatsIPFSClient.id raises when Kubo RPC is unreachable on a bad port."""
    client = KuboRpcClient(host='127.0.0.1', port=1, timeout=1)
    wrapped = CatsIPFSClient(client)
    with pytest.raises(Exception):
        wrapped.id()


def test_connect_respects_ipfs_api_env(monkeypatch):
    """connect reads IPFS_API_* env, and explicit host/port kwargs override it."""
    monkeypatch.setenv('IPFS_API_HOST', '10.0.0.9')
    monkeypatch.setenv('IPFS_API_PORT', '5009')
    client = connect()
    assert client._client.base_url == 'http://10.0.0.9:5009/api/v0'
    # kwargs override env
    client2 = connect(host='127.0.0.1', port=5001)
    assert client2._client.base_url == 'http://127.0.0.1:5001/api/v0'
