"""AQ-safe Node process lifecycle CLI: start|stop|status|ensure."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import subprocess
import time

from cats import CATS_HOME, RUNTIME
from cats.network import _load_bootstrap_content_store_module
from cats.node.app import HOST, PORT, catNode

logger = logging.getLogger(__name__)

# Command-line markers for our peer-edge process (``python -m cats.node`` /
# legacy ``cats/node.py`` path invocations). Unrelated listeners on the same
# port (e.g. macOS AirPlay on 5000) must not be killed.
_NODE_CMD_MARKERS = ('cats.node', 'cats/node', 'node.py')


def _is_cats_node_cmd(cmd: str) -> bool:
    return any(marker in cmd for marker in _NODE_CMD_MARKERS)


def _flask_listening(host: str, port: int) -> bool:
    """True when something accepts TCP on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((host, port)) == 0


def _listen_pids(port: int) -> list[str]:
    try:
        return subprocess.run(
            ['lsof', '-t', f'-i:{port}', '-sTCP:LISTEN'],
            capture_output=True, text=True, timeout=5,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return []


def _cats_node_on_port(port: int) -> bool:
    """True when a cats.node process (not AirPlay/etc.) listens on ``port``."""
    for pid in _listen_pids(port):
        try:
            cmd = subprocess.run(
                ['ps', '-p', pid, '-o', 'command='],
                capture_output=True, text=True, timeout=5,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        if _is_cats_node_cmd(cmd):
            return True
    return False


def _stop_node_process(host: str, port: int) -> None:
    """Kill any leftover cats.node peer still bound to our port.

    Agent/chat sessions launch this server in the background and don't
    always terminate it when the session ends, so a stale process can be
    left holding the port for a future run to collide with. Only processes
    whose command line matches this package are killed - other programs on
    the port (e.g. macOS's AirPlay Receiver on 5000) are left alone.

    Never touches InfraStructure ContentStore (host Kubo).
    """
    if not _flask_listening(host, port):
        return

    pids = _listen_pids(port)
    if not pids:
        return

    killed_any = False
    for pid in pids:
        try:
            # Debug mode's reloader is a parent/child pair; the listener is
            # usually the child, so its parent must be killed too or it
            # will just respawn a new child on the same port.
            info = subprocess.run(
                ['ps', '-p', pid, '-o', 'ppid=,command='],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue

        if not info or not _is_cats_node_cmd(info):
            continue  # leave unrelated processes (e.g. AirPlay) alone

        ppid = info.split(None, 1)[0]
        for target in {pid, ppid}:
            try:
                parent_cmd = subprocess.run(
                    ['ps', '-p', target, '-o', 'command='],
                    capture_output=True, text=True, timeout=5,
                ).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            if not _is_cats_node_cmd(parent_cmd):
                continue
            logger.warning(
                "Killing cats.node process (pid %s) still bound to %s:%d",
                target, host, port,
            )
            try:
                os.kill(int(target), signal.SIGTERM)
                killed_any = True
            except (OSError, ValueError):
                pass

    if killed_any:
        for _ in range(20):
            time.sleep(0.1)
            if not _flask_listening(host, port):
                return


def _free_stale_port(host: str, port: int) -> None:
    """Alias used by start — clear a prior cats.node listener before bind."""
    _stop_node_process(host, port)


def _bootstrap_content_store_ensure():
    """Operator heal: bootstrap-tree ContentStore.ensure (default tree).

    Used by ``node ensure`` only — not by ``node start``. ContentMesh does not
    call this. Fail loud if utils missing or ensure raises.
    """
    module = _load_bootstrap_content_store_module(CATS_HOME)
    module.ContentStore.ensure(cwd=CATS_HOME)
    RUNTIME.contentMesh._bootstrap_content_store_ensured = True


def _bootstrap_content_store_assert_ready():
    """Strict bootstrap ContentStore.is_ready (default tree; not Order-bound).

    Kept for unit tests / callers that need a hard check. Does not heal —
    run ``node ensure`` / ``make content-store-ensure`` if Kubo is down.
    ``node start`` uses soft probe instead (§6r CAS-only).
    """
    module = _load_bootstrap_content_store_module(CATS_HOME)
    if module.ContentStore.is_ready():
        RUNTIME.contentMesh._bootstrap_content_store_ensured = True
        return
    raise RuntimeError(
        'Host Kubo ContentStore API not ready. Run '
        '`make content-store-ensure` or `uv run python -m cats.node ensure` '
        '(start soft-warns only; host Kubo TF ensure retired §6s).'
    )


def _bootstrap_content_store_soft_ready():
    """Soft bootstrap ContentStore probe for ``node start`` (§6r/§6s).

    Same posture as ContentMesh.ensure_bootstrap_content_store: warn when
    Kubo is down, never abort. CAS-only Orders do not need live Kubo.
    """
    RUNTIME.contentMesh.ensure_bootstrap_content_store()


def _handle_stop_signal(signum, frame):
    """Exit cleanly; leave optional host Kubo running if present."""
    raise SystemExit(0)


def _cmd_start():
    """Soft-probe bootstrap ContentStore, then bind Flask (§6r/§6s).

    Start does not heal and does not hard-require Kubo. Optional operator
    heal: ``node ensure`` / content-store CLI.
    SIGINT/SIGTERM must not stop Kubo.
    """
    _bootstrap_content_store_soft_ready()

    # Debug mode's reloader re-executes this script for its worker process,
    # inheriting the listening socket the monitor already created (via
    # WERKZEUG_SERVER_FD) rather than opening its own. That worker run sets
    # WERKZEUG_RUN_MAIN, so it's skipped here - otherwise the guard would
    # mistake that legitimately-inherited socket for a stale leftover and
    # kill its own monitor process out from under itself.
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        _free_stale_port(HOST, PORT)
        if _flask_listening(HOST, PORT) and not _cats_node_on_port(PORT):
            logger.error(
                'Port %s:%d is in use by a non-cats.node process '
                '(common on macOS: AirPlay Receiver on 5000). '
                'Set CAT_NODE_PORT to a free port, e.g. '
                '`CAT_NODE_PORT=5002 make node-start`.',
                HOST,
                PORT,
            )
            return 1
    signal.signal(signal.SIGINT, _handle_stop_signal)
    signal.signal(signal.SIGTERM, _handle_stop_signal)
    catNode.run(host=HOST, port=PORT, debug=True, use_reloader=False)
    return 0


def _cmd_stop():
    """Stop Flask Node only — never ContentStore / host Kubo."""
    _stop_node_process(HOST, PORT)
    if _flask_listening(HOST, PORT):
        logger.error('Node still listening on %s:%d after stop', HOST, PORT)
        return 1
    print(f'node stopped ({HOST}:{PORT})')
    return 0


def _cmd_status():
    """Report Flask listen + ContentStore readiness; exit 0 only if both OK."""
    # TCP alone is not enough — macOS AirPlay often owns :5000.
    flask_up = _cats_node_on_port(PORT)
    try:
        module = _load_bootstrap_content_store_module(CATS_HOME)
        store_ready = module.ContentStore.is_ready()
    except (RuntimeError, FileNotFoundError, OSError) as exc:
        logger.error('ContentStore status probe failed: %s', exc)
        store_ready = False

    print(f'flask={"up" if flask_up else "down"}')
    if not flask_up and _flask_listening(HOST, PORT):
        print(
            f'note: {HOST}:{PORT} accepts TCP but is not cats.node '
            f'(set CAT_NODE_PORT if AirPlay/other owns the port)',
            flush=True,
        )
    print(f'content_store={"ready" if store_ready else "not_ready"}')
    return 0 if flask_up and store_ready else 1


def _cmd_ensure():
    """Operator heal facade: bootstrap ContentStore.ensure only (no Flask)."""
    try:
        _bootstrap_content_store_ensure()
    except (RuntimeError, FileNotFoundError, OSError) as exc:
        logger.error('ContentStore bootstrap ensure failed: %s', exc)
        return 1
    print('content_store ready')
    return 0


def main(argv=None):
    """AQ-safe Node CLI: start|stop|status|ensure (default: start)."""
    parser = argparse.ArgumentParser(
        description=(
            'CAT Node process lifecycle. start soft-probes InfraStructure '
            'bootstrap ContentStore then binds Flask (Kubo optional for '
            'CAS-only); ensure heals host Kubo via ContentStore.ensure; '
            'stop kills Flask only (never host Kubo).'
        )
    )
    parser.add_argument(
        'command',
        nargs='?',
        default='start',
        choices=('start', 'stop', 'status', 'ensure'),
        help='start (default), stop, status, or ensure',
    )
    args = parser.parse_args(argv)

    if args.command == 'start':
        return _cmd_start()
    if args.command == 'stop':
        return _cmd_stop()
    if args.command == 'status':
        return _cmd_status()
    if args.command == 'ensure':
        return _cmd_ensure()
    return 1
