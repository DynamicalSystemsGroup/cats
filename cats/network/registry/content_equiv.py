"""Envelope subcomponent content equivalence — mesh.cat ≡ HTTP GET.

Per-stem fetch equivalence (and registry digest agreement when the record
cites that stem). Distinct from handoff coherence, index parity, and flatten.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from cats.network.cas import from_ni, is_http_uri, is_ni_or_digest

HttpGetJson = Callable[[str], Any]
HttpGetBytes = Callable[[str], bytes]

_REG_STEM = {
    'order': 'order',
    'data': 'data',
    'seed': 'seed',
    'data_stages': 'data_stages',
    'function': 'function',
    'structure': 'structure',
    'invoice': 'invoice',
    'structure_as_executed': 'structure_as_executed',
}

# Opaque / non-JSON payloads — compare raw bytes when ``http_get`` is provided.
_BYTES_STEMS = frozenset({
    'data',
    'seed',
    'log',
    'egressed_data',
    'integrated_data',
    'ingressed_data',
})

_FUNCTION_SLOT_STEMS = (
    'infrafunction_source',
    'infrafunction',
    'process_source',
    'process',
)

_STRUCTURE_SLOT_STEMS = ('infrastructure', 'plant', 'root')

_DATA_STAGES_NEST_STEMS = (
    'egressed_data',
    'integrated_data',
    'ingressed_data',
)


def _uri_digest(uri: str) -> str:
    """Last path segment lowercased (orders vs cas collection path)."""
    return uri.rstrip('/').rsplit('/', 1)[-1].lower()


def _digest_token(value: str) -> str:
    """Normalize ``ni:`` / hex / HTTP URI path to a comparable digest token."""
    text = value.strip()
    if is_http_uri(text):
        return _uri_digest(text)
    if is_ni_or_digest(text):
        return from_ni(text).lower()
    return text.lower()


def _mesh_bytes(content_mesh, locator: str) -> bytes:
    if hasattr(content_mesh, 'catObj'):
        raw = content_mesh.catObj(locator)
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
    if hasattr(content_mesh, 'cat_bytes'):
        return bytes(content_mesh.cat_bytes(locator))
    raw = content_mesh.cat(locator)
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    if isinstance(raw, str):
        return raw.encode('utf-8')
    return json.dumps(raw).encode('utf-8')


def _assert_registry_digest_agreement(
    stem: str,
    uri: str,
    record: dict[str, Any] | None,
) -> None:
    if not record:
        return
    locs = record.get('locators') or {}
    reg_uri = record.get(f'{stem}_uri') or locs.get(f'{stem}_uri')
    if isinstance(reg_uri, str) and reg_uri.strip():
        if stem == 'data':
            if reg_uri.strip() != uri.strip():
                raise AssertionError(
                    f'record data_uri {reg_uri!r} != fetch uri {uri!r}'
                )
        elif _uri_digest(reg_uri) != _uri_digest(uri):
            raise AssertionError(
                f'registry {stem}_uri digest {_uri_digest(reg_uri)!r} != '
                f'fetch uri digest {_uri_digest(uri)!r}'
            )
    reg_key = _REG_STEM.get(stem)
    eq = record.get(reg_key) if reg_key else None
    # Only compare when the registry equality id is a real ni:/hex digest.
    if isinstance(eq, str) and eq.strip() and is_ni_or_digest(eq.strip()):
        if _digest_token(eq) != _digest_token(uri):
            raise AssertionError(
                f'registry {stem} id digest {_digest_token(eq)!r} != '
                f'uri digest {_digest_token(uri)!r}'
            )


def assert_fetch_equiv(
    stem: str,
    uri: str,
    *,
    content_mesh,
    http_get_json: HttpGetJson,
    http_get: HttpGetBytes | None = None,
    record: dict[str, Any] | None = None,
    locator: str | None = None,
    as_bytes: bool | None = None,
) -> Any:
    """Assert ``content_mesh.cat(locator)`` ≡ HTTP GET of ``uri``.

    Prefers registry equality ids on ``record`` when present (same contract as
    ``make_content_fetch_ref``). When the record cites ``stem``, also asserts
    digest agreement. Opaque stems compare bytes via ``http_get`` when set.
    """
    if not isinstance(uri, str) or not uri.strip():
        raise AssertionError(f'{stem}: missing uri')
    uri = uri.strip()

    loc = locator
    if loc is None and record is not None:
        reg_key = _REG_STEM.get(stem)
        if reg_key:
            candidate = record.get(reg_key)
            if isinstance(candidate, str) and candidate.strip():
                loc = candidate.strip()
    loc = loc or uri

    use_bytes = as_bytes if as_bytes is not None else stem in _BYTES_STEMS
    mesh_raw = _mesh_bytes(content_mesh, loc)

    if use_bytes and http_get is not None and str(uri).startswith('http'):
        via_http = http_get(uri)
        if via_http != mesh_raw:
            raise AssertionError(
                f'HTTP GET {uri!r} bytes must match AddressStore/registry cat '
                f'of {loc!r}'
            )
        _assert_registry_digest_agreement(stem, uri, record)
        return via_http

    try:
        via_mesh = json.loads(mesh_raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        if use_bytes and http_get is not None:
            raise AssertionError(
                f'mesh cat of {loc!r} is non-JSON but bytes compare failed '
                f'earlier path unavailable'
            ) from exc
        if http_get is not None and str(uri).startswith('http'):
            via_http_b = http_get(uri)
            if via_http_b != mesh_raw:
                raise AssertionError(
                    f'HTTP GET {uri!r} bytes must match mesh cat of {loc!r}'
                ) from exc
            _assert_registry_digest_agreement(stem, uri, record)
            return via_http_b
        raise AssertionError(
            f'mesh cat of {loc!r} is not JSON and no http_get for bytes: {exc}'
        ) from exc

    if str(uri).startswith('http'):
        via_http = http_get_json(uri)
        if via_http != via_mesh:
            raise AssertionError(
                f'HTTP GET {uri!r} must match AddressStore/registry cat '
                f'of {loc!r}'
            )
    _assert_registry_digest_agreement(stem, uri, record)
    return via_mesh


def _uri_slot(obj: dict[str, Any], stem: str) -> str | None:
    value = obj.get(f'{stem}_uri')
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def assert_bom_subcomponent_equiv(
    bom: dict[str, Any],
    stem: str,
    **fetch_kw,
) -> Any:
    """Assert fetch equiv for one BOM stem (``invoice`` / ``log``)."""
    if not isinstance(bom, dict):
        raise AssertionError(f'BOM is not a JSON object: {type(bom).__name__}')
    uri = _uri_slot(bom, stem)
    if uri is None:
        return None
    return assert_fetch_equiv(stem, uri, **fetch_kw)


def assert_bom_stage_lineage_equiv(bom: dict[str, Any], **fetch_kw) -> None:
    """Assert mesh ≡ HTTP for each stageLineage entity with an http(s) ``@id``."""
    if not isinstance(bom, dict):
        raise AssertionError(f'BOM is not a JSON object: {type(bom).__name__}')
    lineage = bom.get('stageLineage') or []
    if not isinstance(lineage, list):
        raise AssertionError(f'stageLineage is not a list: {type(lineage).__name__}')
    for index, entity in enumerate(lineage):
        if not isinstance(entity, dict):
            continue
        uri = entity.get('@id')
        if not isinstance(uri, str) or not is_http_uri(uri):
            # Skip blank nodes / ipfs:// / non-HTTP ids.
            continue
        content_id = entity.get('contentId')
        locator = (
            content_id.strip()
            if isinstance(content_id, str) and content_id.strip()
            else None
        )
        assert_fetch_equiv(
            f'stageLineage[{index}]',
            uri,
            locator=locator,
            as_bytes=True,
            **fetch_kw,
        )


def assert_bom_content_equiv(bom: dict[str, Any], **fetch_kw) -> None:
    """Umbrella: BOM invoice / log / stageLineage fetch equivalence."""
    assert_bom_subcomponent_equiv(bom, 'invoice', **fetch_kw)
    assert_bom_subcomponent_equiv(bom, 'log', **fetch_kw)
    assert_bom_stage_lineage_equiv(bom, **fetch_kw)


def assert_invoice_subcomponent_equiv(
    invoice: dict[str, Any],
    stem: str,
    **fetch_kw,
) -> Any:
    """Assert fetch equiv for one Invoice stem (and data_stages nest)."""
    if not isinstance(invoice, dict):
        raise AssertionError(
            f'Invoice is not a JSON object: {type(invoice).__name__}'
        )
    uri = _uri_slot(invoice, stem)
    if uri is None:
        return None
    if stem == 'data_stages':
        nest = assert_fetch_equiv(stem, uri, as_bytes=False, **fetch_kw)
        if not isinstance(nest, dict):
            raise AssertionError(
                f'data_stages at {uri!r} is not a JSON object: '
                f'{type(nest).__name__}'
            )
        for nested in _DATA_STAGES_NEST_STEMS:
            nested_uri = _uri_slot(nest, nested)
            if nested_uri is None:
                continue
            assert_fetch_equiv(nested, nested_uri, as_bytes=True, **fetch_kw)
        return nest
    as_bytes = stem in _BYTES_STEMS
    return assert_fetch_equiv(stem, uri, as_bytes=as_bytes, **fetch_kw)


def assert_invoice_content_equiv(invoice: dict[str, Any], **fetch_kw) -> None:
    """Umbrella: Invoice order/data/seed/data_stages/structure_as_executed."""
    for stem in (
        'order',
        'data',
        'seed',
        'data_stages',
        'structure_as_executed',
    ):
        assert_invoice_subcomponent_equiv(invoice, stem, **fetch_kw)


def assert_order_subcomponent_equiv(
    order: dict[str, Any],
    stem: str,
    **fetch_kw,
) -> Any:
    """Assert fetch equiv for one Order stem; nest Function/Structure slots.

    Order ``invoice_uri`` is the *input* Invoice. Registry ``invoice`` /
    ``invoice_uri`` / ``data`` cite the Executor-minted *output* Invoice —
    so input-invoice fetches must not remap or digest-agree against ``record``.
    """
    if not isinstance(order, dict):
        raise AssertionError(
            f'Order is not a JSON object: {type(order).__name__}'
        )
    uri = _uri_slot(order, stem)
    if uri is None:
        return None
    # Input Invoice ≠ registry output Invoice / egress data.
    slot_kw = {**fetch_kw, 'record': None} if stem == 'invoice' else fetch_kw
    payload = assert_fetch_equiv(stem, uri, as_bytes=False, **slot_kw)
    if stem == 'function' and isinstance(payload, dict):
        for slot in _FUNCTION_SLOT_STEMS:
            slot_uri = _uri_slot(payload, slot)
            if slot_uri is None:
                continue
            assert_fetch_equiv(slot, slot_uri, as_bytes=False, **fetch_kw)
    elif stem == 'structure' and isinstance(payload, dict):
        for slot in _STRUCTURE_SLOT_STEMS:
            slot_uri = _uri_slot(payload, slot)
            if slot_uri is None:
                continue
            assert_fetch_equiv(slot, slot_uri, as_bytes=False, **fetch_kw)
    elif stem == 'invoice' and isinstance(payload, dict):
        data_uri = _uri_slot(payload, 'data')
        if data_uri is not None:
            # Input data ≠ registry egress ``data`` / ``data_uri``.
            assert_fetch_equiv('data', data_uri, as_bytes=True, **slot_kw)
    return payload


def assert_order_content_equiv(order: dict[str, Any], **fetch_kw) -> None:
    """Umbrella: Order function/structure/invoice (+ nested slot URIs)."""
    for stem in ('function', 'structure', 'invoice'):
        assert_order_subcomponent_equiv(order, stem, **fetch_kw)
