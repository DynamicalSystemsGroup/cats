"""Assert registry record locators resolve over HTTP (claims → fetchable)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

HttpGetJson = Callable[[str], Any]
"""``http_get_json(url_or_path) -> parsed JSON`` (raises on non-success)."""

HttpGetBytes = Callable[[str], bytes]
"""``http_get(url_or_path) -> body bytes`` (raises on non-success)."""


def _uri_from_record(record: dict[str, Any], *keys: str) -> str | None:
    locs = record.get('locators') or {}
    for key in keys:
        for source in (record, locs):
            value = source.get(key) if isinstance(source, dict) else None
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _require_json_object(
    http_get_json: HttpGetJson,
    uri: str,
    *,
    label: str,
) -> dict[str, Any]:
    try:
        body = http_get_json(uri)
    except Exception as exc:
        raise AssertionError(
            f'registry claim {label} unreachable at {uri!r}: {exc}'
        ) from exc
    if not isinstance(body, dict):
        raise AssertionError(
            f'registry claim {label} at {uri!r} is not a JSON object: '
            f'{type(body).__name__}'
        )
    return body


def assert_registry_claims_reachable(
    record: dict[str, Any],
    *,
    http_get_json: HttpGetJson,
    http_get: HttpGetBytes | None = None,
) -> None:
    """Assert registry record locator / ``*_uri`` claims resolve over HTTP.

    Checks URIs present on ``record`` / ``record['locators']``:

    - ``bom_ldp_uri`` → JSON object (ExecutionBom-shaped when ``invoice_uri`` set)
    - ``invoice_uri`` → JSON object
    - ``order_uri`` → JSON object when set
    - ``data_uri`` → reachable (``http_get`` for opaque bytes, else ``http_get_json``)
    - Optional stage URIs when set: ``seed_uri``, ``ingress_data_uri``,
      ``integration_data_uri``, ``data_stages_uri``

    This is **not** registry index parity (Python ↔ ``GET /ldp/registry/…``)
    and **not** “all HTTP content lives in the registry.”
    """
    bom_ldp_uri = _uri_from_record(record, 'bom_ldp_uri')
    if not bom_ldp_uri:
        locs = record.get('locators') or {}
        bom_ldp_uri = locs.get('bom_ldp_uri')
    if isinstance(bom_ldp_uri, str) and bom_ldp_uri.strip():
        bom = _require_json_object(
            http_get_json, bom_ldp_uri.strip(), label='bom_ldp_uri'
        )
        inv_claim = _uri_from_record(record, 'invoice_uri')
        if inv_claim and bom.get('invoice_uri') and bom.get('invoice_uri') != inv_claim:
            raise AssertionError(
                f'BOM at {bom_ldp_uri!r} invoice_uri {bom.get("invoice_uri")!r} '
                f'!= record invoice_uri {inv_claim!r}'
            )

    invoice_uri = _uri_from_record(record, 'invoice_uri')
    if invoice_uri:
        _require_json_object(http_get_json, invoice_uri, label='invoice_uri')

    order_uri = _uri_from_record(record, 'order_uri')
    if order_uri:
        _require_json_object(http_get_json, order_uri, label='order_uri')

    data_uri = _uri_from_record(record, 'data_uri')
    if data_uri:
        if http_get is not None:
            try:
                body = http_get(data_uri)
            except Exception as exc:
                raise AssertionError(
                    f'registry claim data_uri unreachable at {data_uri!r}: {exc}'
                ) from exc
            if body is None or body == b'':
                raise AssertionError(
                    f'registry claim data_uri at {data_uri!r} returned empty body'
                )
        else:
            try:
                http_get_json(data_uri)
            except Exception as exc:
                raise AssertionError(
                    f'registry claim data_uri unreachable at {data_uri!r}: {exc}'
                ) from exc

    for stage_key in (
        'seed_uri',
        'ingress_data_uri',
        'integration_data_uri',
        'data_stages_uri',
    ):
        stage_uri = _uri_from_record(record, stage_key)
        if not stage_uri:
            continue
        if http_get is not None and stage_key != 'data_stages_uri':
            # Prefer bytes GET for opaque stage payloads; data_stages is JSON nest.
            if stage_key == 'data_stages_uri':
                _require_json_object(
                    http_get_json, stage_uri, label=stage_key
                )
            else:
                try:
                    body = http_get(stage_uri)
                except Exception as exc:
                    raise AssertionError(
                        f'registry claim {stage_key} unreachable at '
                        f'{stage_uri!r}: {exc}'
                    ) from exc
                if body is None or body == b'':
                    raise AssertionError(
                        f'registry claim {stage_key} at {stage_uri!r} '
                        f'returned empty body'
                    )
        else:
            try:
                http_get_json(stage_uri)
            except Exception as exc:
                raise AssertionError(
                    f'registry claim {stage_key} unreachable at {stage_uri!r}: '
                    f'{exc}'
                ) from exc
