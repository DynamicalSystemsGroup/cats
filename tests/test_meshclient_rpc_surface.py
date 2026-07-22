"""MeshClient uses CatsIPFSClient RPC + CAT_NODE_* endpoints (no ipfs CLI)."""
import json
import pickle
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cats.network import MeshClient, _node_init_endpoint
import cats.network as network_mod

REPO_ROOT = Path(__file__).resolve().parents[1]
MESH_INIT = REPO_ROOT / 'cats' / 'network' / '__init__.py'


def test_meshclient_has_no_ipfs_cli_subprocess_strings():
    """MeshClient source must not shell out to the ipfs CLI."""
    text = MESH_INIT.read_text(encoding='utf-8')
    for needle in (
        'ipfs cat',
        'ipfs get',
        'ipfs ls',
        'ipfs dag',
        "['ipfs', 'cat'",
        'subprocess.check_output',
    ):
        assert needle not in text, f'unexpected CLI/subprocess remnant: {needle}'


def test_node_init_endpoint_uses_cat_node_env(monkeypatch):
    """_node_init_endpoint builds the URL from CAT_NODE_HOST / CAT_NODE_PORT."""
    monkeypatch.setenv('CAT_NODE_HOST', '192.168.1.10')
    monkeypatch.setenv('CAT_NODE_PORT', '6000')
    assert _node_init_endpoint() == 'http://192.168.1.10:6000/cat/node/init'


def test_cat_and_cat_obj_delegate_to_ipfs_client(monkeypatch):
    """cat / catObj delegate to CatsIPFSClient.cat / cat_bytes."""
    fake = MagicMock()
    fake.cat.return_value = '{"k": 1}'
    fake.cat_bytes.return_value = b'\x80\x04'
    client = MeshClient(ipfsClient=fake, CATS_HOME=str(REPO_ROOT))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    assert client.cat('QmX') == '{"k": 1}'
    fake.cat.assert_called_once_with('QmX')
    assert client.catObj('QmY') == b'\x80\x04'
    fake.cat_bytes.assert_called_once_with('QmY')


