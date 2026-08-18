"""Phase 2a Solid pod + WAC + LDN control plane."""
from unittest.mock import MagicMock, patch
import json

import pytest

from cats.network.feedback import build_execution_bom, sign_execution_bom
from cats.network.identity import node_did
from cats.network.identity.webid import (
    build_webid_document,
    webid_uri,
    write_webid_document,
)
from cats.network.ldp import (
    BomLdpStore,
    SolidBomPublisher,
    SolidPublishError,
    announce_bom,
    bom_solid_uri,
    build_bom_announcement,
    ensure_solid_bom_acl,
    fetch_bom_envelope,
    solid_configured,
)
from cats.network.ldp.ldn import ldn_inbox_urls
from cats.network.ldp.wac import build_bom_container_acl


def _mesh_cat_for_runtime_invoice(cid):
    """AddressStore-shaped cats for Runtime.execute → build_record."""
    return {
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


def test_solid_configured(monkeypatch):
    monkeypatch.delenv('SOLID_POD_BASE_URL', raising=False)
    assert solid_configured() is False
    monkeypatch.setenv('SOLID_POD_BASE_URL', 'https://pod.example/user/')
    assert solid_configured() is True


def test_bom_solid_uri(monkeypatch):
    monkeypatch.setenv('SOLID_POD_BASE_URL', 'https://pod.example/user')
    monkeypatch.delenv('SOLID_BOMS_PATH', raising=False)
    assert bom_solid_uri('QmBom') == 'https://pod.example/user/boms/QmBom'


def test_solid_publisher_rejects_path_traversal(monkeypatch):
    monkeypatch.setenv('SOLID_POD_BASE_URL', 'https://pod.example/user')
    monkeypatch.setenv('SOLID_CLIENT_ACCESS_TOKEN', 'tok')
    with pytest.raises(ValueError):
        SolidBomPublisher().publish('../etc/passwd', {'x': 1})


def test_solid_publisher_put_path_and_auth(monkeypatch, tmp_path):
    monkeypatch.setenv('SOLID_POD_BASE_URL', 'https://pod.example/user/')
    monkeypatch.setenv('SOLID_CLIENT_ACCESS_TOKEN', 'secret-token')
    bom = _signed_bom(monkeypatch, tmp_path)

    class _Resp:
        status_code = 201
        text = ''

    class _Session:
        def __init__(self):
            self.calls = []

        def put(self, url, data=None, headers=None, timeout=None):
            self.calls.append((url, data, headers, timeout))
            return _Resp()

    session = _Session()
    uri = SolidBomPublisher(session=session).publish('QmSolid', bom)
    assert uri == 'https://pod.example/user/boms/QmSolid'
    assert len(session.calls) == 1
    url, data, headers, _ = session.calls[0]
    assert url == uri
    assert headers['Authorization'] == 'Bearer secret-token'
    assert headers['Content-Type'] == 'application/ld+json'
    assert b'QmInv' in data


def test_solid_publisher_basic_auth(monkeypatch, tmp_path):
    monkeypatch.setenv('SOLID_POD_BASE_URL', 'https://pod.example/u')
    monkeypatch.delenv('SOLID_CLIENT_ACCESS_TOKEN', raising=False)
    monkeypatch.setenv('SOLID_CLIENT_ID', 'cid')
    monkeypatch.setenv('SOLID_CLIENT_SECRET', 'csecret')
    bom = _signed_bom(monkeypatch, tmp_path)

    class _Resp:
        status_code = 200
        text = ''

    class _Session:
        def put(self, url, data=None, headers=None, timeout=None):
            assert headers['Authorization'].startswith('Basic ')
            return _Resp()

    SolidBomPublisher(session=_Session()).publish('QmB', bom)


def test_solid_publisher_auth_required(monkeypatch, tmp_path):
    monkeypatch.setenv('SOLID_POD_BASE_URL', 'https://pod.example/u')
    monkeypatch.delenv('SOLID_CLIENT_ACCESS_TOKEN', raising=False)
    monkeypatch.delenv('SOLID_CLIENT_ID', raising=False)
    monkeypatch.delenv('SOLID_CLIENT_SECRET', raising=False)
    bom = _signed_bom(monkeypatch, tmp_path)
    with pytest.raises(SolidPublishError, match='auth unset'):
        SolidBomPublisher().publish('QmB', bom)


def test_solid_publisher_acl_denied(monkeypatch, tmp_path):
    monkeypatch.setenv('SOLID_POD_BASE_URL', 'https://pod.example/u')
    monkeypatch.setenv('SOLID_CLIENT_ACCESS_TOKEN', 'bad')
    bom = _signed_bom(monkeypatch, tmp_path)

    class _Resp:
        status_code = 403
        text = 'Forbidden'

    class _Session:
        def put(self, url, data=None, headers=None, timeout=None):
            return _Resp()

    with pytest.raises(SolidPublishError, match='denied'):
        SolidBomPublisher(session=_Session()).publish('QmB', bom)


def test_solid_publisher_401(monkeypatch, tmp_path):
    monkeypatch.setenv('SOLID_POD_BASE_URL', 'https://pod.example/u')
    monkeypatch.setenv('SOLID_CLIENT_ACCESS_TOKEN', 'bad')
    bom = _signed_bom(monkeypatch, tmp_path)

    class _Resp:
        status_code = 401
        text = 'Unauthorized'

    class _Session:
        def put(self, url, data=None, headers=None, timeout=None):
            return _Resp()

    with pytest.raises(SolidPublishError, match='denied'):
        SolidBomPublisher(session=_Session()).publish('QmB', bom)


def test_ldn_inbox_urls(monkeypatch):
    monkeypatch.delenv('SOLID_LDN_INBOX_URLS', raising=False)
    assert ldn_inbox_urls() == []
    monkeypatch.setenv(
        'SOLID_LDN_INBOX_URLS',
        'https://a.example/inbox, https://b.example/inbox/, not-a-url',
    )
    assert ldn_inbox_urls() == [
        'https://a.example/inbox',
        'https://b.example/inbox/',
    ]


def test_build_bom_announcement():
    note = build_bom_announcement(
        bom_cid='QmC',
        bom_solid_uri='https://pod.example/boms/QmC',
    )
    assert note['@type'] == 'Announce'
    assert note['object']['@id'] == 'https://pod.example/boms/QmC'
    assert note['bom_cid'] == 'QmC'


def test_announce_bom_multi_inbox():
    class _Resp:
        def __init__(self, code):
            self.status_code = code
            self.text = ''

    class _Session:
        def __init__(self):
            self.posts = []

        def post(self, url, data=None, headers=None, timeout=None):
            self.posts.append(url)
            if 'fail' in url:
                return _Resp(500)
            return _Resp(201)

    session = _Session()
    ok = announce_bom(
        [
            'https://ok.example/inbox',
            'https://fail.example/inbox',
            'https://ok2.example/inbox',
        ],
        'QmC',
        'https://pod.example/boms/QmC',
        session=session,
    )
    assert ok == [
        'https://ok.example/inbox',
        'https://ok2.example/inbox',
    ]
    assert len(session.posts) == 3


def test_webid_links_did_key(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    monkeypatch.delenv('SOLID_WEBID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    path = write_webid_document(cats_home=str(tmp_path))
    assert path.is_file()
    doc = build_webid_document(cats_home=str(tmp_path))
    assert doc['alsoKnownAs'] == did
    assert did in doc['verificationMethod'][0]['@id']
    assert webid_uri(str(tmp_path)).startswith('file://')


def test_build_bom_container_acl():
    acl = build_bom_container_acl(
        resource_uri='https://pod.example/boms/',
        agent_webid='https://pod.example/profile/card#me',
        readers=['https://reader.example/card#me'],
    )
    graph = acl['@graph']
    assert any(
        a.get('acl:agent', {}).get('@id')
        == 'https://pod.example/profile/card#me'
        for a in graph
    )
    modes = graph[0]['acl:mode']
    assert {'@id': 'acl:Write'} in modes


def test_ensure_solid_bom_acl(monkeypatch, tmp_path):
    monkeypatch.setenv('SOLID_POD_BASE_URL', 'https://pod.example/user')
    monkeypatch.setenv('SOLID_CLIENT_ACCESS_TOKEN', 'tok')
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    node_did(cats_home=str(tmp_path))

    class _Resp:
        status_code = 201
        text = ''

    class _Session:
        def __init__(self):
            self.puts = []

        def put(self, url, data=None, headers=None, timeout=None):
            self.puts.append(url)
            return _Resp()

        def head(self, url, headers=None, timeout=None):
            return _Resp()

    uri = ensure_solid_bom_acl(
        cats_home=str(tmp_path),
        session=_Session(),
    )
    assert uri.endswith('/boms/')


def test_fetch_bom_envelope_solid_url(monkeypatch, tmp_path):
    bom = _signed_bom(monkeypatch, tmp_path)

    class _Resp:
        status_code = 200
        text = ''

        def json(self):
            return bom

    class _Session:
        def get(self, url, timeout=None, headers=None):
            assert url == 'https://pod.example/user/boms/QmX'
            return _Resp()

    out = fetch_bom_envelope(
        'https://pod.example/user/boms/QmX',
        session=_Session(),
    )
    assert out['invoice_cid'] == 'QmInv'


def test_runtime_execute_dual_publish(monkeypatch, tmp_path):
    from cats.runtime import Runtime

    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    monkeypatch.setenv('SOLID_POD_BASE_URL', 'https://pod.example/user')
    monkeypatch.setenv('SOLID_CLIENT_ACCESS_TOKEN', 'tok')
    monkeypatch.setenv(
        'SOLID_LDN_INBOX_URLS',
        'https://inbox.example/notify',
    )
    node_did(cats_home=str(tmp_path))

    mesh = MagicMock()
    mesh.put_json.return_value = 'QmRuntimeBom'
    mesh.cat.side_effect = _mesh_cat_for_runtime_invoice
    runtime = Runtime(contentMesh=mesh, CATS_HOME=str(tmp_path))

    factory = MagicMock()
    executor = MagicMock()
    executor.execute.return_value = ({'log_cid': 'QmLog'}, 'QmInvoice')
    factory.produce.return_value = executor

    solid_uri = 'https://pod.example/user/boms/QmRuntimeBom'
    with patch.object(
        SolidBomPublisher,
        'publish',
        return_value=solid_uri,
    ) as publish, patch(
        'cats.runtime.announce_bom',
        return_value=['https://inbox.example/notify'],
    ) as announce:
        response = runtime.execute(factory, {'order_cid': 'QmOrder'})

    publish.assert_called_once()
    announce.assert_called_once_with(None, 'QmRuntimeBom', solid_uri)
    assert response['bom_cid'] == 'QmRuntimeBom'
    assert response['bom_ldp_uri'] == (
        'http://127.0.0.1:5002/ldp/boms/QmRuntimeBom'
    )
    assert response['bom_solid_uri'] == solid_uri
    stored = BomLdpStore(str(tmp_path)).get('QmRuntimeBom')
    assert stored is not None
    assert 'proof' in stored


def test_runtime_execute_solid_failure_raises(monkeypatch, tmp_path):
    from cats.runtime import Runtime

    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    monkeypatch.setenv('SOLID_POD_BASE_URL', 'https://pod.example/user')
    monkeypatch.setenv('SOLID_CLIENT_ACCESS_TOKEN', 'tok')
    node_did(cats_home=str(tmp_path))

    mesh = MagicMock()
    mesh.put_json.return_value = 'QmFail'
    mesh.cat.side_effect = _mesh_cat_for_runtime_invoice
    runtime = Runtime(contentMesh=mesh, CATS_HOME=str(tmp_path))
    factory = MagicMock()
    executor = MagicMock()
    executor.execute.return_value = ({'log_cid': 'QmLog'}, 'QmInvoice')
    factory.produce.return_value = executor

    class _Resp:
        status_code = 403
        text = 'nope'

    class _Session:
        def put(self, url, data=None, headers=None, timeout=None):
            return _Resp()

    with patch(
        'cats.runtime.SolidBomPublisher',
        lambda **kw: SolidBomPublisher(session=_Session()),
    ):
        with pytest.raises(SolidPublishError, match='denied'):
            runtime.execute(factory, {'order_cid': 'QmOrder'})


def test_runtime_execute_solid_unset_identical(monkeypatch, tmp_path):
    from cats.runtime import Runtime

    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    monkeypatch.delenv('SOLID_POD_BASE_URL', raising=False)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    node_did(cats_home=str(tmp_path))

    mesh = MagicMock()
    mesh.put_json.return_value = 'QmLocal'
    mesh.cat.side_effect = _mesh_cat_for_runtime_invoice
    runtime = Runtime(contentMesh=mesh, CATS_HOME=str(tmp_path))
    factory = MagicMock()
    executor = MagicMock()
    executor.execute.return_value = ({'log_cid': 'QmLog'}, 'QmInvoice')
    factory.produce.return_value = executor

    response = runtime.execute(factory, {'order_cid': 'QmOrder'})
    assert response['bom_solid_uri'] is None
    assert response['bom_ldp_uri'].endswith('/ldp/boms/QmLocal')
