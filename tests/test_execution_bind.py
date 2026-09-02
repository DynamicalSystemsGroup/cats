"""BOM prov:used execution bind — Order then output Invoice."""
from __future__ import annotations

import pytest

from cats.network.feedback import build_execution_bom
from cats.network.registry import assert_execution_bind


def _store(**bodies):
    def http_get_json(url):
        if url not in bodies:
            raise KeyError(url)
        return bodies[url]

    return http_get_json


def test_execution_bind_ok_identity_and_payload():
    order_uri = 'http://n/ldp/cas/ord1'
    invoice_uri = 'http://n/ldp/cas/inv1'
    order = {'function_uri': 'http://n/f', 'structure_uri': 'http://n/s'}
    invoice = {'data_uri': 'http://n/d', 'order_uri': order_uri}
    bom = build_execution_bom(
        log_id='log1',
        invoice_id='inv1',
        order_id='ord1',
        invoice_uri=invoice_uri,
        order_uri=order_uri,
    )
    bind = assert_execution_bind(
        bom,
        order_uri=order_uri,
        invoice_uri=invoice_uri,
        http_get_json=_store(**{order_uri: order, invoice_uri: invoice}),
        expected_order=order,
        expected_invoice=invoice,
    )
    assert bind[0]['@id'] == order_uri
    assert bind[1]['@id'] == invoice_uri


def test_execution_bind_digest_agrees_across_collections():
    bom = {
        'prov:wasGeneratedBy': {
            'prov:used': [
                {'@id': 'http://n/ldp/cas/ord1', 'contentId': 'ord1'},
                {'@id': 'http://n/ldp/cas/inv1', 'contentId': 'inv1'},
            ]
        }
    }
    bind = assert_execution_bind(
        bom,
        order_uri='http://n/ldp/orders/ord1',
        invoice_uri='http://n/ldp/invoices/inv1',
    )
    assert len(bind) == 2


def test_execution_bind_ipfs_id_agrees_via_content_id():
    bom = {
        'prov:wasGeneratedBy': {
            'prov:used': [
                {'@id': 'ipfs://ord1', 'contentId': 'ord1'},
                {'@id': 'ipfs://inv1', 'contentId': 'inv1'},
            ]
        }
    }
    assert_execution_bind(
        bom,
        order_uri='http://n/ldp/cas/ord1',
        invoice_uri='http://n/ldp/cas/inv1',
    )


def test_execution_bind_single_used_raises():
    bom = build_execution_bom(log_id='log1', invoice_id='inv1')
    with pytest.raises(AssertionError, match='Order then Invoice'):
        assert_execution_bind(
            bom,
            order_uri='http://n/ldp/cas/ord1',
            invoice_uri='http://n/ldp/cas/inv1',
        )


def test_execution_bind_order_mismatch_raises():
    bom = build_execution_bom(
        log_id='log1',
        invoice_id='inv1',
        order_id='ord1',
        invoice_uri='http://n/ldp/cas/inv1',
        order_uri='http://n/ldp/cas/ord1',
    )
    with pytest.raises(AssertionError, match='Order token'):
        assert_execution_bind(
            bom,
            order_uri='http://n/ldp/cas/other',
            invoice_uri='http://n/ldp/cas/inv1',
        )


def test_execution_bind_payload_mismatch_raises():
    order_uri = 'http://n/ldp/cas/ord1'
    invoice_uri = 'http://n/ldp/cas/inv1'
    bom = build_execution_bom(
        log_id='log1',
        invoice_id='inv1',
        order_id='ord1',
        invoice_uri=invoice_uri,
        order_uri=order_uri,
    )
    with pytest.raises(AssertionError, match='payload != expected'):
        assert_execution_bind(
            bom,
            order_uri=order_uri,
            invoice_uri=invoice_uri,
            http_get_json=_store(
                **{
                    order_uri: {'function_uri': 'http://n/f'},
                    invoice_uri: {'data_uri': 'http://n/d'},
                }
            ),
            expected_order={'function_uri': 'http://n/f'},
            expected_invoice={'data_uri': 'http://n/other'},
        )


def test_execution_bind_expected_requires_http_get_json():
    bom = build_execution_bom(
        log_id='log1',
        invoice_id='inv1',
        order_id='ord1',
        invoice_uri='http://n/ldp/cas/inv1',
        order_uri='http://n/ldp/cas/ord1',
    )
    with pytest.raises(AssertionError, match='require http_get_json'):
        assert_execution_bind(
            bom,
            order_uri='http://n/ldp/cas/ord1',
            invoice_uri='http://n/ldp/cas/inv1',
            expected_invoice={'data_uri': 'http://n/d'},
        )
