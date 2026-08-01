"""Control-Feedback BOM packaging (JSON-LD + PROV-O + Data Integrity).

Phase 1: address refs + DID attribution.
Phase 1b: eddsa-jcs-2022 proof via ``sign_execution_bom``.
"""
from __future__ import annotations

from typing import Any

from cats.network.feedback.data_integrity import (
    DATA_INTEGRITY_CONTEXT,
    sign_document,
    verify_document,
)
from cats.network.identity.node_did import (
    did_key_verification_method,
    load_node_signing_material,
)

# Compact JSON-LD context for ExecutionBom.
_EXECUTION_BOM_CONTEXT: list[Any] = [
    'https://www.w3.org/ns/prov#',
    {
        'cats': 'https://dynamicalsystemsgroup.github.io/cats/ns#',
        'invoice_cid': 'cats:invoice_cid',
        'log_cid': 'cats:log_cid',
        'node_did': 'cats:node_did',
    },
]


def attach_node_did(package: dict, node_did: str) -> dict:
    """Set ``node_did`` on a feedback package (DID attribution)."""
    package['node_did'] = node_did
    return package


def build_execution_bom(
    *,
    log_cid: str,
    invoice_cid: str,
    node_did: str | None = None,
) -> dict[str, Any]:
    """Build post-execute BOM dict from address refs only (no payloads).

    Matches ControlFeedbackLoop §5: Invoice + log. Structure as-executed nesting
    lives on the Invoice (``structure_as_executed_cid``). ``node_did`` is
    additive Node attribution and must not replace Invoice stage CIDs.

    Shape is JSON-LD + PROV-O (unsigned until ``sign_execution_bom``).
    ``bom_cid`` is minted by the caller and must not appear inside this object.
    """
    bom: dict[str, Any] = {
        '@context': list(_EXECUTION_BOM_CONTEXT),
        '@type': ['prov:Entity', 'cats:ExecutionBom'],
        'invoice_cid': invoice_cid,
        'log_cid': log_cid,
        'prov:wasGeneratedBy': {
            '@type': 'prov:Activity',
            'prov:used': {'@id': f'ipfs://{invoice_cid}'},
        },
    }
    if node_did is not None:
        attach_node_did(bom, node_did)
        bom['prov:wasAttributedTo'] = {'@id': node_did}
    return bom


def sign_execution_bom(
    bom: dict[str, Any],
    *,
    cats_home: str | None = None,
) -> dict[str, Any]:
    """Sign an ExecutionBom with eddsa-jcs-2022 using local Node key material.

    Ensures ``bom['node_did']`` matches the signing keyfile DID (and
    ``CAT_NODE_DID`` when set). Extends ``@context`` with the Data Integrity
    v2 context when missing.
    """
    did, private_key = load_node_signing_material(cats_home)
    node = bom.get('node_did')
    if node is None:
        attach_node_did(bom, did)
        bom['prov:wasAttributedTo'] = {'@id': did}
    elif node != did:
        raise ValueError(
            f'bom.node_did ({node!r}) does not match signing DID ({did!r})'
        )

    ctx = bom.get('@context')
    if isinstance(ctx, list):
        if DATA_INTEGRITY_CONTEXT not in ctx:
            bom = {**bom, '@context': list(ctx) + [DATA_INTEGRITY_CONTEXT]}
    elif ctx is None:
        bom = {
            **bom,
            '@context': list(_EXECUTION_BOM_CONTEXT) + [DATA_INTEGRITY_CONTEXT],
        }
    else:
        bom = {
            **bom,
            '@context': [ctx, DATA_INTEGRITY_CONTEXT],
        }

    return sign_document(
        bom,
        private_key,
        did_key_verification_method(did),
    )


def verify_execution_bom(bom: dict[str, Any]) -> None:
    """Verify the Data Integrity proof on an ExecutionBom; raise on failure."""
    verify_document(bom)
