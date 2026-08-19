"""Locator index: content_id → HTTP locators (CAS-over-HTTP discovery)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cats.network.cas.digest import (
    content_id_fs_key,
    from_ni,
    is_ni_or_digest,
    to_ni,
)
from cats.network.cas.store import cas_ldp_uri


class LocatorIndex:
    """Append-only locator lists under ``{CATS_HOME}/.cats/registry/by-content/``."""

    def __init__(self, cats_home: str):
        self.cats_home = cats_home
        self.root = Path(cats_home) / '.cats' / 'registry' / 'by-content'
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, content_id: str) -> Path:
        key = content_id_fs_key(content_id, label='content_id')
        return self.root / f'{key}.json'

    def _canonical_id(self, content_id: str) -> str:
        if is_ni_or_digest(content_id):
            return to_ni(from_ni(content_id))
        return content_id.strip()

    def put(
        self,
        content_id: str,
        *,
        uri: str,
        media_type: str | None = None,
    ) -> Path:
        """Register ``uri`` for ``content_id`` (append-if-absent by uri)."""
        canonical = self._canonical_id(content_id)
        path = self._path(canonical)
        doc: dict[str, Any]
        if path.is_file():
            doc = json.loads(path.read_text(encoding='utf-8'))
        else:
            doc = {'content_id': canonical, 'locators': []}
        locators = doc.setdefault('locators', [])
        if not any(loc.get('uri') == uri for loc in locators):
            entry: dict[str, Any] = {'uri': uri}
            if media_type:
                entry['media_type'] = media_type
            locators.insert(0, entry)
        doc['content_id'] = canonical
        path.write_text(
            json.dumps(doc, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        return path

    def put_cas_node_locator(
        self,
        content_id: str,
        *,
        base_url: str | None = None,
        media_type: str | None = None,
    ) -> Path:
        """Register the Node ``/ldp/cas/<hex>`` locator for a digest id."""
        digest = from_ni(content_id) if is_ni_or_digest(content_id) else content_id
        uri = cas_ldp_uri(digest, base_url=base_url)
        return self.put(content_id, uri=uri, media_type=media_type)

    def get(self, content_id: str) -> dict[str, Any] | None:
        path = self._path(content_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding='utf-8'))

    def lookup_uris(self, content_id: str) -> list[str]:
        doc = self.get(content_id)
        if doc is None:
            return []
        return [str(loc['uri']) for loc in doc.get('locators') or [] if loc.get('uri')]

    def find_content_id_for_uri(self, uri: str) -> str | None:
        """Reverse-lookup ``content_id`` for an exact locator ``uri`` (Node-local scan)."""
        target = (uri or '').strip()
        if not target:
            return None
        for path in self.root.glob('*.json'):
            try:
                doc = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                continue
            for loc in doc.get('locators') or []:
                if loc.get('uri') == target:
                    content_id = doc.get('content_id')
                    if isinstance(content_id, str) and content_id.strip():
                        return self._canonical_id(content_id)
        return None
