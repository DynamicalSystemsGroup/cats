"""Verify fetched bytes match a CID via Kubo only-hash (UnixFS add rules)."""
from __future__ import annotations

from typing import Protocol


class CidIntegrityError(ValueError):
    """Raised when fetched bytes do not hash to the requested CID."""

    def __init__(self, cid: str, computed: str):
        self.cid = cid
        self.computed = computed
        super().__init__(
            f'CID integrity check failed: expected {cid!r}, only-hash produced {computed!r}'
        )


class _OnlyHashClient(Protocol):
    def only_hash_bytes(self, data: bytes, **kwargs) -> str: ...


def normalize_cid(cid: str) -> str:
    return cid.strip()


def cids_equal(expected: str, actual: str, client: object | None = None) -> bool:
    """True if CIDs denote the same content id (string match or Kubo format)."""
    left = normalize_cid(expected)
    right = normalize_cid(actual)
    if left == right:
        return True
    cid_format = getattr(client, 'cid_format', None)
    if cid_format is None:
        return False
    try:
        return cid_format(left, version=1) == cid_format(right, version=1)
    except Exception:
        return False


def verify_bytes_match_cid(client: _OnlyHashClient, cid: str, data: bytes) -> None:
    """Recompute CID with Kubo ``add?only-hash=true``; raise on mismatch."""
    computed = client.only_hash_bytes(data)
    if not cids_equal(cid, computed, client):
        raise CidIntegrityError(normalize_cid(cid), normalize_cid(computed))
