"""Phase 2a BOM registry — Control-Feedback index (before Phase 2b / §6d)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from flask import Flask

from cats.network.feedback import build_execution_bom, sign_execution_bom
from cats.network.identity import node_did
from cats.network.ldp import BomLdpStore
from cats.network.ldp.headers import LDP_BASIC_CONTAINER, LDP_RESOURCE
from cats.network.registry import (
    AmbiguousBomError,
    BomRegistry,
    RegistryError,
    build_record,
    register_registry_routes,
)


def _signed_bom(monkeypatch, tmp_path, *, invoice_id='QmInv'):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    return sign_execution_bom(
        build_execution_bom(
            log_id='QmLog',
            invoice_id=invoice_id,
            node_did=did,
        ),
        cats_home=str(tmp_path),
    )


def _mesh_with_invoice(
    *,
    invoice_id='QmInv',
    order_id='QmOrder',
    data_id='QmDataOut',
    function_id='QmFn',
    structure_id='QmStruct',
    input_data_id='QmDataIn',
):
    mesh = MagicMock()

    def _cat(cid):
        if cid == invoice_id:
            return json.dumps({
                'order_cid': order_id,
                'data_cid': data_id,
                'ingress_data_cid': 'QmIngress',
                'integration_data_cid': 'QmInteg',
                'seed_cid': 'QmSeed',
            })
        if cid == order_id:
            return json.dumps({
                'function_cid': function_id,
                'structure_cid': structure_id,
                'invoice_cid': 'QmInvIn',
            })
        if cid == 'QmInvIn':
            return json.dumps({'data_cid': input_data_id})
        raise KeyError(cid)

    mesh.cat.side_effect = _cat
    return mesh


def test_registry_put_get_idempotent_indexes(tmp_path, monkeypatch):
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice()
    record = build_record(
        bom,
        'QmBom1',
        content_mesh=mesh,
        locators={'bom_ldp_uri': 'http://n/ldp/boms/QmBom1'},
    )
    reg = BomRegistry(str(tmp_path))
    reg.put(record)
    reg.put(record)  # idempotent
    stored = reg.get('QmBom1')
    assert stored['data'] == 'QmDataOut'
    assert stored['content_id'] == 'QmBom1'
    assert 'data_cid' not in stored
    assert reg.lookup_order('QmBom1') == 'QmOrder'
    assert reg.lookup_bom('QmDataOut') == ['QmBom1']
    assert reg.lookup_by_order('QmOrder') == ['QmBom1']


def test_registry_rejects_path_traversal(tmp_path):
    reg = BomRegistry(str(tmp_path))
    with pytest.raises(ValueError):
        reg.put({
            'content_id': '../etc/passwd',
            'order': 'QmOrder',
            'data': 'QmData',
        })


def test_build_record_rejects_unsigned(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    unsigned = build_execution_bom(
        log_id='QmLog',
        invoice_id='QmInv',
        node_did=did,
    )
    mesh = _mesh_with_invoice()
    with pytest.raises(RegistryError, match='unsigned|invalid'):
        build_record(unsigned, 'QmBom', content_mesh=mesh)


def test_build_record_rejects_tampered(monkeypatch, tmp_path):
    bom = _signed_bom(monkeypatch, tmp_path)
    bom['invoice_uri'] = 'QmEvil'
    mesh = _mesh_with_invoice(invoice_id='QmEvil')
    with pytest.raises(RegistryError, match='unsigned|invalid'):
        build_record(bom, 'QmBom', content_mesh=mesh)


def test_build_record_uses_invoice_data(monkeypatch, tmp_path):
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice(data_id='QmFromInvoice')
    record = build_record(bom, 'QmBom', content_mesh=mesh)
    assert record['data'] == 'QmFromInvoice'
    assert record['function'] == 'QmFn'
    assert record['input_data'] == 'QmDataIn'
    assert 'data_cid' not in record
    assert 'function_cid' not in record


def test_ambiguous_data_lookup(tmp_path, monkeypatch):
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice()
    reg = BomRegistry(str(tmp_path))
    for cid in ('QmBomA', 'QmBomB'):
        # Re-sign would change proof; put pre-built records directly for index test.
        reg.put({
            'content_id': cid,
            'invoice_uri': 'QmInv',
            'order': 'QmOrder',
            'data': 'QmShared',
            'input_data': None,
            'node_did': bom['node_did'],
            'function': 'QmFn',
            'structure': 'QmStruct',
            'locators': {},
            'ingress_data': None,
            'integration_data': None,
            'seed': None,
        })
    assert reg.lookup_bom('QmShared') == ['QmBomB', 'QmBomA']
    with pytest.raises(AmbiguousBomError) as exc:
        reg.resolve_unique_bom('QmShared')
    assert set(exc.value.bom_ids) == {'QmBomA', 'QmBomB'}
    assert set(exc.value.bom_cids) == {'QmBomA', 'QmBomB'}


def test_flask_registry_routes(monkeypatch, tmp_path):
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice()
    record = build_record(
        bom,
        'QmFlask',
        content_mesh=mesh,
        locators={'bom_ldp_uri': 'http://127.0.0.1:5002/ldp/boms/QmFlask'},
    )
    BomRegistry(str(tmp_path)).put(record)

    app = Flask(__name__)
    register_registry_routes(app, cats_home=str(tmp_path))
    client = app.test_client()

    container = client.get('/ldp/registry/')
    assert container.status_code == 200
    assert LDP_BASIC_CONTAINER in container.headers.get('Link', '')
    assert any('QmFlask' in u for u in container.get_json()['contains'])

    resource = client.get('/ldp/registry/boms/QmFlask')
    assert resource.status_code == 200
    assert LDP_RESOURCE in resource.headers.get('Link', '')
    body = resource.get_json()
    assert body['order'] == 'QmOrder'
    assert body['content_id'] == 'QmFlask'
    assert 'order_cid' not in body
    assert 'data_cid' not in body

    from cats.network.registry import (
        assert_registry_bom_parity,
        assert_registry_by_data_parity,
        assert_registry_by_order_parity,
    )

    reg = BomRegistry(str(tmp_path))
    assert_registry_bom_parity(record, body, bom_id='QmFlask')
    by_data = client.get('/ldp/registry/by-data/QmDataOut')
    assert by_data.status_code == 200
    assert_registry_by_data_parity(
        reg.lookup_bom('QmDataOut'),
        by_data.get_json(),
        data_id='QmDataOut',
    )

    by_order = client.get('/ldp/registry/by-order/QmOrder')
    assert by_order.status_code == 200
    assert_registry_by_order_parity(
        reg.lookup_by_order('QmOrder'),
        by_order.get_json(),
        order_id='QmOrder',
        bom_id='QmFlask',
    )

    missing = client.get('/ldp/registry/boms/QmMissing')
    assert missing.status_code == 404

    put = client.put('/ldp/registry/boms/QmFlask', json=record)
    assert put.status_code == 405


def test_init_rejects_legacy_cid_keys(monkeypatch, tmp_path):
    from cats.node import app as node_app

    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice()
    record = build_record(bom, 'QmInit', content_mesh=mesh)
    BomRegistry(str(tmp_path)).put(record)

    monkeypatch.setattr(node_app, 'CATS_HOME', str(tmp_path))

    with node_app.catNode.app_context():
        for legacy in (
            {'bom_cid': 'QmInit'},
            {'data_cid': 'QmDataOut'},
            {'order_cid': 'QmDirect'},
        ):
            order_cid, err = node_app._resolve_order_id_from_request(legacy)
            assert order_cid is None
            assert err[1] == 400
            assert 'no longer accepted' in err[0].get_json()['error']


def test_init_content_id_and_data_uri(monkeypatch, tmp_path):
    from cats.node import app as node_app

    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice()
    record = build_record(bom, 'QmInit', content_mesh=mesh)
    BomRegistry(str(tmp_path)).put(record)

    monkeypatch.setattr(node_app, 'CATS_HOME', str(tmp_path))
    data_uri = 'http://127.0.0.1:5002/ldp/cas/QmDataOut'

    with node_app.catNode.app_context():
        order_cid, err = node_app._resolve_order_id_from_request(
            {'content_id': 'QmDataOut'}
        )
        assert err is None
        assert order_cid == 'QmOrder'

        order_cid, err = node_app._resolve_order_id_from_request(
            {'data_uri': data_uri}
        )
        assert err is None
        assert order_cid == 'QmOrder'

        bom_uri = 'http://127.0.0.1:5002/ldp/boms/QmInit'
        order_cid, err = node_app._resolve_order_id_from_request(
            {'bom_ldp_uri': bom_uri}
        )
        assert err is None
        assert order_cid == 'QmOrder'

        _, err = node_app._resolve_order_id_from_request({'content_id': 'QmNope'})
        assert err[1] == 404

        BomRegistry(str(tmp_path)).put({
            **record,
            'content_id': 'QmInit2',
        })
        _, err = node_app._resolve_order_id_from_request({'content_id': 'QmDataOut'})
        assert err[1] == 409
        assert set(err[0].get_json()['bom_ids']) == {'QmInit', 'QmInit2'}

        _, err = node_app._resolve_order_id_from_request({})
        assert err[1] == 400


def test_link_process_via_content_id(monkeypatch, tmp_path):
    from cats.network import ContentMesh

    bom = _signed_bom(monkeypatch, tmp_path)
    # flatten_bom needs a richer invoice/order graph.
    invoice = {
        'order_cid': 'QmOrder',
        'data_cid': 'QmDataOut',
    }
    order = {
        'function_cid': 'QmFn',
        'structure_cid': 'QmStruct',
        'invoice_cid': 'QmInvOld',
        'structure_filepath': 'structure',
        'endpoint': 'http://127.0.0.1:5000/cat/node/init',
    }
    prev_function = {
        'process_cid': 'QmProcBind',
        'infrafunction_cid': 'QmIfrBind',
        'process_source_cid': 'QmProcSrc',
        'infrafunction_source_cid': 'QmIfrSrc',
    }
    prev_process = {
        'ingress_subproc_cid': 'QmIn',
        'integrated_subproc_cid': 'QmInt',
        'egress_subproc_cid': 'QmEg',
        'integration_cache_subproc_cid': 'QmCache',
    }
    prev_infrafunction = {'infrafunction_subproc_cid': 'QmIfr'}

    signed = sign_execution_bom(
        build_execution_bom(
            log_id='QmLog',
            invoice_id='QmInv',
            node_did=bom['node_did'],
        ),
        cats_home=str(tmp_path),
    )

    def _cat(cid):
        return {
            'QmInv': json.dumps(invoice),
            'QmOrder': json.dumps(order),
            'QmFn': json.dumps(prev_function),
            'QmStruct': json.dumps({
                'root_cid': 'QmRoot',
                'plant_cid': 'QmPlant',
                'infrastructure_cid': 'QmInfra',
            }),
            'QmInvOld': json.dumps({'data_cid': 'QmDataOut'}),
            'QmProcBind': json.dumps(prev_process),
            'QmIfrBind': json.dumps(prev_infrafunction),
            'QmLog': json.dumps({}),
        }[cid]

    mesh = MagicMock()
    mesh.cat.side_effect = _cat
    record = build_record(
        signed,
        'QmLinkBom',
        content_mesh=mesh,
        locators={'bom_ldp_uri': 'http://127.0.0.1:5002/ldp/boms/QmLinkBom'},
    )
    BomRegistry(str(tmp_path)).put(record)
    BomLdpStore(str(tmp_path)).put('QmLinkBom', signed)

    from data.input.function.process import process_0, process_1

    fake = MagicMock()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')

    with pytest.raises(RuntimeError, match='bom_cid no longer accepted'):
        client.linkProcess(bom_cid='QmLinkBom', integrated_subproc=process_1)

    with pytest.raises(RuntimeError, match='data_cid no longer accepted'):
        client.linkProcess(data_cid='QmDataOut', integrated_subproc=process_0)

    order_req = client.linkProcess(
        content_id='QmDataOut', integrated_subproc=process_1
    )
    assert order_req['content_id']
    assert 'order_cid' not in order_req
    assert 'invoice_cid' not in order_req
    assert 'order_uri' in order_req
    assert 'invoice_uri' in order_req

    order_req2 = client.linkProcess(
        bom_ldp_uri='http://127.0.0.1:5002/ldp/boms/QmLinkBom',
        integrated_subproc=process_0,
    )
    assert order_req2['content_id']
