"""Phase 2a BOM registry — Control-Feedback index (before Phase 2b)."""
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


def _signed_bom(monkeypatch, tmp_path, *, invoice_cid='QmInv'):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    return sign_execution_bom(
        build_execution_bom(
            log_cid='QmLog',
            invoice_cid=invoice_cid,
            node_did=did,
        ),
        cats_home=str(tmp_path),
    )


def _mesh_with_invoice(
    *,
    invoice_cid='QmInv',
    order_cid='QmOrder',
    data_cid='QmDataOut',
    function_cid='QmFn',
    structure_cid='QmStruct',
    input_data_cid='QmDataIn',
):
    mesh = MagicMock()

    def _cat(cid):
        if cid == invoice_cid:
            return json.dumps({
                'order_cid': order_cid,
                'data_cid': data_cid,
                'ingress_data_cid': 'QmIngress',
                'integration_data_cid': 'QmInteg',
                'seed_cid': 'QmSeed',
            })
        if cid == order_cid:
            return json.dumps({
                'function_cid': function_cid,
                'structure_cid': structure_cid,
                'invoice_cid': 'QmInvIn',
            })
        if cid == 'QmInvIn':
            return json.dumps({'data_cid': input_data_cid})
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
    assert reg.get('QmBom1')['data_cid'] == 'QmDataOut'
    assert reg.lookup_order('QmBom1') == 'QmOrder'
    assert reg.lookup_bom('QmDataOut') == ['QmBom1']
    assert reg.lookup_by_order('QmOrder') == ['QmBom1']


def test_registry_rejects_path_traversal(tmp_path):
    reg = BomRegistry(str(tmp_path))
    with pytest.raises(ValueError):
        reg.put({
            'bom_cid': '../etc/passwd',
            'order_cid': 'QmOrder',
            'data_cid': 'QmData',
        })


def test_build_record_rejects_unsigned(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    unsigned = build_execution_bom(
        log_cid='QmLog',
        invoice_cid='QmInv',
        node_did=did,
    )
    mesh = _mesh_with_invoice()
    with pytest.raises(RegistryError, match='unsigned|invalid'):
        build_record(unsigned, 'QmBom', content_mesh=mesh)


def test_build_record_rejects_tampered(monkeypatch, tmp_path):
    bom = _signed_bom(monkeypatch, tmp_path)
    bom['invoice_cid'] = 'QmEvil'
    mesh = _mesh_with_invoice(invoice_cid='QmEvil')
    with pytest.raises(RegistryError, match='unsigned|invalid'):
        build_record(bom, 'QmBom', content_mesh=mesh)


def test_build_record_uses_invoice_data_cid(monkeypatch, tmp_path):
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice(data_cid='QmFromInvoice')
    record = build_record(bom, 'QmBom', content_mesh=mesh)
    assert record['data_cid'] == 'QmFromInvoice'
    assert record['function_cid'] == 'QmFn'
    assert record['input_data_cid'] == 'QmDataIn'


def test_ambiguous_data_cid(tmp_path, monkeypatch):
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice()
    reg = BomRegistry(str(tmp_path))
    for cid in ('QmBomA', 'QmBomB'):
        # Re-sign would change proof; put pre-built records directly for index test.
        reg.put({
            'bom_cid': cid,
            'invoice_cid': 'QmInv',
            'order_cid': 'QmOrder',
            'data_cid': 'QmShared',
            'input_data_cid': None,
            'node_did': bom['node_did'],
            'function_cid': 'QmFn',
            'structure_cid': 'QmStruct',
            'locators': {},
            'ingress_data_cid': None,
            'integration_data_cid': None,
            'seed_cid': None,
        })
    assert reg.lookup_bom('QmShared') == ['QmBomB', 'QmBomA']
    with pytest.raises(AmbiguousBomError) as exc:
        reg.resolve_unique_bom('QmShared')
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
    assert resource.get_json()['order_cid'] == 'QmOrder'

    by_data = client.get('/ldp/registry/by-data/QmDataOut')
    assert by_data.status_code == 200
    assert by_data.get_json()['bom_cids'] == ['QmFlask']

    by_order = client.get('/ldp/registry/by-order/QmOrder')
    assert by_order.status_code == 200
    assert by_order.get_json()['bom_cids'] == ['QmFlask']

    missing = client.get('/ldp/registry/boms/QmMissing')
    assert missing.status_code == 404

    put = client.put('/ldp/registry/boms/QmFlask', json=record)
    assert put.status_code == 405


def test_init_bom_cid_and_data_cid(monkeypatch, tmp_path):
    from cats.node import app as node_app

    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5002')
    bom = _signed_bom(monkeypatch, tmp_path)
    mesh = _mesh_with_invoice()
    record = build_record(bom, 'QmInit', content_mesh=mesh)
    BomRegistry(str(tmp_path)).put(record)

    monkeypatch.setattr(node_app, 'CATS_HOME', str(tmp_path))

    with node_app.catNode.app_context():
        order_cid, err = node_app._resolve_order_cid_from_request(
            {'bom_cid': 'QmInit'}
        )
        assert err is None
        assert order_cid == 'QmOrder'

        order_cid, err = node_app._resolve_order_cid_from_request(
            {'data_cid': 'QmDataOut'}
        )
        assert err is None
        assert order_cid == 'QmOrder'

        order_cid, err = node_app._resolve_order_cid_from_request(
            {'order_cid': 'QmDirect'}
        )
        assert err is None
        assert order_cid == 'QmDirect'

        _, err = node_app._resolve_order_cid_from_request({'data_cid': 'QmNope'})
        assert err[1] == 404

        BomRegistry(str(tmp_path)).put({
            **record,
            'bom_cid': 'QmInit2',
        })
        _, err = node_app._resolve_order_cid_from_request({'data_cid': 'QmDataOut'})
        assert err[1] == 409
        assert set(err[0].get_json()['bom_cids']) == {'QmInit', 'QmInit2'}

        _, err = node_app._resolve_order_cid_from_request({})
        assert err[1] == 400


def test_link_process_via_bom_cid(monkeypatch, tmp_path):
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

    signed = dict(bom)
    signed['invoice_cid'] = 'QmInv'
    # Re-sign with matching invoice_cid
    signed = sign_execution_bom(
        build_execution_bom(
            log_cid='QmLog',
            invoice_cid='QmInv',
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

    order_req = client.linkProcess(bom_cid='QmLinkBom', integrated_subproc=process_1)
    assert order_req['order_cid']

    order_req2 = client.linkProcess(data_cid='QmDataOut', integrated_subproc=process_0)
    assert order_req2['order_cid']
