"""Order subcomponent content equivalence — mesh.cat ≡ HTTP GET."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from cats.network.registry import (
    assert_order_content_equiv,
    assert_order_subcomponent_equiv,
)


def _mesh(bodies: dict):
    mesh = MagicMock()

    def cat_obj(locator):
        if locator not in bodies:
            raise KeyError(locator)
        value = bodies[locator]
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        if isinstance(value, str):
            return value.encode('utf-8')
        return json.dumps(value).encode('utf-8')

    mesh.catObj.side_effect = cat_obj
    mesh.cat.side_effect = lambda loc: cat_obj(loc).decode('utf-8')
    return mesh


def _http(bodies: dict):
    def http_get_json(url):
        value = bodies[url]
        if isinstance(value, (bytes, bytearray)):
            return json.loads(value.decode('utf-8'))
        if isinstance(value, str):
            return json.loads(value)
        return value

    def http_get(url):
        value = bodies[url]
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        if isinstance(value, str):
            return value.encode('utf-8')
        return json.dumps(value).encode('utf-8')

    return http_get_json, http_get


def test_order_function_fetch_equiv():
    fn_uri = 'http://n/ldp/cas/fn'
    ifs = 'http://n/ldp/cas/ifs'
    iff = 'http://n/ldp/cas/if'
    ps = 'http://n/ldp/cas/ps'
    p = 'http://n/ldp/cas/p'
    function = {
        'infrafunction_source_uri': ifs,
        'infrafunction_uri': iff,
        'process_source_uri': ps,
        'process_uri': p,
    }
    bodies = {
        fn_uri: function,
        ifs: {'module': 'a'},
        iff: {'module': 'b'},
        ps: {'module': 'c'},
        p: {'module': 'd'},
    }
    order = {'function_uri': fn_uri}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    out = assert_order_subcomponent_equiv(
        order,
        'function',
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )
    assert out == function


def test_order_structure_fetch_equiv():
    st_uri = 'http://n/ldp/cas/st'
    infra = 'http://n/ldp/cas/infra'
    plant = 'http://n/ldp/cas/plant'
    root = 'http://n/ldp/cas/root'
    structure = {
        'infrastructure_uri': infra,
        'plant_uri': plant,
        'root_uri': root,
    }
    bodies = {
        st_uri: structure,
        infra: {'kind': 'infra'},
        plant: {'kind': 'plant'},
        root: {'kind': 'root'},
    }
    order = {'structure_uri': st_uri}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    out = assert_order_subcomponent_equiv(
        order,
        'structure',
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )
    assert out == structure


def test_order_invoice_fetch_equiv_with_data():
    inv_uri = 'http://n/ldp/cas/ii'
    data_uri = 'http://n/ldp/cas/indata'
    invoice = {'data_uri': data_uri}
    bodies = {inv_uri: invoice, data_uri: b'input-bytes'}
    order = {'invoice_uri': inv_uri}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    out = assert_order_subcomponent_equiv(
        order,
        'invoice',
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )
    assert out == invoice


def test_order_input_invoice_ignores_registry_output_invoice():
    """Order.invoice_uri is input; record.invoice_uri is Executor output."""
    input_inv = 'http://n/ldp/cas/' + ('1' * 64)
    output_inv = 'http://n/ldp/cas/' + ('2' * 64)
    data_uri = 'http://n/ldp/cas/' + ('3' * 64)
    invoice = {'data_uri': data_uri}
    bodies = {
        input_inv: invoice,
        data_uri: b'input-bytes',
        # Output invoice must not be used as mesh locator for input fetch.
        output_inv: {'order_uri': 'http://n/o', 'data_uri': 'http://n/egress'},
    }
    order = {'invoice_uri': input_inv}
    record = {
        'invoice_uri': output_inv,
        'invoice': 'ni:///sha-256;' + ('A' * 43),
        'data_uri': 'http://n/ldp/cas/' + ('e' * 64),
        'data': 'ni:///sha-256;' + ('B' * 43),
    }
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    out = assert_order_subcomponent_equiv(
        order,
        'invoice',
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record=record,
    )
    assert out == invoice
    mesh.catObj.assert_any_call(input_inv)


def test_order_content_equiv_umbrella():
    fn_uri = 'http://n/f'
    st_uri = 'http://n/s'
    inv_uri = 'http://n/i'
    order = {
        'function_uri': fn_uri,
        'structure_uri': st_uri,
        'invoice_uri': inv_uri,
    }
    bodies = {
        fn_uri: {},
        st_uri: {},
        inv_uri: {},
    }
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    assert_order_content_equiv(
        order,
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )


def test_order_fetch_mismatch_raises():
    uri = 'http://n/f'
    mesh = _mesh({uri: {'k': 1}})
    with pytest.raises(AssertionError, match='must match'):
        assert_order_subcomponent_equiv(
            {'function_uri': uri},
            'function',
            content_mesh=mesh,
            http_get_json=lambda u: {'k': 2},
            http_get=lambda u: b'{}',
        )
