"""Verify fetched bytes match a CID (pure UnixFS first; Kubo only-hash fallback)."""
from __future__ import annotations

from typing import Protocol

from cats.network.address_store.unixfs_cid import (
    compute_unixfs_file_cid,
    local_cids_equal,
)


class CidIntegrityError(ValueError):
    """Raised when fetched bytes do not hash to the requested CID."""

    def __init__(self, cid: str, computed: str, *, path: str = 'verify'):
        self.cid = cid
        self.computed = computed
        self.path = path
        super().__init__(
            f'CID integrity check failed ({path}): expected {cid!r}, '
            f'computed {computed!r}'
        )


class _OnlyHashClient(Protocol):
    def only_hash_bytes(self, data: bytes, **kwargs) -> str: ...


def normalize_cid(cid: str) -> str:
    return cid.strip()


def cids_equal(expected: str, actual: str, client: object | None = None) -> bool:
    """True if CIDs denote the same content id (local v0/v1 or Kubo format)."""
    left = normalize_cid(expected)
    right = normalize_cid(actual)
    if local_cids_equal(left, right):
        return True
    cid_format = getattr(client, 'cid_format', None)
    if cid_format is None:
        return False
    try:
        return cid_format(left, version=1) == cid_format(right, version=1)
    except Exception:
        return False


def verify_bytes_match_cid(client: _OnlyHashClient | None, cid: str, data: bytes) -> None:
    """Verify ``data`` matches ``cid`` via pure UnixFS, else Kubo only-hash.

    Happy path (default single- or multi-block UnixFS File) needs no RPC.
    Mismatch / exotic layouts fall back to ``client.only_hash_bytes`` when available.
    """
    expected = normalize_cid(cid)
    computed = compute_unixfs_file_cid(data)
    if cids_equal(expected, computed, client):
        return
    pure_computed = normalize_cid(computed)

    only_hash = getattr(client, 'only_hash_bytes', None) if client is not None else None
    if only_hash is not None:
        oracle = only_hash(data)
        if cids_equal(expected, oracle, client):
            return
        raise CidIntegrityError(
            expected, normalize_cid(oracle), path='only-hash'
        )

    raise CidIntegrityError(expected, pure_computed, path='unixfs')
