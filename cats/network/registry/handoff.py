"""Control-plane handoff coherence — response → registry → BOM → Invoice → Order.

**Not** registry index parity (Python ↔ ``GET /ldp/registry/…``). **Not**
flattening (``flatten_uri_dict`` stays with the caller).

Asserts the labeled CAT0 handoff invariants and returns loaded envelopes for
inspect / flatten cells.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

HttpGetJson = Callable[[str], Any]
"""``http_get_json(url_or_path) -> dict`` (absolute http(s) or Node-relative)."""

_REG_STEM = {
    'order': 'order',
    'data': 'data',
    'seed': 'seed',
    'data_stages': 'data_stages',
    'function': 'function',
    'structure': 'structure',
}


def _uri_digest(uri: str) -> str:
    """Last path segment lowercased (orders vs cas collection path)."""
    return uri.rstrip('/').rsplit('/', 1)[-1].lower()


def resolve_handoff_invoice_uri(
    cat_response: dict[str, Any],
    record: dict[str, Any],
) -> str | None:
    """Prefer response, then BOM body, then registry record / locators."""
    locs = record.get('locators') or {}
    candidates = (
        cat_response.get('invoice_uri'),
        (cat_response.get('bom') or {}).get('invoice_uri'),
        record.get('invoice_uri'),
        locs.get('invoice_uri'),
    )
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def make_content_fetch_ref(
    *,
    record: dict[str, Any],
    content_mesh,
    http_get_json: HttpGetJson,
) -> Callable[[str, str], Any]:
    """``fetch(stem, uri)`` for ``flatten_uri_dict`` with mesh ≡ HTTP assert.

    Content-address fetch equivalence — ``contentMesh.cat`` ≡ HTTP GET of
    ``*_uri`` when the URI is http(s). Prefers registry equality ids on
    ``record`` when present.
    """

    def fetch_ref(stem: str, uri: str) -> Any:
        reg_key = _REG_STEM.get(stem)
        locator = record.get(reg_key) if reg_key else None
        locator = locator or uri
        raw = content_mesh.cat(locator)
        if isinstance(raw, (bytes, bytearray)):
            via_mesh = json.loads(raw.decode('utf-8'))
        elif isinstance(raw, str):
            via_mesh = json.loads(raw)
        else:
            via_mesh = raw
        if str(uri).startswith('http'):
            via_http = http_get_json(uri)
            if via_http != via_mesh:
                raise AssertionError(
                    f'HTTP GET {uri!r} must match AddressStore/registry cat '
                    f'of {locator!r}'
                )
        return via_mesh

    return fetch_ref


def assert_control_plane_handoff_coherence(
    *,
    cat_response: dict[str, Any],
    record: dict[str, Any],
    http_get_json: HttpGetJson,
    content_mesh=None,
) -> dict[str, Any]:
    """Assert CAT0 control-plane handoff coherence; return loaded envelopes.

    Overall: control-plane handoff invariants (handoff-chain integrity) —
    response → registry → LDP BOM → Invoice → Order. Distinct from registry
    index parity. Does **not** flatten nested ``*_uri`` refs.

    Checks:

    1. **Locator presence** — ``bom_ldp_uri`` and ``invoice_uri`` exist.
    2. **Response–registry locator agreement** — execute response locators ≡
       ``record`` / locators.
    3. **Envelope–Invoice binding** — signed ExecutionBom ``invoice_uri`` ≡
       resolved Invoice (when present on the BOM).
    4. **Envelope slot completeness** — Invoice has order/data/seed; Order has
       function/structure/input invoice.
    5. **Registry–payload ref agreement** — registry ``data_uri`` / order
       digest ≡ Invoice refs (orders vs cas path OK if digest matches).

    When ``content_mesh`` is set, also returns ``fetch_ref`` implementing
    **content-address fetch equivalence** for a later ``flatten_uri_dict`` call
    (assert-only helper does not flatten).

    Returns ``bom_ldp_uri``, ``invoice_uri``, ``bom``, ``invoice``, ``order``,
    ``locators``, and optional ``fetch_ref``. Invoice slot URIs
    (``order_uri`` / ``data_uri`` / ``seed_uri``) and Order slot URIs
    (``function_uri`` / ``structure_uri`` / ``invoice_uri``) live on those
    envelope dicts — not duplicated at the top level.
    """
    locs = record.get('locators') or {}
    bom_ldp_uri = cat_response.get('bom_ldp_uri')
    invoice_uri = resolve_handoff_invoice_uri(cat_response, record)

    # Locator presence — required fetch addresses exist.
    if not isinstance(bom_ldp_uri, str) or not bom_ldp_uri.strip():
        raise AssertionError(
            f'missing bom_ldp_uri on cat_response: {cat_response!r}'
        )
    if not isinstance(invoice_uri, str) or not invoice_uri.strip():
        raise AssertionError(
            f'missing invoice_uri (response/record/locators): '
            f'response={cat_response!r} record={record!r}'
        )
    bom_ldp_uri = bom_ldp_uri.strip()
    invoice_uri = invoice_uri.strip()

    # Response–registry locator agreement — execute response ≡ record.
    if locs.get('bom_ldp_uri') != bom_ldp_uri:
        raise AssertionError(
            f'record locators.bom_ldp_uri {locs.get("bom_ldp_uri")!r} != '
            f'response bom_ldp_uri {bom_ldp_uri!r}'
        )
    if locs.get('invoice_uri') and locs.get('invoice_uri') != invoice_uri:
        raise AssertionError(
            f'record locators.invoice_uri {locs.get("invoice_uri")!r} != '
            f'resolved invoice_uri {invoice_uri!r}'
        )
    if record.get('invoice_uri') and record.get('invoice_uri') != invoice_uri:
        raise AssertionError(
            f'record.invoice_uri {record.get("invoice_uri")!r} != '
            f'resolved invoice_uri {invoice_uri!r}'
        )

    # Envelope–Invoice binding — GET signed ExecutionBom.
    bom = http_get_json(bom_ldp_uri)
    if not isinstance(bom, dict):
        raise AssertionError(f'BOM at {bom_ldp_uri!r} is not a JSON object')
    if bom.get('invoice_uri') and bom.get('invoice_uri') != invoice_uri:
        raise AssertionError(
            f'ExecutionBom invoice_uri {bom.get("invoice_uri")!r} != '
            f'resolved invoice_uri {invoice_uri!r}'
        )

    # Envelope slot completeness (Invoice) + registry–payload ref agreement.
    invoice = http_get_json(invoice_uri)
    if not isinstance(invoice, dict):
        raise AssertionError(f'Invoice at {invoice_uri!r} is not a JSON object')
    order_uri = invoice.get('order_uri')
    data_uri = invoice.get('data_uri')
    seed_uri = invoice.get('seed_uri')
    if not (order_uri and data_uri and seed_uri):
        raise AssertionError(
            f'Invoice missing order_uri/data_uri/seed_uri: {invoice!r}'
        )
    if record.get('data_uri') and data_uri != record.get('data_uri'):
        raise AssertionError(
            f'Invoice data_uri {data_uri!r} != record data_uri '
            f'{record.get("data_uri")!r}'
        )
    reg_order_uri = locs.get('order_uri') or record.get('order_uri')
    if reg_order_uri and _uri_digest(reg_order_uri) != _uri_digest(order_uri):
        raise AssertionError(
            f'registry order URI digest {_uri_digest(reg_order_uri)!r} != '
            f'Invoice order_uri digest {_uri_digest(order_uri)!r}'
        )

    # Envelope slot completeness (Order) — slots remain on ``order`` only.
    order = http_get_json(order_uri)
    if not isinstance(order, dict):
        raise AssertionError(f'Order at {order_uri!r} is not a JSON object')
    if not (
        order.get('function_uri')
        and order.get('structure_uri')
        and order.get('invoice_uri')
    ):
        raise AssertionError(
            f'Order missing function_uri/structure_uri/invoice_uri: {order!r}'
        )

    out: dict[str, Any] = {
        'bom_ldp_uri': bom_ldp_uri,
        'invoice_uri': invoice_uri,
        'bom': bom,
        'invoice': invoice,
        'order': order,
        'locators': locs,
    }
    if content_mesh is not None:
        out['fetch_ref'] = make_content_fetch_ref(
            record=record,
            content_mesh=content_mesh,
            http_get_json=http_get_json,
        )
    return out
