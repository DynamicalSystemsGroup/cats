"""Feedback / identity preparatory seams (no W3C libs; no AddressStore)."""

from cats.network.feedback import attach_node_uri, build_execution_bom
from cats.network.identity import node_uri


def test_build_execution_bom_includes_node_uri_and_cid_keys():
    bom = build_execution_bom(
        log_cid='log',
        invoice_cid='inv',
        node_uri='http://127.0.0.1:5000',
    )
    assert bom == {
        'log_cid': 'log',
        'invoice_cid': 'inv',
        'node_uri': 'http://127.0.0.1:5000',
    }
    assert 'plant_snapshot_cid' not in bom
    assert 'infrastructure_snapshot_cid' not in bom


def test_build_execution_bom_omits_node_uri_when_none():
    bom = build_execution_bom(
        log_cid='log',
        invoice_cid='inv',
    )
    assert 'node_uri' not in bom
    assert set(bom) == {'log_cid', 'invoice_cid'}


def test_attach_node_uri_sets_field():
    pkg = attach_node_uri({'invoice_cid': 'inv'}, 'http://node:5000')
    assert pkg['node_uri'] == 'http://node:5000'


def test_node_uri_respects_env(monkeypatch):
    monkeypatch.setenv('CAT_NODE_HOST', '10.0.0.2')
    monkeypatch.setenv('CAT_NODE_PORT', '6000')
    assert node_uri() == 'http://10.0.0.2:6000'


def test_node_uri_defaults(monkeypatch):
    monkeypatch.delenv('CAT_NODE_HOST', raising=False)
    monkeypatch.delenv('CAT_NODE_PORT', raising=False)
    assert node_uri() == 'http://127.0.0.1:5000'
