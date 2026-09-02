"""BOM ``prov:used`` execution bind — Order then output Invoice.

Distinct from handoff coherence (response → registry → Invoice → Order slots)
and from ``content_equiv`` (mesh.cat ≡ HTTP of envelope stems).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cats.network.cas import from_ni, is_http_uri, is_ni_or_digest

HttpGetJson = Callable[[str], Any]


def _ref_token(value: str) -> str:
    """Normalize URI / ``ipfs://`` / ``ni:`` / digest to a comparable token."""
    text = value.strip()
    if text.lower().startswith('ipfs://'):
        text = text[7:]
    if is_http_uri(text):
        return text.rstrip('/').rsplit('/', 1)[-1].lower()
    if is_ni_or_digest(text):
        return from_ni(text).lower()
    return text.lower()


def _require_uri(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssertionError(f'missing {label}: {value!r}')
    return value.strip()


def _used_entities(bom: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(bom, dict):
        raise AssertionError(f'BOM is not a JSON object: {type(bom).__name__}')
    activity = bom.get('prov:wasGeneratedBy')
    if not isinstance(activity, dict):
        raise AssertionError(
            f'BOM missing prov:wasGeneratedBy object: {bom!r}'
        )
    used = activity.get('prov:used')
    if isinstance(used, dict):
        entities = [used]
    elif isinstance(used, list):
        entities = used
    else:
        raise AssertionError(
            f'prov:used is not a list or object: {type(used).__name__}'
        )
    out: list[dict[str, Any]] = []
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            raise AssertionError(
                f'prov:used[{index}] is not an object: {entity!r}'
            )
        entity_id = entity.get('@id')
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise AssertionError(
                f'prov:used[{index}] missing @id: {entity!r}'
            )
        out.append(entity)
    return out


def _entity_agrees(entity: dict[str, Any], uri: str, *, label: str) -> None:
    expected = _ref_token(uri)
    candidates: list[str] = []
    for key in ('@id', 'contentId'):
        raw = entity.get(key)
        if isinstance(raw, str) and raw.strip():
            candidates.append(_ref_token(raw))
    if expected in candidates:
        return
    raise AssertionError(
        f'{label} token {expected!r} does not match '
        f'@id/contentId {candidates!r} ({entity!r})'
    )


def _fetch_payload(
    entity: dict[str, Any],
    *,
    http_get_json: HttpGetJson,
    expected: dict[str, Any] | None,
    label: str,
) -> dict[str, Any]:
    entity_uri = entity['@id'].strip()
    if not is_http_uri(entity_uri):
        raise AssertionError(
            f'{label} @id is not http(s), cannot GET payload: {entity_uri!r}'
        )
    body = http_get_json(entity_uri)
    if not isinstance(body, dict):
        raise AssertionError(
            f'{label} GET {entity_uri!r} is not a JSON object: '
            f'{type(body).__name__}'
        )
    if expected is not None and body != expected:
        raise AssertionError(
            f'{label} GET {entity_uri!r} payload != expected envelope'
        )
    return body


def assert_execution_bind(
    bom: dict[str, Any],
    *,
    order_uri: str,
    invoice_uri: str,
    http_get_json: HttpGetJson | None = None,
    expected_order: dict[str, Any] | None = None,
    expected_invoice: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Assert ``prov:used`` is Order then output Invoice; return the bind list.

    Shape: two entities with ``@id``. Identity: ``used[0]`` ≡ ``order_uri``,
    ``used[1]`` ≡ ``invoice_uri`` (``contentId`` or URI last-path digest;
    ``ipfs://`` vs ``http(s)`` / ``ldp/orders`` vs ``ldp/cas`` OK).

    When ``http_get_json`` is set, GET each ``@id`` (must be http(s)) and
    require a JSON object. When ``expected_order`` / ``expected_invoice`` are
    set, those bodies must equal the GET payloads (pointer reachability +
    envelope identity). Expected bodies require ``http_get_json``.
    """
    order_uri = _require_uri(order_uri, label='order_uri')
    invoice_uri = _require_uri(invoice_uri, label='invoice_uri')
    if expected_order is not None or expected_invoice is not None:
        if http_get_json is None:
            raise AssertionError(
                'expected_order/expected_invoice require http_get_json'
            )

    bind = _used_entities(bom)
    if len(bind) < 2:
        raise AssertionError(
            f'prov:used must cite Order then Invoice; got {len(bind)} '
            f'entit{"y" if len(bind) == 1 else "ies"}: {bind!r}'
        )

    _entity_agrees(bind[0], order_uri, label='Order')
    _entity_agrees(bind[1], invoice_uri, label='output Invoice')

    if http_get_json is not None:
        _fetch_payload(
            bind[0],
            http_get_json=http_get_json,
            expected=expected_order,
            label='Order',
        )
        _fetch_payload(
            bind[1],
            http_get_json=http_get_json,
            expected=expected_invoice,
            label='output Invoice',
        )
    return bind
