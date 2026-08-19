"""InfraStructure [IaaS] transport helpers (Docker Kubo peers) for Process.

Ships inside `infrastructure/` so it is part of `infrastructure_cid`
(directory model). Owns the T&D facet: peer container identity, swarm peering,
CID migrate (get→re-add), and Plant-facing staging. Structure lifetime — torn
down with Compose peers; distinct from the long-lived ContentStore (host Kubo)
and from Node CAS-over-HTTP digests (``ni:``).

Process [Composed Function] transport callables are clients of Function-owned
``TransportPort`` (migrate / stage_for_plant only). The Executor narrows this
``TransportContext`` with ``as_transport_port`` before invoking those callables.
Peering mutate is Structure-owned Option B: TF
`shell_script.ipfs_transport_peering` calls `ensure_peered` every apply;
`InfraStructure.apply` only `assert_ready`. Process must not heal peers.

**CAS ``ni:`` / hex digests:** migrate and stage_for_plant materialize via
Node ``CasHttpStore`` (no Bitswap / ``ipfs get``). Legacy CIDs still use
Docker Kubo get→re-add.

See docs/STORAGE.md and docs/IPFS.md.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

UTILS_FILENAME = 'transport_utils.py'

MIGRATION_CONTAINER = 'structure-ipfs_migration-1'
INTEGRATION_CONTAINER = 'structure-ipfs_integration-1'
IPFS_GET_TIMEOUT = 600
IPFS_SWARM_PORT = 4001

# One level up from infrastructure/ → structure home (cwd for migrate).
_STRUCTURE_HOME_DEFAULT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')
)


def _run(cmd, **kwargs):
    kwargs.setdefault('shell', True)
    kwargs.setdefault('capture_output', True)
    kwargs.setdefault('text', True)
    return subprocess.run(cmd, **kwargs)


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

        class _NoIpfs:
            def cat_bytes(self, cid):
                raise RuntimeError(f'legacy CID not available in CAS transport: {cid!r}')

            def get(self, cid, dest_path):
                raise RuntimeError(f'legacy CID not available in CAS transport: {cid!r}')

            def dag_export(self, cid, filepath):
                raise RuntimeError(f'legacy CID not available in CAS transport: {cid!r}')

        return AddressStore(_NoIpfs(), cats_home=cats_home).get(content_id, dest_dir)

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


def _container_running(container):
    proc = _run(
        f"docker ps --format '{{{{.Names}}}}' | grep -qx '{container}'"
    )
    return proc.returncode == 0


def _container_ip(container):
    proc = _run(
        "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "
        f"{container}"
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _container_peer_id(container):
    proc = _run(f"docker exec {container} ipfs id -f '<id>'")
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _host_peer_id():
    proc = _run("ipfs id -f '<id>'")
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _swarm_connect(container, multiaddr):
    _run(f"docker exec {container} ipfs swarm connect {multiaddr}")


def _docker_ipfs_migrate_cmd(container, input_dir_id, output_dir):
    # Quote id — unquoted ``ni:///sha-256;…`` is split by shell on ``;``.
    cid_q = shlex.quote(input_dir_id)
    out_q = shlex.quote(output_dir)
    inner = (
        f'ipfs get {cid_q} -o {out_q} && '
        f'cd {out_q} && '
        f'rm -f api config datastore_spec gateway repo.lock version && '
        f'ipfs add -r .'
    )
    return f'docker exec {container} sh -c {shlex.quote(inner)}'


@dataclass(frozen=True)
class TransportContext:
    """T&D transport surface for Process port (migrate / stage_for_plant)."""

    migration_container: str = MIGRATION_CONTAINER
    integration_container: str = INTEGRATION_CONTAINER
    get_timeout: int = IPFS_GET_TIMEOUT
    swarm_port: int = IPFS_SWARM_PORT
    structure_home: str = _STRUCTURE_HOME_DEFAULT

    @classmethod
    def default(cls, structure_home=None):
        if structure_home is None:
            return cls()
        return cls(structure_home=structure_home)

    def assert_ready(self):
        """Fail fast if transport peer containers are not running (no heal)."""
        missing = [
            name
            for name in (self.migration_container, self.integration_container)
            if not _container_running(name)
        ]
        if missing:
            raise RuntimeError(
                'InfraStructure transport peers not ready; missing containers: '
                f'{", ".join(missing)}. Reconcile Structure so Compose peers '
                'exist and TF shell_script.ipfs_transport_peering has run '
                '(Option B: apply asserts; ensure_peered is Structure-owned).'
            )

    def ensure_peered(self):
        """Connect transport containers to host Kubo and each other.

        Sole Structure peering **mutate** path — TF
        ``shell_script.ipfs_transport_peering`` (every apply via timestamp
        trigger) and the à la carte CLI. ``InfraStructure.apply`` only
        asserts ``assert_ready`` afterward. No-ops quietly if containers
        are not running yet.
        """
        if not _container_running(self.migration_container):
            return
        if not _container_running(self.integration_container):
            return

        host_peer = _host_peer_id()
        if host_peer:
            host_maddr = (
                f'/dns4/host.docker.internal/tcp/{self.swarm_port}/p2p/{host_peer}'
            )
            for container in (
                self.migration_container,
                self.integration_container,
            ):
                _swarm_connect(container, host_maddr)
                ip = _container_ip(container)
                peer = _container_peer_id(container)
                if ip and peer:
                    _run(
                        f'ipfs swarm connect '
                        f'/ip4/{ip}/tcp/{self.swarm_port}/p2p/{peer}'
                    )

        migration_ip = _container_ip(self.migration_container)
        migration_peer = _container_peer_id(self.migration_container)
        integration_ip = _container_ip(self.integration_container)
        integration_peer = _container_peer_id(self.integration_container)

        if migration_ip and migration_peer:
            _swarm_connect(
                self.integration_container,
                f'/ip4/{migration_ip}/tcp/{self.swarm_port}/p2p/{migration_peer}',
            )
        if integration_ip and integration_peer:
            _swarm_connect(
                self.migration_container,
                f'/ip4/{integration_ip}/tcp/{self.swarm_port}/p2p/{integration_peer}',
            )

    def migrate(self, input_dir_id):
        """Fetch content id → remint for the next Process stage.

        * ``ni:`` / hex — CAS materialize + ``put_tree`` (no Docker Bitswap).
        * Legacy CID — Docker IPFS get→re-add on the migration peer.

        Returns (cid, data_dir_name). Raises RuntimeError on failure.
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

        self.assert_ready()
        unix_ts = int(time.time())
        output_dir = f'/outputs/data_{unix_ts}'
        cmd = _docker_ipfs_migrate_cmd(
            self.migration_container, input_dir_id, output_dir
        )
        try:
            result = _run(
                cmd,
                cwd=self.structure_home,
                timeout=self.get_timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f'Command timed out after {self.get_timeout}s fetching CID '
                f'{input_dir_id}. Ensure host ContentStore (Kubo) is up and '
                'Structure transport peers are peered.'
            ) from e

        if result.returncode != 0:
            raise RuntimeError(f'Command failed with error: {result.stderr}')

        for line in result.stdout.splitlines():
            print(line)
            if line.startswith('added') and line.endswith(f'data_{unix_ts}'):
                cid = line.split()[1]
                return cid, f'data_{unix_ts}'
        raise RuntimeError('CID not found in the output.')

    def stage_for_plant(self, input_dir_id, *, cwd, data_cache=None):
        """Stage ingress content onto the Plant-facing integration cache mount.

        `cwd` is INTEGRATION_INPUT_CACHE; the Docker volume bind is
        INTEGRATION_INPUT_DATA_CACHE → /outputs. Returns host path for Ray.

        CAS ``ni:`` / hex digests materialize on the host path directly (no
        ``ipfs get`` in the integration peer).
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

        self.assert_ready()
        container_out = f'/outputs/{stage_name}'
        cid_q = shlex.quote(input_dir_id)
        out_q = shlex.quote(container_out)
        inner = (
            f'ipfs get {cid_q} -o {out_q} && '
            f'cd {out_q} && '
            f'rm -f api config datastore_spec gateway repo.lock version && '
            f'chmod -R 777 .'
        )
        exec_cmd = (
            f'docker exec {self.integration_container} '
            f'sh -c {shlex.quote(inner)}'
        )
        print(exec_cmd)
        try:
            result = _run(exec_cmd, cwd=cwd, timeout=self.get_timeout)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f'Command timed out after {self.get_timeout}s fetching CID '
                f'{input_dir_id}. Ensure host ContentStore (Kubo) is up and '
                'Structure transport peers are peered.'
            ) from e

        if result.returncode != 0:
            raise RuntimeError(f'Command failed with error: {result.stderr}')
        if not os.path.isdir(host_path):
            raise RuntimeError(
                f'Integration cache staging succeeded in container but host '
                f'path missing: {host_path}'
            )
        return host_path


def _main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'InfraStructure transport peers (Docker Kubo T&D facet). '
            'Peering is Structure-owned; Process uses TransportPort '
            '(Executor narrows this context via as_transport_port).'
        )
    )
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser(
        'ensure-peered',
        help='Peer migration/integration containers to host and each other',
    )
    sub.add_parser(
        'status',
        help='Exit 0 if both transport peer containers are running',
    )

    args = parser.parse_args(argv)
    ctx = TransportContext.default()

    if args.cmd == 'status':
        try:
            ctx.assert_ready()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print('ready')
        return 0

    if args.cmd == 'ensure-peered':
        ctx.ensure_peered()
        print('peered')
        return 0

    return 1


if __name__ == '__main__':
    raise SystemExit(_main())
