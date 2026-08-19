"""Content refs (§6d/§6f): ``*_uri`` fetch; equality via ``ni:`` / ``hl:`` / legacy.

New mints write only ``*_uri`` (never ``*_cid``). Readers accept legacy dual-field
or CID-only graphs via ``ref_id``. Intake accepts ``hl:`` as an alias to ``ni:``.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from cats.network.cas.digest import (
    from_ni,
    is_legacy_cid,
    is_ni_or_digest,
    to_ni,
    validate_digest_segment,
)
from cats.network.cas.hashlink import from_hl, is_hl
from cats.network.cas.store import cas_ldp_uri

# Match /ldp/cas/<hex>, /ldp/invoices/<key>, /ldp/orders/<key>, /ldp/boms/<key>
_LDP_CONTENT_PATH = re.compile(
    r'^/ldp/(?:cas|invoices|orders|boms)/([0-9a-fA-Za-z_-]+)$'
)


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


def is_http_uri(value: str) -> bool:
    """True when ``value`` looks like an absolute http(s) URI."""
    if not isinstance(value, str):
        return False
    lowered = value.strip().lower()
    return lowered.startswith('http://') or lowered.startswith('https://')


def resolve_intake_ref(
    value: str,
    *,
    cats_home: str | None = None,
) -> str | None:
    """Resolve init / ``link*`` intake to an equality id.

    Accepts ``hl:`` (→ ``ni:``, optional hint registration), ``ni:`` / hex,
    or ``http(s)://`` (path / LocatorIndex). Returns ``None`` when an HTTP
    locator cannot be mapped. Raises ``ValueError`` for malformed ``hl:``.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if is_hl(raw):
        ni, uris = from_hl(raw)
        if cats_home:
            from cats.network.cas.locators import LocatorIndex

            index = LocatorIndex(cats_home)
            for uri in uris:
                if is_http_uri(uri):
                    index.put(ni, uri=uri)
        return ni
    if is_ni_or_digest(raw):
        return equality_id(raw)
    if is_http_uri(raw):
        found = content_id_from_uri(raw, cats_home=cats_home)
        if found:
            return found
        if cats_home:
            from cats.network.cas.locators import LocatorIndex

            found = LocatorIndex(cats_home).find_content_id_for_uri(raw)
            if found:
                return equality_id(found) if is_ni_or_digest(found) else found
        return None
    return raw


def content_id_from_uri(
    uri: str,
    *,
    cats_home: str | None = None,
) -> str | None:
    """Extract equality id from an HTTP locator (path digest or LocatorIndex)."""
    if not uri or not is_http_uri(uri):
        return None
    parsed = urlparse(uri.strip())
    match = _LDP_CONTENT_PATH.match(parsed.path or '')
    if match:
        key = match.group(1)
        try:
            digest = validate_digest_segment(key.lower())
            return to_ni(digest)
        except ValueError:
            # Non-hex key (legacy CID path segment) — use as equality id.
            return key
    if cats_home:
        from cats.network.cas.locators import LocatorIndex

        found = LocatorIndex(cats_home).find_content_id_for_uri(uri.strip())
        if found:
            return equality_id(found) if is_ni_or_digest(found) else found
    return None


def uri_field_name(stem_or_cid_field: str) -> str:
    """Map ``data`` / ``data_cid`` → ``data_uri``."""
    if stem_or_cid_field.endswith('_cid'):
        return stem_or_cid_field[: -len('_cid')] + '_uri'
    if stem_or_cid_field.endswith('_uri'):
        return stem_or_cid_field
    if stem_or_cid_field == 'cid':
        return 'uri'
    return f'{stem_or_cid_field}_uri'


def cid_field_name(stem: str) -> str:
    """Map stem ``data`` → ``data_cid`` (legacy field)."""
    if stem.endswith('_cid'):
        return stem
    if stem.endswith('_uri'):
        return stem[: -len('_uri')] + '_cid'
    return f'{stem}_cid'