def test_get_and_get_car_delegate(monkeypatch, tmp_path):
    """get / getCar delegate to CatsIPFSClient.get / dag_export."""
    fake = MagicMock()
    client = MeshClient(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    assert client.get('QmZ', 'bom.json', output=str(tmp_path)) == 'bom.json'
    fake.get.assert_called_once_with('QmZ', str(tmp_path / 'bom.json'))

    client.getCar('QmCar', str(tmp_path / 'x.car'))
    fake.dag_export.assert_called_once_with('QmCar', str(tmp_path / 'x.car'))


def test_link_data_uses_ls_links(monkeypatch):
    """linkData resolves the outputs subdirectory via ls links."""
    fake = MagicMock()
    fake.ls.return_value = [
        {'Name': 'inputs', 'Hash': 'QmIn'},
        {'Name': 'outputs', 'Hash': 'QmOut'},
    ]
    client = MeshClient(ipfsClient=fake, CATS_HOME=str(REPO_ROOT))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    assert client.linkData('QmRoot') == 'QmOut'
    assert client.linkData('QmRoot', subdir=' - outputs/') == 'QmOut'


def test_fetch_ipfs_object_uses_bytes(monkeypatch):
    """fetch_ipfs_object unpickles objects fetched via cat_bytes."""
    payload = pickle.dumps({'ok': True})
    fake = MagicMock()
    fake.cat_bytes.return_value = payload
    client = MeshClient(ipfsClient=fake, CATS_HOME=str(REPO_ROOT))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    assert client.fetch_ipfs_object('QmP') == {'ok': True}


def test_create_order_request_default_endpoint_is_init(monkeypatch, tmp_path):
    """create_order_request defaults endpoint to /cat/node/init."""
    fake = MagicMock()
    # Minimal stubs so create_order_request can run far enough to set endpoint.
    fake.add.return_value = [{'Name': 'data', 'Hash': 'QmData'}]
    fake.add_str.side_effect = lambda s: f'cid-{hash(s) & 0xFFFF:x}'
    fake.add_pyobj.side_effect = lambda *_a, **_k: 'QmPy'

    structure = tmp_path / 'structure'
    plant = structure / 'plant'
    infra = structure / 'infrastructure'
    plant.mkdir(parents=True)
    infra.mkdir(parents=True)
    (structure / 'main.tf').write_text('module "plant" { source = "./plant" }\n')
    (structure / 'outputs.tf').write_text('output "x" { value = 1 }\n')
    (structure / '.terraform.lock.hcl').write_text('# lock\n')
    (plant / 'x.tf').write_text('x')
    (infra / 'y.tf').write_text('y')
    process_pkg = tmp_path / 'function' / 'process'
    infra_pkg = tmp_path / 'function' / 'infrafunction'
    process_pkg.mkdir(parents=True)
    infra_pkg.mkdir(parents=True)
    (process_pkg / '__init__.py').write_text('# process\n')
    (infra_pkg / '__init__.py').write_text('# infrafunction\n')
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'f.csv').write_text('a\n')

    def _cid_dir(path):
        name = Path(path).name
        return f'Qm{name}', name

    client = MeshClient(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cidDir', _cid_dir)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')

    # create_order_request still calls cidDir on real paths via self.cidDir — stubbed.
    # Also needs add_str for structure/function/invoice/order JSON.
    order_req = client.create_order_request(
        ingress_subproc=lambda: None,
        integrated_subproc=lambda: None,
        egress_subproc=lambda: None,
        integration_cache_subproc=lambda: None,
        infrafunction_subproc=lambda: None,
        data_dirpath=str(data),
        structure_filepath=str(structure),
    )
    order = json.loads(
        # last add_str for order body — recover from fake call args that look like order JSON
        next(
            args[0]
            for args, _ in reversed(fake.add_str.call_args_list)
            if '"endpoint"' in args[0]
        )
    )
    assert order['endpoint'] == 'http://127.0.0.1:5000/cat/node/init'
    assert order_req['order_cid']

    structure_payload = json.loads(
        next(
            args[0]
            for args, _ in fake.add_str.call_args_list
            if '"root_cid"' in args[0]
            and '"plant_cid"' in args[0]
            and '"infrastructure_cid"' in args[0]
        )
    )
    assert structure_payload['root_cid'] == 'Qmstructure-root'
    assert structure_payload['plant_cid'] == 'Qmplant'
    assert structure_payload['infrastructure_cid'] == 'Qminfrastructure'

    function_payload = json.loads(
        next(
            args[0]
            for args, _ in fake.add_str.call_args_list
            if '"process_source_cid"' in args[0]
            and '"infrafunction_source_cid"' in args[0]
            and '"process_cid"' in args[0]
        )
    )
    assert function_payload['process_source_cid'] == 'Qmprocess'
    assert function_payload['infrafunction_source_cid'] == 'Qminfrafunction'


def test_cat_submit_uses_requests(monkeypatch, capsys):
    """catSubmit POSTs the order_request JSON via requests and returns the BOM."""
    fake = MagicMock()
    fake.cat.return_value = json.dumps(
        {'endpoint': 'http://127.0.0.1:5000/cat/node/init', 'invoice_cid': 'QmI'}
    )
    client = MeshClient(ipfsClient=fake, CATS_HOME=str(REPO_ROOT))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    class _Resp:
        status_code = 200
        content = b'{"bom": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {'bom': True}

    posts = []

    def _post(url, json=None, timeout=None):
        posts.append((url, json))
        return _Resp()

    monkeypatch.setattr(network_mod.requests, 'post', _post)
    out = client.catSubmit({'order_cid': 'QmOrder'})
    assert out['bom'] is True
    assert posts == [
        ('http://127.0.0.1:5000/cat/node/init', {'order_cid': 'QmOrder'})
    ]
    assert 'curl -X POST' in out['POST']
    captured = capsys.readouterr().out
    assert 'POST http://127.0.0.1:5000/cat/node/init' in captured
    assert 'done in' in captured
    assert '200' in captured
