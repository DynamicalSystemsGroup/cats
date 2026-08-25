"""ContentMesh CAS reads/writes + CAT_NODE_* endpoints (no ipfs CLI / legacy CID)."""
import json
import pickle
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cats.network import ContentMesh, _node_init_endpoint
import cats.network.content_mesh as content_mesh_mod
from cats.network.cas import CasHttpStore, put_tree

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


def test_cat_and_cat_obj_via_cas(tmp_path, monkeypatch):
    """cat / catObj read CAS ni: blobs (legacy CID unsupported §6s)."""
    store = CasHttpStore(str(tmp_path))
    text_id = store.put(b'{"k": 1}')
    raw_id = store.put(b'\x80\x04')
    client = ContentMesh(ipfsClient=None, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    assert client.cat(text_id) == '{"k": 1}'
    assert client.catObj(raw_id) == b'\x80\x04'


def test_legacy_cid_cat_fail_closed(tmp_path, monkeypatch):
    """Legacy CID cat/get/getCar fail closed (§6s)."""
    client = ContentMesh(ipfsClient=None, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    with pytest.raises(RuntimeError, match='§6s'):
        client.cat('QmX')
    with pytest.raises(RuntimeError, match='§6s'):
        client.get('QmZ', 'bom.json', output=str(tmp_path))
    with pytest.raises(RuntimeError, match='§6s'):
        client.getCar('QmCar', str(tmp_path / 'x.car'))


def test_link_data_cas_manifest(tmp_path, monkeypatch):
    """linkData resolves outputs via CAS directory manifest."""
    root = tmp_path / 'tree'
    (root / 'outputs').mkdir(parents=True)
    (root / 'outputs' / 'f.txt').write_text('x', encoding='utf-8')
    (root / 'inputs').mkdir()
    (root / 'inputs' / 'g.txt').write_text('y', encoding='utf-8')
    content_id = put_tree(CasHttpStore(str(tmp_path)), str(root))

    client = ContentMesh(ipfsClient=None, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    out_id = client.linkData(content_id)
    assert out_id.startswith('ni:///sha-256;')


def test_fetch_ipfs_object_uses_cas_bytes(tmp_path, monkeypatch):
    """fetch_ipfs_object unpickles objects fetched via CAS catObj."""
    payload = pickle.dumps({'ok': True})
    content_id = CasHttpStore(str(tmp_path)).put(payload)
    client = ContentMesh(ipfsClient=None, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    assert client.fetch_ipfs_object(content_id) == {'ok': True}


def test_create_order_request_default_endpoint_is_init(monkeypatch, tmp_path):
    """create_order_request defaults endpoint to /cat/node/init."""
    from data.input.function.infrafunction import infrafunction_subproc
    from data.input.function.process import (
        egress,
        ingress,
        integration_cache,
        process_0,
    )

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
        from cats.network.cas import sha256_hex, to_ni

        name = Path(path).name
        return to_ni(sha256_hex(name.encode())), name

    client = ContentMesh(ipfsClient=None, CATS_HOME=str(tmp_path))
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
    assert 'structure-root' in structure_payload['root_uri'] or structure_payload[
        'root_uri'
    ].startswith('http')
    assert structure_payload['plant_uri']
    assert structure_payload['infrastructure_uri']

    function_payload = next(
        obj for obj in put_objs
        if isinstance(obj, dict)
        and 'process_source_uri' in obj
        and 'infrafunction_source_uri' in obj
        and 'process_uri' in obj
    )
    assert function_payload['process_source_uri']
    assert function_payload['infrafunction_source_uri']


def test_cat_submit_uses_requests(monkeypatch, tmp_path, capsys):
    """catSubmit POSTs the order_request JSON via requests and returns the BOM."""
    store = CasHttpStore(str(tmp_path))
    order_body = json.dumps(
        {'endpoint': 'http://127.0.0.1:5000/cat/node/init', 'invoice_cid': 'x'}
    ).encode('utf-8')
    order_id = store.put(order_body)
    client = ContentMesh(ipfsClient=None, CATS_HOME=str(tmp_path))
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
        'content_id': order_id,
        'order_uri': f'http://127.0.0.1:5000/ldp/orders/{order_id.split(";")[-1]}',
    })
    assert out['bom'] is True
    assert posts[0][0] == 'http://127.0.0.1:5000/cat/node/init'
    assert 'curl -X POST' in out['POST']
    captured = capsys.readouterr().out
    assert 'POST http://127.0.0.1:5000/cat/node/init' in captured
    assert 'done in' in captured
    assert '200' in captured
