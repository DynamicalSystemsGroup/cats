"""Phase 2a Node-hosted LDP BOM control plane."""
from unittest.mock import MagicMock
import json

import pytest
from flask import Flask

from cats.network.feedback import build_execution_bom, sign_execution_bom
from cats.network.identity import node_did
from cats.network.ldp import (
    BomLdpStore,
    LdpEnvelopeError,
    bom_ldp_path,
    bom_ldp_uri,
    container_link_header,
    fetch_bom_envelope,
    register_ldp_routes,
    resource_link_header,
)
from cats.network.ldp.headers import LDP_BASIC_CONTAINER, LDP_RESOURCE


def _signed_bom(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    return sign_execution_bom(
        build_execution_bom(
            log_cid='QmLog',
            invoice_cid='QmInv',
            node_did=did,
        ),
        cats_home=str(tmp_path),
    )


def test_bom_ldp_uri_and_path(monkeypatch):
    monkeypatch.setenv('CAT_NODE_HOST', '10.0.0.2')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    assert bom_ldp_path('QmBom') == '/ldp/boms/QmBom'
    assert bom_ldp_uri('QmBom') == 'http://10.0.0.2:5002/ldp/boms/QmBom'


def test_link_headers_mark_ldp_types():
    assert LDP_RESOURCE in resource_link_header()
    assert LDP_BASIC_CONTAINER in container_link_header()


def test_bom_ldp_store_put_get_list(tmp_path, monkeypatch):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    bom = _signed_bom(monkeypatch, tmp_path)
    store = BomLdpStore(str(tmp_path))
    store.put('QmBom1', bom)
    assert store.get('QmBom1')['invoice_cid'] == 'QmInv'
    assert store.list() == ['QmBom1']
    store.put('QmBom2', {**bom, 'log_cid': 'QmLog2'})
    assert store.list()[0] in ('QmBom1', 'QmBom2')
    assert set(store.list()) == {'QmBom1', 'QmBom2'}


def test_bom_ldp_store_rejects_path_traversal(tmp_path):
    store = BomLdpStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.put('../etc/passwd', {'x': 1})


def test_container_document(monkeypatch, tmp_path):
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    bom = _signed_bom(monkeypatch, tmp_path)
    store = BomLdpStore(str(tmp_path))
    store.put('QmC', bom)
    doc = store.container_document()
    assert 'ldp:BasicContainer' in doc['@type']
    assert doc['contains'] == ['http://127.0.0.1:5002/ldp/boms/QmC']


def test_fetch_bom_envelope_verifies(monkeypatch, tmp_path):
    bom = _signed_bom(monkeypatch, tmp_path)

    class _Resp:
        status_code = 200
        text = ''

        def json(self):
            return bom

    class _Session:
        def get(self, url, timeout=None, headers=None):
            assert url.endswith('/ldp/boms/QmX')
            return _Resp()

    out = fetch_bom_envelope(
        'http://127.0.0.1:5002/ldp/boms/QmX',
        session=_Session(),
    )
    assert out['invoice_cid'] == 'QmInv'


def test_fetch_bom_envelope_tamper_fails(monkeypatch, tmp_path):
    bom = _signed_bom(monkeypatch, tmp_path)
    bom['invoice_cid'] = 'QmEvil'

    class _Resp:
        status_code = 200
        text = ''

        def json(self):
            return bom

    class _Session:
        def get(self, url, timeout=None, headers=None):
            return _Resp()

    with pytest.raises(LdpEnvelopeError, match='Data Integrity'):
        fetch_bom_envelope('http://example/ldp/boms/QmX', session=_Session())


def test_flask_ldp_routes(monkeypatch, tmp_path):
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    bom = _signed_bom(monkeypatch, tmp_path)
    BomLdpStore(str(tmp_path)).put('QmFlask', bom)

    app = Flask(__name__)
    register_ldp_routes(app, cats_home=str(tmp_path))
    client = app.test_client()

    container = client.get('/ldp/boms/')
    assert container.status_code == 200
    assert LDP_BASIC_CONTAINER in container.headers.get('Link', '')
    assert 'application/ld+json' in container.headers.get('Content-Type', '')
    body = container.get_json()
    assert any('QmFlask' in u for u in body['contains'])

    resource = client.get('/ldp/boms/QmFlask')
    assert resource.status_code == 200
    assert LDP_RESOURCE in resource.headers.get('Link', '')
    assert resource.get_json()['invoice_cid'] == 'QmInv'

    missing = client.get('/ldp/boms/QmMissing')
    assert missing.status_code == 404

    put = client.put('/ldp/boms/QmFlask', json=bom)
    assert put.status_code == 405


def test_runtime_execute_publishes_ldp(monkeypatch, tmp_path):
    """Runtime.execute stores BOM in BomLdpStore and returns bom_ldp_uri."""
    from cats.runtime import Runtime
    from cats.network.registry import BomRegistry

    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    node_did(cats_home=str(tmp_path))

    mesh = MagicMock()
    mesh.ipfsClient.add_str.return_value = 'QmRuntimeBom'
    mesh.cat.side_effect = lambda cid: {
        'QmInvoice': json.dumps({
            'order_cid': 'QmOrder',
            'data_cid': 'QmDataOut',
        }),
        'QmOrder': json.dumps({
            'function_cid': 'QmFn',
            'structure_cid': 'QmStruct',
            'invoice_cid': 'QmInvIn',
        }),
        'QmInvIn': json.dumps({'data_cid': 'QmDataIn'}),
    }[cid]
    # Runtime.__init__ assigns paths onto contentMesh
    runtime = Runtime(contentMesh=mesh, CATS_HOME=str(tmp_path))

    factory = MagicMock()
    executor = MagicMock()
    executor.execute.return_value = (
        {'log_cid': 'QmLog'},
        'QmInvoice',
    )
    factory.produce.return_value = executor

    response = runtime.execute(factory, {'order_cid': 'QmOrder'})
    assert response['bom_cid'] == 'QmRuntimeBom'
    assert response['bom_ldp_uri'] == 'http://127.0.0.1:5002/ldp/boms/QmRuntimeBom'
    assert response['bom_solid_uri'] is None
    stored = BomLdpStore(str(tmp_path)).get('QmRuntimeBom')
    assert stored is not None
    assert stored['invoice_cid'] == 'QmInvoice'
    assert 'proof' in stored
    record = BomRegistry(str(tmp_path)).get('QmRuntimeBom')
    assert record is not None
    assert record['order_cid'] == 'QmOrder'
    assert record['data_cid'] == 'QmDataOut'
    assert BomRegistry(str(tmp_path)).lookup_bom('QmDataOut') == ['QmRuntimeBom']
