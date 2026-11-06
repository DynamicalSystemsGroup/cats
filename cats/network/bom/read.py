"""P2 read path: resolve Invoice / Order stems from an execute envelope.

Does not mint or mutate Order, Invoice, or the signed ExecutionBom.
Never reads a top-level execute-response ``invoice_uri``.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cats.network.cas.content_ref import (
    content_id_from_uri,
    is_http_uri,
    ref_id,
    ref_uri,
)
from cats.network.cas.digest import is_ni_or_digest
from cats.network.registry.handoff import resolve_handoff_invoice_uri

FetchJson = Callable[[str], Any]


def invoice_uri_from_response(
    cat_response: dict[str, Any],
    record: dict[str, Any] | None = None,
) -> str | None:
    """Signed ``bom.invoice_uri``, then registry / locators.

    Execute HTTP envelopes omit top-level ``invoice_uri``; a top-level field
    is ignored (same as ``resolve_handoff_invoice_uri``).
    """
    return resolve_handoff_invoice_uri(cat_response or {}, record or {})


def stem_uri(obj: dict[str, Any], stem: str) -> str | None:
    """``{stem}_uri`` when present."""
    if not isinstance(obj, dict):
        return None
    return ref_uri(obj, stem)


def stem_id(
    obj: dict[str, Any],
    stem: str,
    *,
    cats_home: str | None = None,
) -> str | None:
    """Equality id for ``stem`` (``ni:`` / path digest / legacy cid)."""
    if not isinstance(obj, dict):
        return None
    return ref_id(obj, stem, cats_home=cats_home)


def fetch_key(
    token: str,
    *,
    cats_home: str | None = None,
) -> str:
    """Prefer a local CAS id so fetch does not require a live Node HTTP GET."""
    raw = (token or '').strip()
    if not raw:
        return raw
    if is_http_uri(raw):
        found = content_id_from_uri(raw, cats_home=cats_home)
        if found:
            return found
    return raw


def from_flat_or_fetch(
    parent: dict[str, Any],
    stem: str,
    fetch: FetchJson | None = None,
    *,
    cats_home: str | None = None,
) -> Any:
    """Prefer ``parent['flat'][stem]``, else ``fetch`` of the stem locator.

    Projectors must not depend on ``flatten_bom`` inlining a given depth.
    """
    if not isinstance(parent, dict):
        return None
    bag = parent.get('flat')
    if isinstance(bag, dict) and isinstance(bag.get(stem), dict):
        return bag[stem]
    if fetch is None:
        return None
    token = stem_uri(parent, stem) or stem_id(parent, stem, cats_home=cats_home)
    if not token:
        return None
    return fetch(fetch_key(token, cats_home=cats_home))


def order_from_invoice(
    invoice: dict[str, Any],
    fetch: FetchJson | None = None,
    *,
    cats_home: str | None = None,
) -> dict[str, Any] | None:
    payload = from_flat_or_fetch(invoice, 'order', fetch, cats_home=cats_home)
    return payload if isinstance(payload, dict) else None


def function_from_order(
    order: dict[str, Any],
    fetch: FetchJson | None = None,
    *,
    cats_home: str | None = None,
) -> dict[str, Any] | None:
    payload = from_flat_or_fetch(order, 'function', fetch, cats_home=cats_home)
    return payload if isinstance(payload, dict) else None


def structure_from_order(
    order: dict[str, Any],
    fetch: FetchJson | None = None,
    *,
    cats_home: str | None = None,
) -> dict[str, Any] | None:
    payload = from_flat_or_fetch(order, 'structure', fetch, cats_home=cats_home)
    return payload if isinstance(payload, dict) else None


def structure_as_executed_from_invoice(
    invoice: dict[str, Any],
    fetch: FetchJson | None = None,
    *,
    cats_home: str | None = None,
) -> dict[str, Any] | None:
    payload = from_flat_or_fetch(
        invoice, 'structure_as_executed', fetch, cats_home=cats_home
    )
    return payload if isinstance(payload, dict) else None


def data_stages_from_invoice(
    invoice: dict[str, Any],
    fetch: FetchJson | None = None,
    *,
    cats_home: str | None = None,
) -> dict[str, Any] | None:
    payload = from_flat_or_fetch(
        invoice, 'data_stages', fetch, cats_home=cats_home
    )
    return payload if isinstance(payload, dict) else None


def runtime_sbom_from_invoice(
    invoice: dict[str, Any],
    fetch: FetchJson | None = None,
    *,
    cats_home: str | None = None,
) -> dict[str, Any] | None:
    payload = from_flat_or_fetch(
        invoice, 'runtime_sbom', fetch, cats_home=cats_home
    )
    return payload if isinstance(payload, dict) else None


def seed_from_invoice(
    invoice: dict[str, Any],
    fetch: FetchJson | None = None,
    *,
    cats_home: str | None = None,
) -> dict[str, Any] | None:
    payload = from_flat_or_fetch(invoice, 'seed', fetch, cats_home=cats_home)
    return payload if isinstance(payload, dict) else None


def require_ni(content_id: str | None, *, label: str) -> str:
    """Canonical ``ni:`` for a digest id; raise if missing / not a digest."""
    if not isinstance(content_id, str) or not content_id.strip():
        raise ValueError(f'{label} is required')
    token = content_id.strip()
    if is_http_uri(token):
        found = content_id_from_uri(token)
        if found and is_ni_or_digest(found):
            from cats.network.cas.content_ref import equality_id

            return equality_id(found)
        raise ValueError(f'{label} HTTP locator is not a CAS digest: {token!r}')
    if not is_ni_or_digest(token):
        raise ValueError(f'{label} must be ni: or hex sha-256: {token!r}')
    from cats.network.cas.content_ref import equality_id

    return equality_id(token)
