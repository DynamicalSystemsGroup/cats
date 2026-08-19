"""InfraStructure [IaaS] transport helpers for Process.

Ships inside `infrastructure/` so it is part of the Structure directory model.
Owns Process ``TransportPort`` CAS materialize/stage (§6s — no Docker Kubo
peers, no legacy CID remint).

Process [Composed Function] transport callables are clients of Function-owned
``TransportPort`` (migrate / stage_for_plant only). The Executor narrows this
``TransportContext`` with ``as_transport_port`` before invoking those callables.

**CAS ``ni:`` / hex / HTTP:** migrate and stage_for_plant materialize via Node
``CasHttpStore`` / AddressStore. Legacy CIDs fail closed (§6s).

See docs/STORAGE.md and docs/IPFS.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass

UTILS_FILENAME = 'transport_utils.py'

# One level up from infrastructure/ → structure home (cwd for migrate).
_STRUCTURE_HOME_DEFAULT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')
)


def _is_cas_content_id(content_id: str) -> bool:
    """True for RFC 6920 ``ni:``, hex sha256, or HTTP CAS/LDP URIs."""
    if not isinstance(content_id, str) or not content_id:
        return False
    if content_id.startswith('ni:'):
        return True
    if content_id.startswith('http://') or content_id.startswith('https://'):
        return True
    if len(content_id) == 64 and all(
        c in '0123456789abcdef' for c in content_id.lower()
    ):
        return True
    return False


def _resolve_cats_home(structure_home: str) -> str:
    env = os.environ.get('CATS_HOME')
    if env:
        return os.path.abspath(env)
    # INPUT_STRUCTURE_HOME = {CATS_HOME}/data/input/structure
    return os.path.abspath(os.path.join(structure_home, '..', '..', '..'))


def _legacy_cid_unsupported(content_id: str) -> RuntimeError:
    return RuntimeError(
        f'Legacy CID {content_id!r} is unsupported (§6s); remint to ni: / HTTP uri'
    )


def _cas_materialize(content_id: str, dest_dir: str, *, cats_home: str) -> str:
    """Expand a CAS directory manifest (or write a single blob) under dest_dir."""
    from cats.network.cas import (
        CasHttpStore,
        is_directory_manifest,
        materialize_tree,
    )
    from cats.network.cas.content_ref import is_http_uri

    if is_http_uri(content_id):
        from cats.network.address_store import AddressStore

        return AddressStore(None, cats_home=cats_home).get(content_id, dest_dir)

    store = CasHttpStore(cats_home)

    def fetch(cid: str) -> bytes:
        data = store.get(cid)
        if data is None:
            raise FileNotFoundError(f'CAS content not found: {cid}')
        return data

    raw = fetch(content_id)
    try:
        obj = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        obj = None
    if is_directory_manifest(obj):
        return materialize_tree(fetch, content_id, dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    # Single-file blob: write as opaque payload.bin (rare for Process data dirs).
    out = os.path.join(dest_dir, 'payload.bin')
    with open(out, 'wb') as handle:
        handle.write(raw)
    return dest_dir


def _cas_put_tree(directory: str, *, cats_home: str) -> str:
    from cats.network.cas import CasHttpStore, LocatorIndex, put_tree

    store = CasHttpStore(cats_home)
    content_id = put_tree(store, directory)
    LocatorIndex(cats_home).put_cas_node_locator(
        content_id, media_type='application/json'
    )
    return content_id


@dataclass(frozen=True)
class TransportContext:
    """Process transport surface (migrate / stage_for_plant) — CAS only (§6s)."""

    structure_home: str = _STRUCTURE_HOME_DEFAULT

    @classmethod
    def default(cls, structure_home=None):
        if structure_home is None:
            return cls()
        return cls(structure_home=structure_home)

    def migrate(self, input_dir_id):
        """Fetch content id → remint for the next Process stage.

        ``ni:`` / hex / HTTP — CAS materialize + ``put_tree``.
        Legacy CID — fail closed (§6s).

        Returns (content_id, data_dir_name). Raises RuntimeError on failure.
        """
        if _is_cas_content_id(input_dir_id):
            cats_home = _resolve_cats_home(self.structure_home)
            unix_ts = int(time.time())
            data_name = f'data_{unix_ts}'
            with tempfile.TemporaryDirectory(prefix='cats-cas-migrate-') as tmp:
                dest = os.path.join(tmp, data_name)
                _cas_materialize(input_dir_id, dest, cats_home=cats_home)
                content_id = _cas_put_tree(dest, cats_home=cats_home)
            return content_id, data_name

        raise _legacy_cid_unsupported(input_dir_id)

    def stage_for_plant(self, input_dir_id, *, cwd, data_cache=None):
        """Stage ingress content onto the Plant-facing integration cache.

        `cwd` is INTEGRATION_INPUT_CACHE; returns host path for Ray.

        CAS ``ni:`` / hex / HTTP only. Legacy CIDs fail closed (§6s).
        """
        if data_cache is None:
            data_cache = os.path.join(cwd, 'outputs')
        unix_ts = int(time.time())
        stage_name = f'staged_{unix_ts}'
        host_path = os.path.join(data_cache, stage_name)
        print('Integration Cache:')

        if _is_cas_content_id(input_dir_id):
            cats_home = _resolve_cats_home(self.structure_home)
            _cas_materialize(input_dir_id, host_path, cats_home=cats_home)
            if not os.path.isdir(host_path):
                raise RuntimeError(
                    f'CAS staging failed; host path missing: {host_path}'
                )
            return host_path

        raise _legacy_cid_unsupported(input_dir_id)


def _main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'InfraStructure Process transport (CAS migrate/stage). '
            'Docker Kubo peers and legacy CID remint are retired (§6s).'
        )
    )
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser(
        'status',
        help='Exit 0 (CAS transport needs no peer containers)',
    )

    args = parser.parse_args(argv)

    if args.cmd == 'status':
        print('ready')
        return 0

    return 1


if __name__ == '__main__':
    raise SystemExit(_main())
