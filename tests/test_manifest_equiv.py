"""Directory-manifest / stageLineage payload content-address equivalence."""
from __future__ import annotations

import pytest

from cats.network.cas import (
    MANIFEST_TYPE,
    assert_directory_manifest_equiv,
    assert_stage_lineage_payload_equiv,
)


def _store(bodies: dict):
    def http_get_json(url):
        if url not in bodies:
            raise KeyError(url)
        return bodies[url]

    return http_get_json


def _manifest(entries: dict[str, str]) -> dict:
    return {'@type': MANIFEST_TYPE, 'entries': dict(entries)}


def test_directory_manifest_equiv_same_uri():
    uri = 'http://n/ldp/cas/a'
    assert_directory_manifest_equiv(
        uri, uri, http_get_json=_store({})
    )


def test_directory_manifest_equiv_same_entries_different_uri():
    entries = {'x.csv': 'ni:///sha-256;aaaa'}
    a = 'http://n/ldp/cas/a'
    b = 'http://n/ldp/cas/b'
    bodies = {a: _manifest(entries), b: _manifest(dict(entries))}
    assert_directory_manifest_equiv(a, b, http_get_json=_store(bodies))


def test_directory_manifest_equiv_mismatch_raises():
    a = 'http://n/ldp/cas/a'
    b = 'http://n/ldp/cas/b'
    bodies = {
        a: _manifest({'x.csv': 'ni:///sha-256;aaaa'}),
        b: _manifest({'x.csv': 'ni:///sha-256;bbbb'}),
    }
    with pytest.raises(AssertionError, match='content mismatch'):
        assert_directory_manifest_equiv(a, b, http_get_json=_store(bodies))


def test_stage_lineage_payload_equiv_ok():
    input_uri = 'http://n/input'
    ingress_uri = 'http://n/ingress'
    integration_uri = 'http://n/integration'
    egress_uri = 'http://n/egress'
    entries_in = {'f.csv': 'ni:///sha-256;1111'}
    # ingress copies input; later stages may differ (transform) but
    # wasDerivedFrom must point at the prior stage URI/content.
    bodies = {
        input_uri: _manifest(entries_in),
        ingress_uri: _manifest(dict(entries_in)),
        integration_uri: _manifest({'f.csv': 'ni:///sha-256;2222'}),
        egress_uri: _manifest({'f.csv': 'ni:///sha-256;3333'}),
    }
    bom = {
        'stageLineage': [
            {
                '@id': ingress_uri,
                'prov:wasDerivedFrom': {'@id': input_uri},
            },
            {
                '@id': integration_uri,
                'prov:wasDerivedFrom': {'@id': ingress_uri},
            },
            {
                '@id': egress_uri,
                'prov:wasDerivedFrom': {'@id': integration_uri},
            },
            {'@id': 'http://n/sae'},  # no wasDerivedFrom — skipped
        ]
    }
    assert_stage_lineage_payload_equiv(
        bom, http_get_json=_store(bodies)
    )


def test_stage_lineage_payload_equiv_bad_pointer_raises():
    ingress_uri = 'http://n/ingress'
    integration_uri = 'http://n/integration'
    wrong = 'http://n/wrong'
    bodies = {
        ingress_uri: _manifest({'a': 'ni:///sha-256;1'}),
        wrong: _manifest({'a': 'ni:///sha-256;9'}),
        integration_uri: _manifest({'a': 'ni:///sha-256;2'}),
    }
    bom = {
        'stageLineage': [
            {
                '@id': ingress_uri,
                'prov:wasDerivedFrom': {'@id': ingress_uri},
            },
            {
                '@id': integration_uri,
                'prov:wasDerivedFrom': {'@id': wrong},
            },
        ]
    }
    with pytest.raises(AssertionError, match='content mismatch'):
        assert_stage_lineage_payload_equiv(
            bom, http_get_json=_store(bodies)
        )
