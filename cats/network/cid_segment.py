"""Shared CID path-segment validation for LDP / registry disk keys."""
from __future__ import annotations

import re

# CIDv0 (Qm…) or CIDv1 (bafy… / similar base32) — path segment only.
_CID_SEGMENT = re.compile(r'^[A-Za-z0-9]+$')


def validate_cid_segment(cid: str, *, label: str = 'cid') -> str:
    """Return stripped ``cid`` or raise ``ValueError`` if unsafe as a path segment."""
    value = (cid or '').strip()
    if not value or '/' in value or '\\' in value or '..' in value:
        raise ValueError(f'invalid {label} path segment: {cid!r}')
    if not _CID_SEGMENT.match(value):
        raise ValueError(f'invalid {label} path segment: {cid!r}')
    return value
