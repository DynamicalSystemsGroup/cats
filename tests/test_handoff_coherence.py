"""Control-plane handoff coherence — response → registry → BOM → Invoice → Order."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from cats.network.registry import (
    assert_control_plane_handoff_coherence,
    assert_input_invoice_slots,
    assert_order_function_slots,
    assert_order_structure_slots,
    make_content_fetch_ref,
    resolve_handoff_invoice_uri,
)


def _store(**bodies):
    def http_get_json(url):
        if url not in bodies:
            raise KeyError(url)
        return bodies[url]

    return http_get_json


def test_resolve_handoff_invoice_uri_prefers_bom_then_registry():
    record = {
        'invoice_uri': 'http://n/inv-rec',
        'locators': {'invoice_uri': 'http://n/inv-loc'},
    }
    # Top-level execute envelope invoice_uri is ignored.
    assert (
        resolve_handoff_invoice_uri({'invoice_uri': 'http://n/inv-resp'}, record)
        == 'http://n/inv-rec'
    )
    assert (
        resolve_handoff_invoice_uri({'bom': {'invoice_uri': 'http://n/inv-bom'}}, record)
        == 'http://n/inv-bom'
    )
    assert resolve_handoff_invoice_uri({}, record) == 'http://n/inv-rec'
    assert (
        resolve_handoff_invoice_uri(
            {}, {'locators': {'invoice_uri': 'http://n/inv-loc'}}
        )
        == 'http://n/inv-loc'
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
            cat_response={'bom_ldp_uri': bom_uri},
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
            cat_response={'bom_ldp_uri': bom_uri},
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


def test_assert_order_function_slots_ok_and_fail():
    ok = {
        'infrafunction_source_uri': 'http://n/ifs',
        'infrafunction_uri': 'http://n/if',
        'process_source_uri': 'http://n/ps',
        'process_uri': 'http://n/p',
    }
    assert_order_function_slots(ok)
    with pytest.raises(AssertionError, match='Function missing'):
        assert_order_function_slots({'infrafunction_uri': 'http://n/if'})


def test_assert_order_structure_slots_ok_and_fail():
    ok = {
        'infrastructure_uri': 'http://n/i',
        'plant_uri': 'http://n/p',
        'root_uri': 'http://n/r',
    }
    assert_order_structure_slots(ok)
    with pytest.raises(AssertionError, match='Structure missing'):
        assert_order_structure_slots({'plant_uri': 'http://n/p'})


def test_assert_input_invoice_slots_ok_and_fail():
    assert_input_invoice_slots({'data_uri': 'http://n/d'})
    with pytest.raises(AssertionError, match='input Invoice missing'):
        assert_input_invoice_slots({})
