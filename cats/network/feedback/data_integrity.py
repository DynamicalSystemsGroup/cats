"""W3C Data Integrity eddsa-jcs-2022 sign/verify (Phase 1b).

Spec: https://www.w3.org/TR/vc-di-eddsa/#eddsa-jcs-2022
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from cats.network.identity.multibase import multibase_z_decode, multibase_z_encode
from cats.network.identity.node_did import ED25519_PUB_PREFIX

CRYPTOSUITE = 'eddsa-jcs-2022'
PROOF_TYPE = 'DataIntegrityProof'
DATA_INTEGRITY_CONTEXT = 'https://w3id.org/security/data-integrity/v2'


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _context_list(ctx: Any) -> list:
    if ctx is None:
        return []
    if isinstance(ctx, list):
        return list(ctx)
    return [ctx]


def _context_starts_with(document_ctx: Any, proof_ctx: Any) -> bool:
    doc = _context_list(document_ctx)
    proof = _context_list(proof_ctx)
    if len(doc) < len(proof):
        return False
    return doc[: len(proof)] == proof


def _public_key_from_did_key_vm(verification_method: str) -> Ed25519PublicKey:
    """Resolve Ed25519 public key from ``did:key:…#…`` verificationMethod."""
    did_part, _, fragment = verification_method.partition('#')
    if not did_part.startswith('did:key:'):
        raise ValueError(
            f'Unsupported verificationMethod (need did:key): {verification_method!r}'
        )
    multibase = fragment if fragment else did_part[len('did:key:'):]
    if not multibase.startswith('z'):
        raise ValueError(
            f'verificationMethod fragment must be multibase z-…: '
            f'{verification_method!r}'
        )
    raw = multibase_z_decode(multibase)
    if not raw.startswith(ED25519_PUB_PREFIX):
        raise ValueError(
            f'verificationMethod is not ed25519-pub multicodec: {verification_method!r}'
        )
    pub = raw[len(ED25519_PUB_PREFIX):]
    if len(pub) != 32:
        raise ValueError(
            f'Ed25519 public key must be 32 bytes, got {len(pub)}'
        )
    return Ed25519PublicKey.from_public_bytes(pub)


def _hash_data(proof_config: dict, unsecured_document: dict) -> bytes:
    canonical_proof = rfc8785.dumps(proof_config)
    canonical_doc = rfc8785.dumps(unsecured_document)
    return (
        hashlib.sha256(canonical_proof).digest()
        + hashlib.sha256(canonical_doc).digest()
    )


def sign_document(
    document: dict[str, Any],
    private_key: Ed25519PrivateKey,
    verification_method: str,
    *,
    created: str | None = None,
) -> dict[str, Any]:
    """Attach an ``eddsa-jcs-2022`` Data Integrity proof to ``document``."""
    unsecured = {k: deepcopy(v) for k, v in document.items() if k != 'proof'}
    proof_options: dict[str, Any] = {
        'type': PROOF_TYPE,
        'cryptosuite': CRYPTOSUITE,
        'created': created or _utc_now_iso(),
        'verificationMethod': verification_method,
        'proofPurpose': 'assertionMethod',
    }
    if '@context' in unsecured:
        proof_options['@context'] = deepcopy(unsecured['@context'])

    if proof_options['type'] != PROOF_TYPE or proof_options['cryptosuite'] != CRYPTOSUITE:
        raise ValueError('Invalid proof options for eddsa-jcs-2022')

    hash_data = _hash_data(proof_options, unsecured)
    signature = private_key.sign(hash_data)
    proof = {**proof_options, 'proofValue': multibase_z_encode(signature)}
    secured = deepcopy(unsecured)
    secured['proof'] = proof
    return secured


def verify_document(document: dict[str, Any]) -> None:
    """Verify an ``eddsa-jcs-2022`` proof on ``document``; raise on failure."""
    if 'proof' not in document:
        raise ValueError('Document has no proof')
    proof = document['proof']
    if not isinstance(proof, dict):
        raise ValueError('proof must be an object')
    if proof.get('type') != PROOF_TYPE:
        raise ValueError(f'Unsupported proof type: {proof.get("type")!r}')
    if proof.get('cryptosuite') != CRYPTOSUITE:
        raise ValueError(
            f'Unsupported cryptosuite: {proof.get("cryptosuite")!r}'
        )
    proof_value = proof.get('proofValue')
    if not isinstance(proof_value, str) or not proof_value:
        raise ValueError('proof.proofValue missing')

    proof_options = {k: deepcopy(v) for k, v in proof.items() if k != 'proofValue'}
    unsecured = {k: deepcopy(v) for k, v in document.items() if k != 'proof'}

    if '@context' in proof_options:
        if not _context_starts_with(
            unsecured.get('@context'), proof_options['@context']
        ):
            raise ValueError(
                'Document @context does not start with proof @context'
            )
        unsecured['@context'] = deepcopy(proof_options['@context'])

    hash_data = _hash_data(proof_options, unsecured)
    signature = multibase_z_decode(proof_value)
    public_key = _public_key_from_did_key_vm(proof['verificationMethod'])
    try:
        public_key.verify(signature, hash_data)
    except InvalidSignature as exc:
        raise ValueError('Data Integrity proof verification failed') from exc
