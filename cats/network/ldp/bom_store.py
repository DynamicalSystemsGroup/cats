"""Disk-backed LDP index for signed ExecutionBom envelopes (control plane)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

# CIDv0 (Qm…) or CIDv1 (bafy… / similar base32) — path segment only.
_CID_SEGMENT = re.compile(r'^[A-Za-z0-9]+$')


def bom_ldp_path(bom_cid: str) -> str:
    """Path under the Node base URL for a BOM LDP resource."""
    return f'/ldp/boms/{bom_cid}'


def bom_ldp_uri(bom_cid: str, *, base_url: str | None = None) -> str:
    """Absolute LDP URI for ``bom_cid`` (uses CAT_NODE_* when base unset)."""
    if base_url is None:
        from cats.network.node_http import _node_base_url

        base_url = _node_base_url()
    return f'{base_url.rstrip("/")}{bom_ldp_path(bom_cid)}'


def _validate_bom_cid(bom_cid: str) -> str:
    cid = (bom_cid or '').strip()
    if not cid or '/' in cid or '\\' in cid or '..' in cid:
        raise ValueError(f'invalid bom_cid path segment: {bom_cid!r}')
    if not _CID_SEGMENT.match(cid):
        raise ValueError(f'invalid bom_cid path segment: {bom_cid!r}')
    return cid


class BomLdpStore:
    """Persist signed BOMs under ``{CATS_HOME}/.cats/ldp/boms/<bom_cid>.json``."""

    def __init__(self, cats_home: str):
        self.cats_home = cats_home
        self.root = Path(cats_home) / '.cats' / 'ldp' / 'boms'
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, bom_cid: str) -> Path:
        return self.root / f'{_validate_bom_cid(bom_cid)}.json'

    def put(self, bom_cid: str, bom: dict[str, Any]) -> Path:
        path = self._path(bom_cid)
        path.write_text(
            json.dumps(bom, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        return path

    def get(self, bom_cid: str) -> dict[str, Any] | None:
        path = self._path(bom_cid)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding='utf-8'))

    def list(self) -> list[str]:
        """Return bom_cid keys sorted by mtime descending (newest first)."""
        entries: list[tuple[float, str]] = []
        for path in self.root.glob('*.json'):
            entries.append((path.stat().st_mtime, path.stem))
        entries.sort(key=lambda item: item[0], reverse=True)
        return [cid for _mtime, cid in entries]

    def container_document(self, *, base_url: str | None = None) -> dict[str, Any]:
        """LDP Basic Container JSON-LD listing contained BOM resource URIs."""
        if base_url is None:
            from cats.network.node_http import _node_base_url

            base_url = _node_base_url()
        base = base_url.rstrip('/')
        contains = [bom_ldp_uri(cid, base_url=base) for cid in self.list()]
        return {
            '@context': {
                'ldp': 'http://www.w3.org/ns/ldp#',
                'contains': {'@id': 'ldp:contains', '@type': '@id'},
            },
            '@id': f'{base}/ldp/boms/',
            '@type': ['ldp:BasicContainer', 'ldp:Container'],
            'contains': contains,
        }
