"""ContentMesh uses CatsIPFSClient RPC + CAT_NODE_* endpoints (no ipfs CLI)."""
import json
import pickle
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cats.network import ContentMesh, _node_init_endpoint
import cats.network.content_mesh as content_mesh_mod

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_MESH_SRC = REPO_ROOT / 'cats' / 'network' / 'content_mesh.py'
ORDER_SRC = REPO_ROOT / 'cats' / 'network' / 'order.py'


def test_meshclient_has_no_ipfs_cli_subprocess_strings():
    """ContentMesh / OrderOps source must not shell out to the ipfs CLI."""
    text = CONTENT_MESH_SRC.read_text(encoding='utf-8') + ORDER_SRC.read_text(
        encoding='utf-8'
    )
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


def test_cat_and_cat_obj_delegate_via_address_store(monkeypatch):
    """cat / catObj read via AddressStore (RPC fallback when gateway unset)."""
    monkeypatch.delenv('IPFS_GATEWAY_URL', raising=False)
    monkeypatch.delenv('CATS_CID_VERIFY', raising=False)
    fake = MagicMock()
    fake.cat_bytes.side_effect = lambda cid: (
        b'{"k": 1}' if cid == 'QmX' else b'\x80\x04'
    )
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(REPO_ROOT))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    assert client.cat('QmX') == '{"k": 1}'
    assert client.catObj('QmY') == b'\x80\x04'
    assert fake.cat_bytes.call_count == 2


def test_get_and_get_car_delegate(monkeypatch, tmp_path):
    """get / getCar delegate to CatsIPFSClient.get / dag_export."""
    fake = MagicMock()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
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
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(REPO_ROOT))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    assert client.linkData('QmRoot') == 'QmOut'
    assert client.linkData('QmRoot', subdir=' - outputs/') == 'QmOut'


def test_fetch_ipfs_object_uses_bytes(monkeypatch):
    """fetch_ipfs_object unpickles objects fetched via cat_bytes."""
    payload = pickle.dumps({'ok': True})
    fake = MagicMock()
    fake.cat_bytes.return_value = payload
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(REPO_ROOT))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    assert client.fetch_ipfs_object('QmP') == {'ok': True}


def test_create_order_request_default_endpoint_is_init(monkeypatch, tmp_path):
    """create_order_request defaults endpoint to /cat/node/init."""
    from data.input.function.infrafunction import infrafunction_subproc
    from data.input.function.process import (
        egress,
        ingress,
        integration_cache,
        process_0,
    )

    fake = MagicMock()

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

    def _put_dir(path):
        name = Path(path).name
        return f'Qm{name}', name

    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'put_dir', _put_dir)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')
    put_objs = []
    real_put = client.put_json

    def _spy_put(obj, **kwargs):
        put_objs.append(obj)
        return real_put(obj, **kwargs)

    monkeypatch.setattr(client, 'put_json', _spy_put)

    # Stock callables mint named-bind leaves on CAS (no Kubo add_str).
    order_req = client.create_order_request(
        ingress_subproc=ingress,
        integrated_subproc=process_0,
        egress_subproc=egress,
        integration_cache_subproc=integration_cache,
        infrafunction_subproc=infrafunction_subproc,
        data_dirpath=str(data),
        structure_filepath=str(structure),
    )
    order = next(
        obj for obj in reversed(put_objs)
        if isinstance(obj, dict) and 'endpoint' in obj
    )
    assert order['endpoint'] == 'http://127.0.0.1:5000/cat/node/init'
    assert order_req['content_id']
    assert 'order_cid' not in order_req
    assert 'invoice_cid' not in order_req
    assert 'order_uri' in order_req
    assert 'invoice_uri' in order_req

    structure_payload = next(
        obj for obj in put_objs
        if isinstance(obj, dict)
        and 'root_uri' in obj
        and 'plant_uri' in obj
        and 'infrastructure_uri' in obj
    )
    assert structure_payload['root_uri'] == 'Qmstructure-root'
    assert structure_payload['plant_uri'] == 'Qmplant'
    assert structure_payload['infrastructure_uri'] == 'Qminfrastructure'

    function_payload = next(
        obj for obj in put_objs
        if isinstance(obj, dict)
        and 'process_source_uri' in obj
        and 'infrafunction_source_uri' in obj
        and 'process_uri' in obj
    )
    assert function_payload['process_source_uri'] == 'Qmprocess'
    assert function_payload['infrafunction_source_uri'] == 'Qminfrafunction'


def test_cat_submit_uses_requests(monkeypatch, capsys):
    """catSubmit POSTs the order_request JSON via requests and returns the BOM."""
    monkeypatch.delenv('IPFS_GATEWAY_URL', raising=False)
    monkeypatch.delenv('CATS_CID_VERIFY', raising=False)
    fake = MagicMock()
    fake.cat_bytes.return_value = json.dumps(
        {'endpoint': 'http://127.0.0.1:5000/cat/node/init', 'invoice_cid': 'QmI'}
    ).encode('utf-8')
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(REPO_ROOT))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    class _Resp:
        status_code = 200
        ok = True
        content = b'{"bom": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {'bom': True}

    posts = []

    def _post(url, json=None, timeout=None):
        posts.append((url, json))
        return _Resp()

    monkeypatch.setattr(content_mesh_mod.requests, 'post', _post)
    out = client.catSubmit({
        'content_id': 'QmOrder',
        'order_uri': 'http://127.0.0.1:5000/ldp/orders/QmOrder',
    })
    assert out['bom'] is True
    assert posts == [
        (
            'http://127.0.0.1:5000/cat/node/init',
            {'order_uri': 'http://127.0.0.1:5000/ldp/orders/QmOrder'},
        )
    ]
    assert 'curl -X POST' in out['POST']
    captured = capsys.readouterr().out
    assert 'POST http://127.0.0.1:5000/cat/node/init' in captured
    assert 'done in' in captured
    assert '200' in captured
