"""Resolve Invoice stage refs: ``data_stages`` nest preferred, flat fallback."""
from __future__ import annotations

import json
from typing import Any

from cats.network.cas.content_ref import ref_id, ref_uri
from cats.network.cas.digest import from_ni, is_ni_or_digest


def _digest_key(content_id: str | None) -> str | None:
    if not content_id:
        return None
    value = content_id.strip()
    if is_ni_or_digest(value):
        return from_ni(value)
    return value.lower()


def resolve_invoice_data_stages(
    invoice: dict[str, Any],
    *,
    content_mesh=None,
    cats_home: str | None = None,
) -> dict[str, Any]:
    """Return stage equality ids + URIs from Invoice.

    Prefer ``data_stages`` / ``data_stages_uri`` nest with keys
    ``ingressed_data`` / ``integrated_data`` / ``egressed_data``.
    Fall back to flat ``ingress_data`` / ``integration_data`` / ``data``.

    Always prefer Invoice ``data`` / ``data_uri`` for egress equality when set
    (lineage / registry by-data); nest ``egressed_data`` fills gaps only.
    """
    if cats_home is None and content_mesh is not None:
        cats_home = getattr(content_mesh, 'CATS_HOME', None)

    out: dict[str, Any] = {
        'ingress_data_id': None,
        'integration_data_id': None,
        'egress_data_id': None,
        'ingress_data_uri': None,
        'integration_data_uri': None,
        'egress_data_uri': None,
        'data_stages_id': None,
        'data_stages_uri': None,
    }

    data_stages_uri = ref_uri(invoice, 'data_stages')
    data_stages_id = ref_id(invoice, 'data_stages', cats_home=cats_home)
    out['data_stages_uri'] = data_stages_uri
    out['data_stages_id'] = data_stages_id

    nest: dict[str, Any] | None = None
    locator = data_stages_uri or data_stages_id
    if locator and content_mesh is not None:
        try:
            nest = json.loads(content_mesh.cat(locator))
        except Exception:
            nest = None

    if isinstance(nest, dict):
        out['ingress_data_uri'] = ref_uri(nest, 'ingressed_data')
        out['integration_data_uri'] = ref_uri(nest, 'integrated_data')
        out['egress_data_uri'] = ref_uri(nest, 'egressed_data')
        out['ingress_data_id'] = ref_id(
            nest, 'ingressed_data', cats_home=cats_home
        )
        out['integration_data_id'] = ref_id(
            nest, 'integrated_data', cats_home=cats_home
        )
        out['egress_data_id'] = ref_id(nest, 'egressed_data', cats_home=cats_home)
    else:
        # Pre-change flat Invoice siblings.
        out['ingress_data_uri'] = ref_uri(invoice, 'ingress_data')
        out['integration_data_uri'] = ref_uri(invoice, 'integration_data')
        out['ingress_data_id'] = ref_id(
            invoice, 'ingress_data', cats_home=cats_home
        )
        out['integration_data_id'] = ref_id(
            invoice, 'integration_data', cats_home=cats_home
        )

    # Egress equality of record: Invoice.data (may equal nest.egressed).
    egress_uri = ref_uri(invoice, 'data')
    egress_id = ref_id(invoice, 'data', cats_home=cats_home)
    if egress_uri:
        out['egress_data_uri'] = egress_uri
    if egress_id:
        out['egress_data_id'] = egress_id

    return out


def assert_egressed_matches_data(
    invoice: dict[str, Any],
    nest: dict[str, Any],
    *,
    cats_home: str | None = None,
) -> None:
    """Raise ``AssertionError`` if nest egressed digest ≠ Invoice data digest."""
    data_id = ref_id(invoice, 'data', cats_home=cats_home)
    egressed_id = ref_id(nest, 'egressed_data', cats_home=cats_home)
    data_key = _digest_key(data_id)
    egressed_key = _digest_key(egressed_id)
    if not data_key or not egressed_key:
        raise AssertionError(
            f'cannot compare data/egressed digests: data={data_id!r} '
            f'egressed={egressed_id!r}'
        )
    if data_key != egressed_key:
        raise AssertionError(
            f'data_stages.egressed_data digest {egressed_key!r} != '
            f'invoice.data digest {data_key!r}'
        )
