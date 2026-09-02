"""As-executed SAE bind, nest slots, and Plant snapshot."""
from __future__ import annotations

import pytest

from cats.network.cas import to_ni
from cats.network.feedback import build_execution_bom
from cats.network.registry import (
    assert_infrastructure_as_executed_slots,
    assert_plant_as_executed_snapshot,
    assert_structure_as_executed_bind,
    assert_structure_as_executed_slots,
)


def _store(**bodies):
    def http_get_json(url):
        if url not in bodies:
            raise KeyError(url)
        return bodies[url]

    return http_get_json


def _plant(**overrides):
    digest = 'a' * 64
    body = {
        'applied_structure_id': to_ni(digest),
        'kind_cluster_name': 'cats',
        'kubeconfig_context': 'kind-cats',
        'ray_dashboard_address': 'http://127.0.0.1:8265',
        'ray_release_name': 'raycluster',
        'rebuilt': False,
    }
    body.update(overrides)
    return body


def test_structure_as_executed_slots_ok_and_fail():
    ok = {
        'plant_as_executed_uri': 'http://n/p',
        'infrastructure_as_executed_uri': 'http://n/i',
    }
    assert_structure_as_executed_slots(ok)
    with pytest.raises(AssertionError, match='structure_as_executed missing'):
        assert_structure_as_executed_slots({'plant_as_executed_uri': 'http://n/p'})


def test_infrastructure_as_executed_slots_ok_and_fail():
    assert_infrastructure_as_executed_slots(
        {'object_store_as_executed_uri': 'http://n/os'}
    )
    with pytest.raises(AssertionError, match='infrastructure_as_executed missing'):
        assert_infrastructure_as_executed_slots({})


def test_structure_as_executed_bind_ok_identity_and_payload():
    sae_uri = 'http://n/ldp/cas/sae1'
    sae = {
        'plant_as_executed_uri': 'http://n/p',
        'infrastructure_as_executed_uri': 'http://n/i',
    }
    bom = build_execution_bom(
        log_id='log1',
        invoice_id='inv1',
        order_id='ord1',
        ingress_data_id='ingress',
        integration_data_id='integration',
        data_id='egress',
        structure_as_executed_id='sae1',
        structure_as_executed_uri=sae_uri,
        ingress_data_uri='http://n/ldp/cas/ingress',
        integration_data_uri='http://n/ldp/cas/integration',
        data_uri='http://n/ldp/cas/egress',
        invoice_uri='http://n/ldp/cas/inv1',
        order_uri='http://n/ldp/cas/ord1',
    )
    entity = assert_structure_as_executed_bind(
        bom,
        structure_as_executed_uri=sae_uri,
        http_get_json=_store(**{sae_uri: sae}),
        expected_structure_as_executed=sae,
    )
    assert entity['@id'] == sae_uri
    assert 'prov:wasDerivedFrom' not in entity


def test_structure_as_executed_bind_digest_across_collections():
    bom = {
        'stageLineage': [
            {
                '@id': 'http://n/ldp/cas/ingress',
                'prov:wasDerivedFrom': {'@id': 'http://n/ldp/cas/input'},
            },
            {'@id': 'http://n/ldp/cas/sae1', 'contentId': 'sae1'},
        ]
    }
    entity = assert_structure_as_executed_bind(
        bom,
        structure_as_executed_uri='http://n/ldp/invoices/sae1',
    )
    assert entity['contentId'] == 'sae1'


def test_structure_as_executed_bind_rejects_payload_hop():
    bom = {
        'stageLineage': [
            {
                '@id': 'http://n/ldp/cas/sae1',
                'prov:wasDerivedFrom': {'@id': 'http://n/ldp/cas/input'},
            }
        ]
    }
    with pytest.raises(AssertionError, match='wasDerivedFrom'):
        assert_structure_as_executed_bind(
            bom,
            structure_as_executed_uri='http://n/ldp/cas/sae1',
        )


def test_structure_as_executed_bind_missing_entity_raises():
    bom = build_execution_bom(
        log_id='log1',
        invoice_id='inv1',
        ingress_data_id='ingress',
        ingress_data_uri='http://n/ldp/cas/ingress',
    )
    with pytest.raises(AssertionError, match='no stageLineage entity'):
        assert_structure_as_executed_bind(
            bom,
            structure_as_executed_uri='http://n/ldp/cas/sae1',
        )


def test_plant_as_executed_snapshot_ok_and_structure_id():
    digest = 'a' * 64
    plant = _plant()
    assert_plant_as_executed_snapshot(plant, structure_id=to_ni(digest))
    assert_plant_as_executed_snapshot(plant, structure_id=digest)


def test_plant_as_executed_snapshot_missing_key_raises():
    plant = _plant()
    del plant['rebuilt']
    with pytest.raises(AssertionError, match='missing'):
        assert_plant_as_executed_snapshot(plant)


def test_plant_as_executed_snapshot_structure_mismatch_raises():
    with pytest.raises(AssertionError, match='applied_structure_id'):
        assert_plant_as_executed_snapshot(
            _plant(),
            structure_id=to_ni('b' * 64),
        )
