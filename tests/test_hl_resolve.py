"""§6f — AddressStore ``hl:`` resolve, intake, Runtime/LDN emit."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from cats.network.address_store import AddressStore
from cats.network.cas import (
    CasHttpStore,
    LocatorIndex,
    from_hl,
    from_ni,
    resolve_intake_ref,
    sha256_hex,
    to_hl,
    to_ni,
)
from cats.network.identity import node_did
from cats.network.ldp import BomLdpStore
from cats.network.ldp.ldn import announce_bom, build_bom_announcement
from cats.network.registry import BomRegistry
from cats.runtime import Runtime


class _NoIpfs:
    def cat_bytes(self, content_id):
        raise AssertionError(f'unexpected IPFS cat: {content_id}')

    def get(self, content_id, dest_path):
        raise AssertionError(f'unexpected IPFS get: {content_id}')

    def dag_export(self, cid, filepath):
        raise AssertionError(f'unexpected IPFS dag_export: {cid}')


def test_address_store_hl_resolve_happy(tmp_path, monkeypatch):
    payload = b'hl-happy-bytes\n'
    digest = sha256_hex(payload)
    ni = to_ni(digest)
    uri = f'https://example.test/ldp/cas/{digest}'
    hl = to_hl(ni, uri)

    store = AddressStore(_NoIpfs(), cats_home=str(tmp_path), timeout=5.0)

    def fake_urlopen(req, timeout=None):
        assert req.full_url == uri
        resp = MagicMock()
        resp.read.return_value = payload
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    monkeypatch.setattr(
        'cats.network.address_store.store.urlopen',
        fake_urlopen,
    )
    assert store.cat_bytes(hl) == payload


def test_address_store_hl_tampered_fails(tmp_path, monkeypatch):
    payload = b'good\n'
    digest = sha256_hex(payload)
    ni = to_ni(digest)
    uri = f'https://example.test/ldp/cas/{digest}'
    hl = to_hl(ni, uri)

    store = AddressStore(_NoIpfs(), cats_home=str(tmp_path), timeout=5.0)

    def fake_urlopen(req, timeout=None):
        resp = MagicMock()
        resp.read.return_value = b'tampered\n'
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    monkeypatch.setattr(
        'cats.network.address_store.store.urlopen',
        fake_urlopen,
    )
    with pytest.raises(RuntimeError, match='hl: sha256 mismatch'):
        store.cat_bytes(hl)


def test_address_store_hl_no_hint_uses_cas(tmp_path):
    payload = b'no-hint\n'
    cas = CasHttpStore(str(tmp_path))
    ni = cas.put(payload)
    hl = to_hl(ni)
    store = AddressStore(_NoIpfs(), cats_home=str(tmp_path))
    assert store.cat_bytes(hl) == payload


def test_resolve_intake_ref_hl(tmp_path):
    digest = sha256_hex(b'intake')
    ni = to_ni(digest)
    uri = f'https://example.test/ldp/cas/{digest}'
    hl = to_hl(ni, uri)
    got = resolve_intake_ref(hl, cats_home=str(tmp_path))
    assert got == ni
    assert uri in LocatorIndex(str(tmp_path)).lookup_uris(ni)


def test_build_bom_announcement_content_id_hl():
    note = build_bom_announcement(
        content_id='ni:///sha-256;aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        bom_solid_uri='https://pod.example/boms/x',
        hl='hl:deadbeef:https://pod.example/boms/x',
    )
    assert note['@type'] == 'Announce'
    assert 'bom_cid' not in note
    assert note['content_id'].startswith('ni:')
    assert note['hl'].startswith('hl:')


def test_announce_bom_passes_hl():
    class _Resp:
        def __init__(self, code):
            self.status_code = code
            self.text = ''

    class _Session:
        def __init__(self):
            self.bodies = []

        def post(self, url, data=None, headers=None, timeout=None):
            self.bodies.append(data.decode('utf-8'))
            return _Resp(201)

    session = _Session()
    ni = to_ni(sha256_hex(b'x'))
    hl = to_hl(ni, 'https://pod.example/boms/x')
    ok = announce_bom(
        ['https://ok.example/inbox'],
        ni,
        'https://pod.example/boms/x',
        hl=hl,
        session=session,
    )
    assert ok == ['https://ok.example/inbox']
    assert '"hl"' in session.bodies[0]
    assert '"content_id"' in session.bodies[0]
    assert 'bom_cid' not in session.bodies[0]


def test_runtime_execute_emits_hl(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    monkeypatch.delenv('SOLID_POD_BASE_URL', raising=False)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    node_did(cats_home=str(tmp_path))

    digest = sha256_hex(b'{"bom":true}\n')
    bom_id = to_ni(digest)

    mesh = MagicMock()
    mesh.put_json.return_value = bom_id
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

    runtime = Runtime(contentMesh=mesh, CATS_HOME=str(tmp_path))
    factory = MagicMock()
    executor = MagicMock()
    executor.execute.return_value = (
        {
            'invoice': {
                'order_cid': 'QmOrder',
                'data_cid': 'QmDataOut',
            },
            'log_uri': 'QmLog',
        },
        'QmInvoice',
    )
    factory.produce.return_value = executor

    with patch('cats.runtime.build_record') as mock_build:
        mock_build.return_value = {
            'content_id': bom_id,
            'data_id': 'QmDataOut',
            'order_id': 'QmOrder',
            'locators': {},
        }
        with patch.object(BomRegistry, 'put', return_value=None):
            response = runtime.execute(factory, {'order_id': 'QmOrder'})

    assert response['content_id'] == bom_id
    assert 'hl' in response
    got_ni, uris = from_hl(response['hl'])
    assert got_ni == bom_id
    assert uris == [response['bom_ldp_uri']]
    assert BomLdpStore(str(tmp_path)).get(bom_id) is not None


def test_link_intake_hl_resolves(tmp_path, monkeypatch):
    """linkProcess(hl=…) resolves data equality via registry."""
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5099')
    from cats.network.cas.digest import content_id_fs_key
    from cats.network.content_mesh import ContentMesh

    data_id = to_ni(sha256_hex(b'data-out\n'))
    bom_id = to_ni(sha256_hex(b'{"@type":"ExecutionBom"}\n'))
    BomLdpStore(str(tmp_path)).put(bom_id, {'@type': 'ExecutionBom', 'proof': {}})
    registry = BomRegistry(str(tmp_path))
    record = {
        'content_id': bom_id,
        'data_id': data_id,
        'order_id': 'QmOrder',
        'locators': {
            'bom_ldp_uri': (
                f'http://127.0.0.1:5099/ldp/boms/{content_id_fs_key(bom_id)}'
            ),
        },
    }
    by_data = registry.by_data_dir / f'{content_id_fs_key(data_id)}.json'
    by_data.parent.mkdir(parents=True, exist_ok=True)
    by_data.write_text(json.dumps([bom_id], indent=2) + '\n', encoding='utf-8')
    bom_path = registry._bom_path(bom_id)
    bom_path.parent.mkdir(parents=True, exist_ok=True)
    bom_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')

    hl = to_hl(data_id, f'https://example.test/ldp/cas/{from_ni(data_id)}')
    mesh = ContentMesh.__new__(ContentMesh)
    mesh.CATS_HOME = str(tmp_path)
    mesh.ipfs = _NoIpfs()

    shell = mesh._response_from_registry(hl=hl)
    assert shell['content_id'] == bom_id
