"""InfraStructure [IaaS] optional host Kubo helpers (operator tooling).

Ships inside `infrastructure/` (directory model). Owns optional host Kubo
readiness: HTTP API probe, stale repo.lock heal, and idempotent `ipfs daemon`
start. Live Orders use Node CAS (§6s); this module is **not** required for
Structure apply or Process transport.

ContentMesh does not call ensure (readiness soft-warn only). Operator CLI /
``node ensure`` call ``ContentStore.ensure()``. The CAT Node process must not
shut down this daemon on exit.

See docs/IPFS.md and docs/STORAGE.md.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import requests

UTILS_FILENAME = 'content_store_utils.py'


def _ipfs_api_id_url():
    """HTTP ``/api/v0/id`` URL for readiness — same API as CatsIPFSClient.connect().

    Canonical: ``IPFS_API_HOST`` / ``IPFS_API_PORT`` (defaults 127.0.0.1:5001).
    Optional escape hatch: ``CATS_IPFS_API_ID_URL`` (full URL) overrides both.
    Kubo can answer CLI ``ipfs id`` offline; always probe the HTTP API instead.
    """
    override = os.environ.get('CATS_IPFS_API_ID_URL')
    if override:
        return override
    host = os.environ.get('IPFS_API_HOST', '127.0.0.1')
    port = int(os.environ.get('IPFS_API_PORT', '5001'))
    return f'http://{host}:{port}/api/v0/id'


def _repo_lock_path():
    ipfs_path = os.environ.get('IPFS_PATH') or os.path.expanduser('~/.ipfs')
    return os.path.join(ipfs_path, 'repo.lock')


def _lock_holder_pids(lock_path):
    """PIDs holding an open FD on repo.lock (via lsof). Empty if unknown."""
    try:
        result = subprocess.run(
            ['lsof', '-t', lock_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    pids = []
    for line in result.stdout.split():
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def _ipfs_daemon_pids():
    """PIDs matching `ipfs daemon`. Empty if the probe fails (not fail-closed)."""
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'ipfs daemon'],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode not in (0, 1):
        return []
    pids = []
    for line in result.stdout.split():
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def _terminate_pids(pids, wait_seconds=2.0):
    """SIGTERM then SIGKILL stubborn PIDs. Ignores missing processes."""
    alive = []
    for pid in pids:
        try:
            os.kill(pid, 15)  # SIGTERM
            alive.append(pid)
        except OSError:
            continue
    if not alive:
        return
    deadline = time.time() + wait_seconds
    while time.time() < deadline and alive:
        still = []
        for pid in alive:
            try:
                os.kill(pid, 0)
                still.append(pid)
            except OSError:
                continue
        alive = still
        if alive:
            time.sleep(0.1)
    for pid in alive:
        try:
            os.kill(pid, 9)  # SIGKILL
        except OSError:
            pass


def _wait_for_ipfs_api(timeout=30.0, poll_interval=0.25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ContentStore.is_ready():
            return True
        time.sleep(poll_interval)
    return False


def _heal_stale_repo_lock():
    """Best-effort recover from a dead API with a held repo.lock.

    A hung Kubo can hold the flock (and even keep swarm sockets) while the
    HTTP API on :5001 is dead — `ipfs shutdown` talks to that API, so it
    cannot clear this state. Terminate lock holders / daemon PIDs, then
    remove the stale lock file so a fresh daemon can start.
    """
    try:
        subprocess.run(
            ['ipfs', 'shutdown'],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass

    time.sleep(0.5)
    if ContentStore.is_ready():
        return

    lock_path = _repo_lock_path()
    pids = set(_lock_holder_pids(lock_path)) | set(_ipfs_daemon_pids())
    if pids:
        print(
            f'Terminating hung host IPFS process(es) holding repo lock: '
            f'{sorted(pids)}',
            flush=True,
        )
        _terminate_pids(sorted(pids))
        # Give the OS time to release flock / listen sockets before restart.
        time.sleep(2.0)

    if ContentStore.is_ready():
        return

    if os.path.exists(lock_path) and not _lock_holder_pids(lock_path):
        try:
            os.unlink(lock_path)
            print(f'Removed stale IPFS repo lock at {lock_path}.', flush=True)
        except OSError:
            pass


class ContentStore:
    """Long-lived InfraStructure content-store facet (host Kubo)."""

    @staticmethod
    def is_ready(timeout=1.0) -> bool:
        """True only when the host Kubo HTTP API accepts /api/v0/id."""
        try:
            response = requests.post(_ipfs_api_id_url(), timeout=timeout)
            return response.ok
        except (requests.RequestException, OSError):
            return False

    @staticmethod
    def ensure(ready_timeout=30.0, cwd=None) -> None:
        """Idempotently ensure host Kubo HTTP API is up.

        Does not claim Node process ownership — content store outlives the
        CAT Node and Structure T&D teardown.
        """
        if ContentStore.is_ready():
            return
        _heal_stale_repo_lock()
        if ContentStore.is_ready():
            return
        api_url = _ipfs_api_id_url()
        print(
            f'Starting host IPFS daemon (waiting for {api_url})...',
            flush=True,
        )
        last_err = ''
        for attempt in range(1, 4):
            proc = subprocess.Popen(
                'ipfs daemon',
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                shell=True,
                universal_newlines=True,
                cwd=cwd,
            )
            if _wait_for_ipfs_api(timeout=ready_timeout):
                print('Host IPFS daemon API ready.', flush=True)
                return
            err = ''
            if proc.poll() is not None and proc.stderr is not None:
                err = proc.stderr.read() or ''
            last_err = err.strip()
            print(
                f'ipfs daemon start attempt {attempt}/3 failed'
                + (f': {last_err}' if last_err else ''),
                flush=True,
            )
            # Another hung start may hold the lock; heal and retry.
            _heal_stale_repo_lock()
            time.sleep(1.0)
        raise RuntimeError(
            'Timed out waiting for host IPFS daemon HTTP API at '
            f'{api_url}'
            + (f': {last_err}' if last_err else '')
        )


def _main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Ensure or probe InfraStructure content-store (host Kubo). '
            'Long-lived facet; not destroyed with Structure T&D / Plant.'
        )
    )
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser(
        'ensure',
        help='Start host Kubo if the HTTP API is down (idempotent)',
    )
    sub.add_parser(
        'status',
        help='Exit 0 if Kubo HTTP API is up, 1 otherwise',
    )

    args = parser.parse_args(argv)

    if args.cmd == 'status':
        if ContentStore.is_ready():
            print('ready')
            return 0
        print('not ready', file=sys.stderr)
        return 1

    if args.cmd == 'ensure':
        ContentStore.ensure()
        return 0

    return 1


if __name__ == '__main__':
    raise SystemExit(_main())