def build_content_ref(
    content_id: str,
    *,
    base_url: str | None = None,
    uri: str | None = None,
) -> dict[str, str]:
    """Build ``{content_id, uri?}`` — ``uri`` defaults to CAS LDP for ``ni:``.

    Deprecated ``cid`` key is no longer emitted (use ``content_id``).
    """
    eid = equality_id(content_id) if is_ni_or_digest(content_id) else content_id.strip()
    ref: dict[str, str] = {'content_id': eid}
    resolved = uri if uri is not None else content_uri(eid, base_url=base_url)
    if resolved:
        ref['uri'] = resolved
    return ref


def set_ref(
    obj: dict[str, Any],
    stem: str,
    content_id: str,
    *,
    base_url: str | None = None,
    uri: str | None = None,
) -> str:
    """Set ``{stem}_uri`` only (never ``{stem}_cid``). Returns equality id.

    When no HTTP CAS locator exists (legacy CID), ``{stem}_uri`` still receives
    the opaque equality/fetch id so remints omit ``*_cid`` without dropping
    identity. ``AddressStore`` accepts CID / ``ni:`` / http(s).
    """
    ref = build_content_ref(content_id, base_url=base_url, uri=uri)
    ufield = uri_field_name(stem)
    cid_field = cid_field_name(stem)
    if 'uri' in ref:
        obj[ufield] = ref['uri']
    else:
        obj[ufield] = ref['content_id']
    # Ensure new mints never carry the legacy cid key.
    if cid_field in obj:
        del obj[cid_field]
    return ref['content_id']


def set_cid_uri(
    obj: dict[str, Any],
    cid_field: str,
    content_id: str,
    *,
    base_url: str | None = None,
    uri: str | None = None,
) -> str:
    """Deprecated dual-field writer — delegates to ``set_ref`` (uri-only)."""
    stem = cid_field[: -len('_cid')] if cid_field.endswith('_cid') else cid_field
    return set_ref(obj, stem, content_id, base_url=base_url, uri=uri)


def ref_uri(obj: dict[str, Any], stem: str) -> str | None:
    """Prefer ``{stem}_uri``; ``None`` if absent."""
    ufield = uri_field_name(stem)
    value = obj.get(ufield)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def ref_id(
    obj: dict[str, Any],
    stem: str,
    *,
    cats_home: str | None = None,
) -> str | None:
    """Equality id: from ``{stem}_uri`` (path / locator) or legacy ``{stem}_cid``."""
    uri = ref_uri(obj, stem)
    if uri:
        if is_hl(uri):
            try:
                return resolve_intake_ref(uri, cats_home=cats_home)
            except ValueError:
                return None
        if is_http_uri(uri):
            found = content_id_from_uri(uri, cats_home=cats_home)
            if found:
                return found
            # HTTP URI present but unparseable — fall through to legacy cid.
        else:
            # Opaque locator in *_uri (legacy CID / ni: without http form).
            # Accept any non-empty non-http value so remints that stash the
            # equality id in *_uri (incl. hyphenated test mocks) still resolve.
            value = uri.strip()
            if is_ni_or_digest(value):
                return equality_id(value)
            return value
    cid_field = cid_field_name(stem)
    legacy = obj.get(cid_field)
    if isinstance(legacy, str) and legacy.strip():
        value = legacy.strip()
        return equality_id(value) if is_ni_or_digest(value) else value
    # Also accept bare content_id on the object (registry projections).
    if stem in ('', 'content') and isinstance(obj.get('content_id'), str):
        value = obj['content_id'].strip()
        return equality_id(value) if is_ni_or_digest(value) else value
    return None


def normalize_legacy_ref(content_id: str) -> dict[str, str]:
    """Normalize a CID-only or ``ni:`` id to a content ref (no forced URI)."""
    value = (content_id or '').strip()
    if is_ni_or_digest(value):
        return build_content_ref(value)
    if is_legacy_cid(value):
        return {'content_id': value}
    raise ValueError(f'not a content id: {content_id!r}')
