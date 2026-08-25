"""BOM subcomponent content equivalence — mesh.cat ≡ HTTP GET."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from cats.network.registry import (
    assert_bom_content_equiv,
    assert_bom_subcomponent_equiv,
    assert_fetch_equiv,
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


def test_bom_invoice_fetch_equiv():
    from cats.network.cas import to_ni

    digest = 'c' * 64
    inv_uri = f'http://n/ldp/cas/{digest}'
    inv_ni = to_ni(digest)
    invoice = {'order_uri': 'http://n/o', 'data_uri': 'http://n/d', 'seed_uri': 'http://n/s'}
    bom = {'invoice_uri': inv_uri}
    bodies = {inv_uri: invoice, inv_ni: invoice}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)
    record = {'invoice': inv_ni}

    out = assert_bom_subcomponent_equiv(
        bom,
        'invoice',
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record=record,
    )
    assert out == invoice
    mesh.catObj.assert_called_with(inv_ni)


def test_bom_log_fetch_equiv():
    log_uri = 'http://n/ldp/cas/log1'
    log_bytes = b'executor-log-bytes'
    bom = {'log_uri': log_uri}
    bodies = {log_uri: log_bytes}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)

    out = assert_bom_subcomponent_equiv(
        bom,
        'log',
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )
    assert out == log_bytes


def test_bom_stage_lineage_fetch_equiv():
    stage_uri = 'http://n/ldp/cas/stage1'
    payload = b'stage-bytes'
    bom = {
        'stageLineage': [
            {'@id': 'ipfs://legacy', 'contentId': 'cidlegacy'},
            {'@id': stage_uri, 'contentId': 'ni-stage'},
        ]
    }
    bodies = {stage_uri: payload, 'ni-stage': payload}
    mesh = _mesh(bodies)
    http_get_json, http_get = _http(bodies)

    assert_bom_content_equiv(
        bom,
        content_mesh=mesh,
        http_get_json=http_get_json,
        http_get=http_get,
    )
    mesh.catObj.assert_any_call('ni-stage')


def test_bom_fetch_equiv_mismatch_raises():
    uri = 'http://n/ldp/cas/x'
    mesh = _mesh({uri: {'k': 1}})
    http_get_json = lambda u: {'k': 2}
    with pytest.raises(AssertionError, match='must match'):
        assert_fetch_equiv(
            'invoice',
            uri,
            content_mesh=mesh,
            http_get_json=http_get_json,
            as_bytes=False,
        )


def test_assert_fetch_equiv_registry_digest_mismatch():
    uri = 'http://n/ldp/cas/aaaa'
    mesh = _mesh({uri: {'k': 1}})
    http_get_json = lambda u: {'k': 1}
    with pytest.raises(AssertionError, match='digest'):
        assert_fetch_equiv(
            'order',
            uri,
            content_mesh=mesh,
            http_get_json=http_get_json,
            record={'order_uri': 'http://n/ldp/orders/bbbb'},
            as_bytes=False,
        )
