"""Order subcomponent content equivalence — mesh.cat ≡ HTTP GET."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from cats.network.registry import (
    assert_order_content_equiv,
    assert_order_function_content_equiv,
    assert_order_invoice_content_equiv,
    assert_order_structure_content_equiv,
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
    assert_order_function_content_equiv(
        function,
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )


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
    assert_order_structure_content_equiv(
        structure,
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )


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
    assert_order_invoice_content_equiv(
        invoice,
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )


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


def test_order_ebom_stems_fetch_equiv():
    fn_sbom_uri = 'http://n/ldp/cas/fnsbom'
    st_sbom_uri = 'http://n/ldp/cas/stsbom'
    nest_uri = 'http://n/ldp/cas/indatasbom'
    dcat_uri = 'http://n/ldp/cas/dcat'
    spdx_uri = 'http://n/ldp/cas/spdx'
    fn_sbom = {'spdxVersion': '3.0.1', 'name': 'function'}
    st_sbom = {'spdxVersion': '3.0.1', 'name': 'structure'}
    nest = {'dcat_uri': dcat_uri, 'spdx_uri': spdx_uri}
    dcat = {'@type': 'dcat:Catalog'}
    spdx = {'spdxVersion': '3.0.1', 'name': 'input'}
    order = {
        'function_sbom_uri': fn_sbom_uri,
        'structure_sbom_uri': st_sbom_uri,
        'input_data_sbom_uri': nest_uri,
    }
    bodies = {
        fn_sbom_uri: fn_sbom,
        st_sbom_uri: st_sbom,
        nest_uri: nest,
        dcat_uri: dcat,
        spdx_uri: spdx,
    }
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    assert (
        assert_order_subcomponent_equiv(
            order,
            'function_sbom',
            content_mesh=mesh,
            http_get_json=http_get_json,
            http_get=http_get,
        )
        == fn_sbom
    )
    assert (
        assert_order_subcomponent_equiv(
            order,
            'structure_sbom',
            content_mesh=mesh,
            http_get_json=http_get_json,
            http_get=http_get,
        )
        == st_sbom
    )
    assert (
        assert_order_subcomponent_equiv(
            order,
            'input_data_sbom',
            content_mesh=mesh,
            http_get_json=http_get_json,
            http_get=http_get,
        )
        == nest
    )
    assert_order_content_equiv(
        order,
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )


def test_order_ebom_stems_missing_still_pass_umbrella():
    order = {
        'function_uri': 'http://n/f',
        'structure_uri': 'http://n/s',
        'invoice_uri': 'http://n/i',
    }
    bodies = {'http://n/f': {}, 'http://n/s': {}, 'http://n/i': {}}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    assert (
        assert_order_subcomponent_equiv(
            order,
            'function_sbom',
            content_mesh=mesh,
            http_get_json=http_get_json,
            http_get=http_get,
        )
        is None
    )
    assert_order_content_equiv(
        order,
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )


def test_order_ebom_stem_unfetchable_fails():
    order = {'function_sbom_uri': 'http://n/ldp/cas/missing'}
    mesh = _mesh({})
    http_get_json, http_get = _http({})
    with pytest.raises((AssertionError, KeyError)):
        assert_order_subcomponent_equiv(
            order,
            'function_sbom',
            content_mesh=mesh,
            http_get_json=http_get_json,
            http_get=http_get,
        )


def test_order_input_data_sbom_missing_dcat_fails():
    nest_uri = 'http://n/ldp/cas/indatasbom'
    nest = {'spdx_uri': 'http://n/ldp/cas/spdx'}
    order = {'input_data_sbom_uri': nest_uri}
    bodies = {nest_uri: nest, 'http://n/ldp/cas/spdx': {'spdxVersion': '3.0.1'}}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    with pytest.raises(AssertionError, match='dcat_uri'):
        assert_order_subcomponent_equiv(
            order,
            'input_data_sbom',
            content_mesh=mesh,
            http_get_json=http_get_json,
            http_get=http_get,
        )


def test_order_input_data_sbom_missing_spdx_fails():
    nest_uri = 'http://n/ldp/cas/indatasbom'
    nest = {'dcat_uri': 'http://n/ldp/cas/dcat'}
    order = {'input_data_sbom_uri': nest_uri}
    bodies = {nest_uri: nest, 'http://n/ldp/cas/dcat': {'@type': 'dcat:Catalog'}}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    with pytest.raises(AssertionError, match='spdx_uri'):
        assert_order_subcomponent_equiv(
            order,
            'input_data_sbom',
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
