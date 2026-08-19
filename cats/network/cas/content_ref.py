"""Phase 2b dual-field content refs: ``*_cid`` (ni:/CID) + ``*_uri`` (HTTP)."""
from __future__ import annotations

from typing import Any

from cats.network.cas.digest import (
    from_ni,
    is_legacy_cid,
    is_ni_or_digest,
    to_ni,
)
from cats.network.cas.store import cas_ldp_uri


def content_uri(
    content_id: str,
    *,
    base_url: str | None = None,
) -> str | None:
    """Return Node CAS LDP URI for ``ni:``/hex; ``None`` for legacy CID-only."""
    if not content_id or not isinstance(content_id, str):
        return None
    value = content_id.strip()
    if is_ni_or_digest(value):
        return cas_ldp_uri(from_ni(value), base_url=base_url)
    return None


def equality_id(content_id: str) -> str:
    """Canonical equality key: ``ni:`` for digests, else stripped CID."""
    value = (content_id or '').strip()
    if is_ni_or_digest(value):
        return to_ni(from_ni(value))
    return value


def build_content_ref(
    content_id: str,
    *,
    base_url: str | None = None,
    uri: str | None = None,
) -> dict[str, str]:
    """Build ``{cid, uri?}`` — ``uri`` defaults to CAS LDP for ``ni:``."""
    cid = equality_id(content_id) if is_ni_or_digest(content_id) else content_id.strip()
    ref: dict[str, str] = {'cid': cid}
    resolved = uri if uri is not None else content_uri(cid, base_url=base_url)
    if resolved:
        ref['uri'] = resolved
    return ref


def uri_field_name(cid_field: str) -> str:
    """Map ``data_cid`` → ``data_uri`` (and ``foo_cid`` → ``foo_uri``)."""
    if cid_field.endswith('_cid'):
        return cid_field[: -len('_cid')] + '_uri'
    if cid_field == 'cid':
        return 'uri'
    return f'{cid_field}_uri'


def set_cid_uri(
    obj: dict[str, Any],
    cid_field: str,
    content_id: str,
    *,
    base_url: str | None = None,
    uri: str | None = None,
) -> str:
    """Set ``cid_field`` and companion ``*_uri`` when a URI is available.

    Returns the content id stored on ``cid_field``.
    """
    ref = build_content_ref(content_id, base_url=base_url, uri=uri)
    obj[cid_field] = ref['cid']
    ufield = uri_field_name(cid_field)
    if 'uri' in ref:
        obj[ufield] = ref['uri']
    elif ufield in obj:
        del obj[ufield]
    return ref['cid']


def normalize_legacy_ref(content_id: str) -> dict[str, str]:
    """Normalize a CID-only or ``ni:`` id to a content ref (no forced URI)."""
    value = (content_id or '').strip()
    if is_ni_or_digest(value):
        return build_content_ref(value)
    if is_legacy_cid(value):
        return {'cid': value}
    raise ValueError(f'not a content id: {content_id!r}')


def is_http_uri(value: str) -> bool:
    """True when ``value`` looks like an absolute http(s) URI."""
    if not isinstance(value, str):
        return False
    lowered = value.strip().lower()
    return lowered.startswith('http://') or lowered.startswith('https://')
