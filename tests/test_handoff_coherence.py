"""Control-plane handoff coherence — response → registry → BOM → Invoice → Order."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from cats.network.registry import (
    assert_control_plane_handoff_coherence,
    make_content_fetch_ref,
    resolve_handoff_invoice_uri,
)


def _store(**bodies):
    def http_get_json(url):
        if url not in bodies:
            raise KeyError(url)
        return bodies[url]

    return http_get_json


def test_resolve_handoff_invoice_uri_prefers_response():
    record = {
        'invoice_uri': 'http://n/inv-rec',
        'locators': {'invoice_uri': 'http://n/inv-loc'},
    }
    resp = {'invoice_uri': 'http://n/inv-resp'}
    assert resolve_handoff_invoice_uri(resp, record) == 'http://n/inv-resp'
    assert (
        resolve_handoff_invoice_uri({'bom': {'invoice_uri': 'http://n/inv-bom'}}, record)
        == 'http://n/inv-bom'
    )


def test_assert_control_plane_handoff_coherence_ok():
    bom_uri = 'http://n/ldp/boms/b1'
    inv_uri = 'http://n/ldp/cas/i1'
    order_uri = 'http://n/ldp/cas/o1'
    data_uri = 'http://n/ldp/cas/d1'
    seed_uri = 'http://n/ldp/cas/s1'
    fn_uri = 'http://n/ldp/cas/f1'
    st_uri = 'http://n/ldp/cas/st1'
    in_inv = 'http://n/ldp/cas/ii1'

    cat_response = {
        'bom_ldp_uri': bom_uri,
        'invoice_uri': inv_uri,
    }
    record = {
        'invoice_uri': inv_uri,
        'data_uri': data_uri,
        'order_uri': 'http://n/ldp/orders/o1',
        'order': 'ni-order',
        'data': 'ni-data',
        'locators': {
            'bom_ldp_uri': bom_uri,
            'invoice_uri': inv_uri,
            'order_uri': 'http://n/ldp/orders/o1',
        },
    }
    http_get_json = _store(
        **{
            bom_uri: {'invoice_uri': inv_uri},
            inv_uri: {
                'order_uri': order_uri,
                'data_uri': data_uri,
                'seed_uri': seed_uri,
            },
            order_uri: {
                'function_uri': fn_uri,
                'structure_uri': st_uri,
                'invoice_uri': in_inv,
            },
        }
    )

    out = assert_control_plane_handoff_coherence(
        cat_response=cat_response,
        record=record,
        http_get_json=http_get_json,
    )
    assert out['bom_ldp_uri'] == bom_uri
    assert out['invoice']['order_uri'] == order_uri
    assert out['order']['function_uri'] == fn_uri
    assert 'function_uri' not in out
    assert 'order_uri' not in out
    assert 'fetch_ref' not in out


def test_assert_fails_on_response_registry_locator_mismatch():
    bom_uri = 'http://n/b'
    inv_uri = 'http://n/i'
    with pytest.raises(AssertionError, match='bom_ldp_uri'):
        assert_control_plane_handoff_coherence(
            cat_response={'bom_ldp_uri': bom_uri, 'invoice_uri': inv_uri},
            record={
                'locators': {
                    'bom_ldp_uri': 'http://n/other',
                    'invoice_uri': inv_uri,
                }
            },
            http_get_json=_store(),
        )


def test_assert_fails_on_incomplete_invoice():
    bom_uri = 'http://n/b'
    inv_uri = 'http://n/i'
    with pytest.raises(AssertionError, match='order_uri/data_uri/seed_uri'):
        assert_control_plane_handoff_coherence(
            cat_response={'bom_ldp_uri': bom_uri, 'invoice_uri': inv_uri},
            record={
                'invoice_uri': inv_uri,
                'locators': {'bom_ldp_uri': bom_uri, 'invoice_uri': inv_uri},
            },
            http_get_json=_store(
                **{
                    bom_uri: {'invoice_uri': inv_uri},
                    inv_uri: {'order_uri': 'http://n/o'},
                }
            ),
        )


def test_make_content_fetch_ref_mesh_equals_http():
    payload = {'k': 1}
    mesh = MagicMock()
    mesh.cat.return_value = json.dumps(payload)
    record = {'order': 'ni-order'}
    http_get_json = lambda url: payload if url == 'http://n/o' else None
    fetch = make_content_fetch_ref(
        record=record, content_mesh=mesh, http_get_json=http_get_json
    )
    assert fetch('order', 'http://n/o') == payload
    mesh.cat.assert_called_with('ni-order')


def test_make_content_fetch_ref_mismatch_raises():
    mesh = MagicMock()
    mesh.cat.return_value = json.dumps({'k': 1})
    fetch = make_content_fetch_ref(
        record={},
        content_mesh=mesh,
        http_get_json=lambda url: {'k': 2},
    )
    with pytest.raises(AssertionError, match='must match'):
        fetch('data', 'http://n/d')
