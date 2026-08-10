"""WebID profile bridge from Node ``did:key`` (Phase 2a Solid identity).

Emits a minimal JSON-LD WebID document that references the existing
``did:key`` verification method. Data Integrity proofs stay on ``did:key``;
the WebID is the Solid-facing agent identity for WAC.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cats.network.identity.node_did import (
    did_key_verification_method,
    node_did,
)


def webid_uri(cats_home: str | None = None) -> str:
    """Return configured WebID URI or a local file URI under ``.cats/``.

    Resolution:
    1. ``SOLID_WEBID`` env (absolute URI)
    2. Local profile path ``{CATS_HOME}/.cats/webid.jsonld`` as ``file://``
    """
    env = os.environ.get('SOLID_WEBID', '').strip()
    if env:
        return env
    home = cats_home or os.environ.get('CATS_HOME') or str(
        Path(__file__).resolve().parents[3]
    )
    path = Path(home) / '.cats' / 'webid.jsonld'
    return path.resolve().as_uri()


def build_webid_document(
    *,
    cats_home: str | None = None,
    webid: str | None = None,
) -> dict[str, Any]:
    """Build a minimal WebID profile linking the Node ``did:key`` VM."""
    did = node_did(cats_home=cats_home)
    vm = did_key_verification_method(did)
    agent = webid if webid is not None else webid_uri(cats_home)
    multibase = (
        did[len('did:key:'):] if did.startswith('did:key:') else did
    )
    return {
        '@context': {
            'foaf': 'http://xmlns.com/foaf/0.1/',
            'solid': 'http://www.w3.org/ns/solid/terms#',
            'sec': 'https://w3id.org/security#',
            'assertionMethod': {'@id': 'sec:assertionMethod', '@type': '@id'},
            'verificationMethod': {
                '@id': 'sec:verificationMethod',
                '@type': '@id',
            },
            'controller': {'@id': 'sec:controller', '@type': '@id'},
            'publicKeyMultibase': 'sec:publicKeyMultibase',
            'alsoKnownAs': {
                '@id': (
                    'https://www.w3.org/ns/activitystreams#alsoKnownAs'
                ),
                '@type': '@id',
            },
        },
        '@id': agent,
        '@type': 'foaf:Agent',
        'alsoKnownAs': did,
        'assertionMethod': [vm],
        'verificationMethod': [
            {
                '@id': vm,
                '@type': 'sec:Ed25519VerificationKey2020',
                'controller': did,
                'publicKeyMultibase': multibase,
            }
        ],
    }


def write_webid_document(cats_home: str | None = None) -> Path:
    """Write WebID JSON-LD under ``{CATS_HOME}/.cats/webid.jsonld``."""
    home = cats_home or os.environ.get('CATS_HOME') or str(
        Path(__file__).resolve().parents[3]
    )
    path = Path(home) / '.cats' / 'webid.jsonld'
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = build_webid_document(cats_home=home, webid=webid_uri(home))
    path.write_text(
        json.dumps(doc, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    return path
