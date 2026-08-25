"""Invoice subcomponent content equivalence — mesh.cat ≡ HTTP GET."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from cats.network.cas import to_ni
from cats.network.registry import (
    assert_fetch_equiv,
    assert_invoice_content_equiv,
    assert_invoice_subcomponent_equiv,
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


def test_invoice_order_fetch_equiv():
    digest = 'd' * 64
    order_uri = f'http://n/ldp/cas/{digest}'
    order_ni = to_ni(digest)
    order = {
        'function_uri': 'http://n/f',
        'structure_uri': 'http://n/s',
        'invoice_uri': 'http://n/ii',
    }
    invoice = {'order_uri': order_uri}
    bodies = {order_uri: order, order_ni: order}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    out = assert_invoice_subcomponent_equiv(
        invoice,
        'order',
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record={'order': order_ni},
    )
    assert out == order
    mesh.catObj.assert_called_with(order_ni)


def test_invoice_data_fetch_equiv():
    data_uri = 'http://n/ldp/cas/d1'
    data = b'egress-bytes'
    invoice = {'data_uri': data_uri}
    bodies = {data_uri: data}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    out = assert_invoice_subcomponent_equiv(
        invoice,
        'data',
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )
    assert out == data


def test_invoice_seed_fetch_equiv():
    seed_uri = 'http://n/ldp/cas/s1'
    seed = {'k': 1}
    invoice = {'seed_uri': seed_uri}
    bodies = {seed_uri: json.dumps(seed).encode('utf-8')}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    out = assert_invoice_subcomponent_equiv(
        invoice,
        'seed',
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )
    assert out == bodies[seed_uri]


def test_invoice_data_stages_fetch_equiv():
    nest_uri = 'http://n/ldp/cas/stages'
    e_uri = 'http://n/ldp/cas/e'
    i_uri = 'http://n/ldp/cas/i'
    g_uri = 'http://n/ldp/cas/g'
    nest = {
        'egressed_data_uri': e_uri,
        'integrated_data_uri': i_uri,
        'ingressed_data_uri': g_uri,
    }
    bodies = {
        nest_uri: nest,
        e_uri: b'e',
        i_uri: b'i',
        g_uri: b'g',
    }
    invoice = {'data_stages_uri': nest_uri}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    out = assert_invoice_subcomponent_equiv(
        invoice,
        'data_stages',
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )
    assert out == nest


def test_invoice_structure_as_executed_fetch_equiv():
    uri = 'http://n/ldp/cas/sae'
    sae = {
        'plant_as_executed_uri': 'http://n/p',
        'infrastructure_as_executed_uri': 'http://n/infra',
    }
    invoice = {'structure_as_executed_uri': uri}
    bodies = {uri: sae}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    out = assert_invoice_subcomponent_equiv(
        invoice,
        'structure_as_executed',
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )
    assert out == sae


def test_invoice_data_registry_digest_agreement():
    digest = 'a' * 64
    data_uri = f'http://n/ldp/cas/{digest}'
    data = b'payload'
    bodies = {data_uri: data, to_ni(digest): data}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    assert_fetch_equiv(
        'data',
        data_uri,
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record={'data': to_ni(digest), 'data_uri': data_uri},
        as_bytes=True,
    )


def test_invoice_data_registry_digest_mismatch():
    data_uri = 'http://n/ldp/cas/' + ('a' * 64)
    mesh = _mesh({data_uri: b'x'})
    http_get_json, http_get = _http({data_uri: b'x'})
    with pytest.raises(AssertionError, match='data_uri'):
        assert_fetch_equiv(
            'data',
            data_uri,
            content_mesh=mesh,
            http_get_json=http_get_json,
            http_get=http_get,
            record={'data_uri': 'http://n/ldp/cas/' + ('b' * 64)},
            as_bytes=True,
        )


def test_invoice_content_equiv_umbrella():
    order_uri = 'http://n/o'
    data_uri = 'http://n/d'
    seed_uri = 'http://n/s'
    invoice = {
        'order_uri': order_uri,
        'data_uri': data_uri,
        'seed_uri': seed_uri,
    }
    bodies = {
        order_uri: {'function_uri': 'http://n/f'},
        data_uri: b'data',
        seed_uri: b'seed',
    }
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    assert_invoice_content_equiv(
        invoice,
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )


def test_invoice_fetch_mismatch_raises():
    uri = 'http://n/o'
    mesh = _mesh({uri: {'k': 1}})
    with pytest.raises(AssertionError, match='must match'):
        assert_invoice_subcomponent_equiv(
            {'order_uri': uri},
            'order',
            content_mesh=mesh,
            http_get_json=lambda u: {'k': 2},
            http_get=lambda u: b'{}',
        )
