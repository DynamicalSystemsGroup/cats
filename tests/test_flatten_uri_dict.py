"""Recursive ``*_uri`` flatten helper."""
from __future__ import annotations

from cats.network.cas import flatten_uri_dict


def test_flatten_inlines_uri_and_drops_uri_key():
    store = {
        'http://x/a': {'n': 1, 'child_uri': 'http://x/b'},
        'http://x/b': {'n': 2},
    }

    def fetch(stem, uri):
        return store[uri]

    raw = {'label': 'root', 'a_uri': 'http://x/a', 'keep': True}
    flat = flatten_uri_dict(raw, fetch, max_depth=2)
    assert flat == {
        'label': 'root',
        'keep': True,
        'a': {'n': 1, 'child': {'n': 2}},
    }
    assert 'a_uri' not in flat
    assert 'child_uri' not in flat['a']


def test_flatten_respects_max_depth():
    store = {
        'http://x/a': {'child_uri': 'http://x/b'},
        'http://x/b': {'n': 2},
    }

    def fetch(stem, uri):
        return store[uri]

    flat = flatten_uri_dict({'a_uri': 'http://x/a'}, fetch, max_depth=1)
    assert flat == {'a': {'child_uri': 'http://x/b'}}


def test_flatten_stems_filter():
    store = {
        'http://x/order': {'k': 'order'},
        'http://x/data': {'k': 'data'},
    }

    def fetch(stem, uri):
        return store[uri]

    raw = {'order_uri': 'http://x/order', 'data_uri': 'http://x/data'}
    flat = flatten_uri_dict(raw, fetch, max_depth=1, stems={'order'})
    assert flat == {
        'order': {'k': 'order'},
        'data_uri': 'http://x/data',
    }


def test_flatten_cycle_keeps_uri():
    store = {
        'http://x/inv': {'order_uri': 'http://x/ord'},
        'http://x/ord': {'invoice_uri': 'http://x/inv'},
    }
    calls: list[str] = []

    def fetch(stem, uri):
        calls.append(uri)
        return store[uri]

    flat = flatten_uri_dict(
        {'invoice_uri': 'http://x/inv'},
        fetch,
        max_depth=4,
        stems={'invoice', 'order'},
    )
    assert flat['invoice']['order']['invoice_uri'] == 'http://x/inv'
    assert calls.count('http://x/inv') == 1
    assert calls.count('http://x/ord') == 1


def test_flatten_drops_legacy_cid_when_expanding():
    def fetch(stem, uri):
        return {'ok': True}

    raw = {'data_uri': 'http://x/d', 'data_cid': 'legacy'}
    flat = flatten_uri_dict(raw, fetch, max_depth=1)
    assert flat == {'data': {'ok': True}}


def test_flatten_non_dict_payload():
    def fetch(stem, uri):
        return b'bytes'

    flat = flatten_uri_dict({'data_uri': 'http://x/d'}, fetch, max_depth=1)
    assert flat == {'data': b'bytes'}
