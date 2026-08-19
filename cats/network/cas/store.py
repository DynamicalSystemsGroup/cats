"""Node-local digest-keyed CAS blob store (data plane; HTTP via LDP routes)."""
from __future__ import annotations

from pathlib import Path

from cats.network.cas.digest import (
    from_ni,
    is_ni_or_digest,
    sha256_hex,
    to_ni,
    validate_digest_segment,
)


def cas_ldp_path(hex_digest: str) -> str:
    """Path under the Node base URL for a CAS blob."""
    return f'/ldp/cas/{validate_digest_segment(hex_digest)}'


def cas_ldp_uri(hex_digest: str, *, base_url: str | None = None) -> str:
    """Absolute LDP URI for a CAS blob (uses CAT_NODE_* when base unset)."""
    if base_url is None:
        from cats.network.node_http import _node_base_url

        base_url = _node_base_url()
    return f'{base_url.rstrip("/")}{cas_ldp_path(hex_digest)}'


class CasHttpStore:
    """Persist opaque blobs under ``{CATS_HOME}/.cats/ldp/cas/<hex>``.

    Identity is sha256 of exact stored bytes. Put is idempotent on digest.
    """

    def __init__(self, cats_home: str):
        self.cats_home = cats_home
        self.root = Path(cats_home) / '.cats' / 'ldp' / 'cas'
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, hex_digest: str) -> Path:
        return self.root / validate_digest_segment(hex_digest)

    def put(self, data: bytes) -> str:
        """Store ``data``; return canonical ``ni:`` content id."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError('CasHttpStore.put expects bytes')
        payload = bytes(data)
        digest = sha256_hex(payload)
        path = self._path(digest)
        if not path.is_file():
            path.write_bytes(payload)
        else:
            existing = path.read_bytes()
            if existing != payload:
                raise RuntimeError(
                    f'CAS digest collision for {digest}: stored bytes differ'
                )
        return to_ni(digest)

    def get(self, content_id: str) -> bytes | None:
        """Return blob bytes for ``ni:`` / hex, or None if missing."""
        if is_ni_or_digest(content_id):
            digest = from_ni(content_id)
        else:
            digest = validate_digest_segment(content_id)
        path = self._path(digest)
        if not path.is_file():
            return None
        return path.read_bytes()

    def has(self, content_id: str) -> bool:
        return self.get(content_id) is not None

    def list_digests(self) -> list[str]:
        """Return hex digests sorted by mtime descending (newest first)."""
        entries: list[tuple[float, str]] = []
        for path in self.root.iterdir():
            if path.is_file() and len(path.name) == 64:
                try:
                    validate_digest_segment(path.name)
                except ValueError:
                    continue
                entries.append((path.stat().st_mtime, path.name))
        entries.sort(key=lambda item: item[0], reverse=True)
        return [digest for _mtime, digest in entries]
