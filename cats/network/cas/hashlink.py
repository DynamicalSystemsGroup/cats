"""Optional ``hl:`` emit for handoff / LDN (Phase 2b slice 6; not required to verify)."""
from __future__ import annotations

import base64
import re

from cats.network.cas.digest import from_ni, is_ni_or_digest, to_ni

# Minimal hashlink: hl:<base64url-sha256>:<url> (draft-shaped; emit-only).
_HL_SHA256 = re.compile(
    r'^hl:([A-Za-z0-9_-]+)(?::(.+))?$'
)


def to_hl(content_id: str, *uris: str) -> str:
    """Build an ``hl:`` string from ``ni:``/hex and optional URL hints.

    Format: ``hl:<base64url-sha256>`` or ``hl:<base64url-sha256>:<uri>``
    (first URI only when multiple are passed — keep handoff compact).
    """
    if not is_ni_or_digest(content_id):
        raise ValueError(f'to_hl requires ni:/hex content id, got {content_id!r}')
    digest = from_ni(content_id)
    raw = bytes.fromhex(digest)
    b64 = base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')
    hints = [u.strip() for u in uris if u and str(u).strip()]
    if not hints:
        return f'hl:{b64}'
    return f'hl:{b64}:{hints[0]}'


def from_hl(hl: str) -> tuple[str, list[str]]:
    """Parse ``hl:`` → ``(ni:, [uris…])``. Raises ``ValueError`` on bad shape."""
    value = (hl or '').strip()
    match = _HL_SHA256.match(value)
    if not match:
        raise ValueError(f'not an hl: sha-256 hashlink: {hl!r}')
    b64 = match.group(1)
    pad = '=' * (-len(b64) % 4)
    raw = base64.urlsafe_b64decode(b64 + pad)
    if len(raw) != 32:
        raise ValueError(f'hl: sha-256 payload must be 32 bytes, got {len(raw)}')
    ni = to_ni(raw.hex())
    rest = match.group(2)
    uris = [rest] if rest else []
    return ni, uris
