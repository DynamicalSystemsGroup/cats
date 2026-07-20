"""Unit / smoke tests for the thin Kubo RPC CatsIPFSClient."""
import json
import tempfile
from pathlib import Path

import pytest
import requests

from cats.network.ipfs_client import CatsIPFSClient, KuboRpcClient, connect


def _kubo_up() -> bool:
    try:
        response = requests.post('http://127.0.0.1:5001/api/v0/id', timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


requires_kubo = pytest.mark.skipif(not _kubo_up(), reason='Kubo daemon not reachable on :5001')


@requires_kubo
def test_connect_id():
    client = connect(validate=True)
    peer = client.id()
    assert 'ID' in peer


@requires_kubo
def test_add_str_roundtrip_via_cli_cat():
    import subprocess

    client = connect()
    cid = client.add_str(json.dumps({'hello': 'cats'}))
    raw = subprocess.check_output(['ipfs', 'cat', cid], text=True)
    assert json.loads(raw) == {'hello': 'cats'}


def _picklable_probe(value):
    return value


@requires_kubo
def test_add_json_and_pyobj():
    client = connect()
    cid = client.add_json({'a': 1})
    assert isinstance(cid, str) and cid.startswith('Qm')

    cid2 = client.add_pyobj(_picklable_probe)
    assert isinstance(cid2, str) and cid2.startswith('Qm')


@requires_kubo
def test_add_directory_recursive_names_match_cidDir():
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
def test_post_upload_single_file():
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
    client = KuboRpcClient(host='127.0.0.1', port=1, timeout=1)
    wrapped = CatsIPFSClient(client)
    with pytest.raises(Exception):
        wrapped.id()
