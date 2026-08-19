"""Digest / ``ni:`` identity helpers for CAS-over-HTTP (RFC 6920 sha-256)."""
from __future__ import annotations

import base64
import hashlib
import re

# Path-safe lowercase hex sha256 (64 chars).
_HEX_SHA256 = re.compile(r'^[0-9a-f]{64}$')
# CIDv0 / CIDv1 path segments (legacy).
_CID_SEGMENT = re.compile(r'^[A-Za-z0-9]+$')
_NI_SHA256 = re.compile(
    r'^ni:///sha-256;([A-Za-z0-9_-]+)$'
)


def sha256_hex(data: bytes) -> str:
    """Return lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def validate_digest_segment(hex_digest: str, *, label: str = 'digest') -> str:
    """Return stripped lowercase hex or raise ``ValueError``."""
    value = (hex_digest or '').strip().lower()
    if not value or '/' in value or '\\' in value or '..' in value:
        raise ValueError(f'invalid {label} path segment: {hex_digest!r}')
    if not _HEX_SHA256.match(value):
        raise ValueError(f'invalid {label} path segment: {hex_digest!r}')
    return value


def to_ni(hex_digest: str) -> str:
    """RFC 6920 ``ni:///sha-256;<base64url>`` from lowercase hex."""
    digest = validate_digest_segment(hex_digest)
    raw = bytes.fromhex(digest)
    b64 = base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')
    return f'ni:///sha-256;{b64}'


def from_ni(ni: str) -> str:
    """Return lowercase hex from ``ni:///sha-256;…`` (or bare hex)."""
    value = (ni or '').strip()
    if _HEX_SHA256.match(value.lower()):
        return value.lower()
    match = _NI_SHA256.match(value)
    if not match:
        raise ValueError(f'not a sha-256 ni: URI or hex digest: {ni!r}')
    b64 = match.group(1)
    pad = '=' * (-len(b64) % 4)
    raw = base64.urlsafe_b64decode(b64 + pad)
    if len(raw) != 32:
        raise ValueError(f'ni: sha-256 payload must be 32 bytes, got {len(raw)}')
    return raw.hex()


def is_ni_or_digest(content_id: str) -> bool:
    """True when ``content_id`` is ``ni:`` or bare hex sha256."""
    if not isinstance(content_id, str):
        return False
    value = content_id.strip()
    if _HEX_SHA256.match(value.lower()):
        return True
    return bool(_NI_SHA256.match(value))


def is_legacy_cid(content_id: str) -> bool:
    """True when ``content_id`` looks like a Kubo CID path segment (not ni:/hex)."""
    value = (content_id or '').strip()
    if not value or is_ni_or_digest(value):
        return False
    return bool(_CID_SEGMENT.match(value)) and '/' not in value


def content_id_to_ni(content_id: str) -> str:
    """Normalize ``ni:`` or hex to canonical ``ni:`` form."""
    return to_ni(from_ni(content_id) if is_ni_or_digest(content_id) else content_id)


def content_id_fs_key(content_id: str, *, label: str = 'content_id') -> str:
    """Filesystem / URL path key: hex for ``ni:``/digest, else CID segment."""
    value = (content_id or '').strip()
    if not value:
        raise ValueError(f'invalid {label} path segment: {content_id!r}')
    if is_ni_or_digest(value):
        return from_ni(value)
    if '/' in value or '\\' in value or '..' in value:
        raise ValueError(f'invalid {label} path segment: {content_id!r}')
    if not _CID_SEGMENT.match(value):
        raise ValueError(f'invalid {label} path segment: {content_id!r}')
    return value
