"""Digest-keyed directory manifests for CAS-over-HTTP trees."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cats.network.cas.digest import is_ni_or_digest
from cats.network.cas.store import CasHttpStore

MANIFEST_TYPE = 'CasDirectoryManifest'


def build_manifest_entries(entries: dict[str, str]) -> dict[str, Any]:
    """Build a sorted directory manifest document."""
    cleaned: dict[str, str] = {}
    for rel, content_id in entries.items():
        path = rel.replace('\\', '/').lstrip('/')
        if not path or path.startswith('../') or '/../' in f'/{path}/':
            raise ValueError(f'unsafe manifest path: {rel!r}')
        if not is_ni_or_digest(content_id):
            raise ValueError(f'manifest entry must be ni:/digest: {content_id!r}')
        cleaned[path] = content_id
    return {
        '@type': MANIFEST_TYPE,
        'entries': dict(sorted(cleaned.items())),
    }


def is_directory_manifest(obj: Any) -> bool:
    """True when ``obj`` is a CAS directory manifest document."""
    return (
        isinstance(obj, dict)
        and obj.get('@type') == MANIFEST_TYPE
        and isinstance(obj.get('entries'), dict)
    )


def put_tree(store: CasHttpStore, directory: str) -> str:
    """Put all files under ``directory``; return ``ni:`` of the manifest blob."""
    root = Path(directory).resolve()
    if not root.is_dir():
        raise NotADirectoryError(directory)
    entries: dict[str, str] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            entries[rel] = store.put(full.read_bytes())
    manifest = build_manifest_entries(entries)
    return store.put(
        (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8')
    )


def materialize_tree(
    fetch_bytes,
    content_id: str,
    dest_dir: str,
) -> str:
    """Fetch manifest ``content_id`` and write files under ``dest_dir``.

    ``fetch_bytes(content_id) -> bytes`` must resolve CAS (and nested file ids).
    """
    raw = fetch_bytes(content_id)
    obj = json.loads(raw.decode('utf-8'))
    if not is_directory_manifest(obj):
        raise ValueError(f'not a CasDirectoryManifest: {content_id!r}')
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    for rel, file_id in obj['entries'].items():
        path = rel.replace('\\', '/').lstrip('/')
        if not path or path.startswith('../') or '/../' in f'/{path}/':
            raise ValueError(f'unsafe manifest path: {rel!r}')
        out = dest / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(fetch_bytes(file_id))
    return dest_dir
