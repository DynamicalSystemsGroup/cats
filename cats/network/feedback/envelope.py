"""Unsigned Control-Feedback BOM packaging (addresses only; VC later)."""
from __future__ import annotations

from typing import Any


def attach_node_uri(package: dict, node_uri: str) -> dict:
    """Set ``node_uri`` on a feedback package (future DID swap)."""
    package['node_uri'] = node_uri
    return package


def build_execution_bom(
    *,
    log_cid: str,
    invoice_cid: str,
    node_uri: str | None = None,
) -> dict[str, Any]:
    """Build post-execute BOM dict from address refs only (no payloads).

    Matches NodeProductFlow §5: Invoice + log. Structure as-executed nesting
    lives on the Invoice (``structure_as_executed_cid``). ``node_uri`` is
    additive Node attribution and must not replace Invoice stage CIDs.
    """
    bom: dict[str, Any] = {
        'log_cid': log_cid,
        'invoice_cid': invoice_cid,
    }
    if node_uri is not None:
        attach_node_uri(bom, node_uri)
    return bom
