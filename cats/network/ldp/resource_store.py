"""Node-local LDP JSON resources for Order / Invoice (Phase 2b data-plane URIs)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from cats.network.cas.digest import content_id_fs_key

ResourceKind = Literal['invoices', 'orders']


def resource_ldp_path(kind: ResourceKind, content_id: str) -> str:
    """Path under the Node base URL for an Order/Invoice LDP resource."""
    key = content_id_fs_key(content_id, label=f'{kind}_id')
    return f'/ldp/{kind}/{key}'


def resource_ldp_uri(
    kind: ResourceKind,
    content_id: str,
    *,
    base_url: str | None = None,
) -> str:
    """Absolute LDP URI for an Order/Invoice resource."""
    if base_url is None:
        from cats.network.node_http import _node_base_url

        base_url = _node_base_url()
    return f'{base_url.rstrip("/")}{resource_ldp_path(kind, content_id)}'


def invoice_ldp_path(content_id: str) -> str:
    return resource_ldp_path('invoices', content_id)


def invoice_ldp_uri(content_id: str, *, base_url: str | None = None) -> str:
    return resource_ldp_uri('invoices', content_id, base_url=base_url)


def order_ldp_path(content_id: str) -> str:
    return resource_ldp_path('orders', content_id)


def order_ldp_uri(content_id: str, *, base_url: str | None = None) -> str:
    return resource_ldp_uri('orders', content_id, base_url=base_url)


class JsonResourceStore:
    """Persist JSON under ``{CATS_HOME}/.cats/ldp/<kind>/<fs_key>.json``.

    Clients GET only; Runtime / Order mint publish (PUT → 405 on Flask).
    """

    def __init__(self, cats_home: str, kind: ResourceKind):
        self.cats_home = cats_home
        self.kind = kind
        self.root = Path(cats_home) / '.cats' / 'ldp' / kind
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, content_id: str) -> Path:
        key = content_id_fs_key(content_id, label=f'{self.kind}_id')
        return self.root / f'{key}.json'

    def put_bytes(self, content_id: str, data: bytes) -> Path:
        """Store exact bytes (must match CAS encoding when dual-published)."""
        path = self._path(content_id)
        path.write_bytes(bytes(data))
        return path

    def put(self, content_id: str, obj: dict[str, Any]) -> Path:
        """Store JSON with the same encoding as ``ContentMesh.put_json``."""
        return self.put_bytes(
            content_id,
            (json.dumps(obj) + '\n').encode('utf-8'),
        )

    def get(self, content_id: str) -> dict[str, Any] | None:
        raw = self.get_bytes(content_id)
        if raw is None:
            return None
        return json.loads(raw.decode('utf-8'))

    def get_bytes(self, content_id: str) -> bytes | None:
        path = self._path(content_id)
        if not path.is_file():
            return None
        return path.read_bytes()

    def list(self) -> list[str]:
        """Return file stems sorted by mtime descending (newest first)."""
        entries: list[tuple[float, str]] = []
        for path in self.root.glob('*.json'):
            entries.append((path.stat().st_mtime, path.stem))
        entries.sort(key=lambda item: item[0], reverse=True)
        return [stem for _mtime, stem in entries]

    def container_document(self, *, base_url: str | None = None) -> dict[str, Any]:
        if base_url is None:
            from cats.network.node_http import _node_base_url

            base_url = _node_base_url()
        base = base_url.rstrip('/')
        contains = [
            resource_ldp_uri(self.kind, stem, base_url=base) for stem in self.list()
        ]
        return {
            '@context': {
                'ldp': 'http://www.w3.org/ns/ldp#',
                'contains': {'@id': 'ldp:contains', '@type': '@id'},
            },
            '@id': f'{base}/ldp/{self.kind}/',
            '@type': ['ldp:BasicContainer', 'ldp:Container'],
            'contains': contains,
        }


def InvoiceLdpStore(cats_home: str) -> JsonResourceStore:
    return JsonResourceStore(cats_home, 'invoices')


def OrderLdpStore(cats_home: str) -> JsonResourceStore:
    return JsonResourceStore(cats_home, 'orders')
