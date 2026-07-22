import os
import sys

# Ray's `uv run` integration rebuilds an isolated per-worker virtualenv from
# pyproject.toml's base `dependencies` only, which omits `ray` itself (it
# lives under the optional `ops` extra) - workers then fail with
# `ModuleNotFoundError: No module named 'ray'`. Disabling it makes workers
# inherit this process's own environment instead, where `ray` is already
# installed. Must be set before anything below can spawn a Ray worker.
os.environ.setdefault('RAY_ENABLE_UV_RUN_RUNTIME_ENV', '0')

# Running this file by path (`python cats/node.py`) only puts its own
# directory - not the repo root - on sys.path. `data/` (holding Process
# [REPL(aC)] under data/input/function/process/ and InfraFunction [FaaS]
# under data/input/function/infrafunction/) lives at the repo root, sibling
# to `cats/`, and isn't part of the installed `cats` package - so it's
# only importable once the repo root is on sys.path. That's needed here
# because InfraFunction unpickles those functions by their
# `data.input.function.process`/`data.input.function.infrafunction`
# module paths (see cats/executor/function/__init__.py), which requires
# `import data` to succeed in *this* process.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import argparse
import logging
import json
import signal
import socket
import subprocess
import time
import traceback

from flask import Flask, request, jsonify
from cats import CATS_HOME, SERVICE
from cats.network import _load_bootstrap_content_store_module

catNode = Flask(__name__)

# Overridable so multiple CAT Node peers can eventually run side-by-side
# (e.g. simulating a local mesh). MeshClient Order endpoints use the same
# CAT_NODE_HOST / CAT_NODE_PORT defaults via `_node_base_url()`.
HOST = os.environ.get('CAT_NODE_HOST', '127.0.0.1')
PORT = int(os.environ.get('CAT_NODE_PORT', 5000))

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def _flask_listening(host: str, port: int) -> bool:
    """True when something accepts TCP on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((host, port)) == 0


def _stop_node_process(host: str, port: int) -> None:
    """Kill any leftover node.py still bound to our port.

    Agent/chat sessions launch this server in the background and don't
    always terminate it when the session ends, so a stale process can be
    left holding the port for a future run to collide with. Only processes
    whose command line matches this script are killed - other programs on
    the port (e.g. macOS's AirPlay Receiver on 5000) are left alone.

    Never touches InfraStructure ContentStore (host Kubo).
    """
    if not _flask_listening(host, port):
        return

    try:
        pids = subprocess.run(
            ['lsof', '-t', f'-i:{port}', '-sTCP:LISTEN'],
            capture_output=True, text=True, timeout=5,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
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

        if not info or 'node.py' not in info:
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
            if 'node.py' not in parent_cmd:
                continue
            logger.warning(
                "Killing node.py process (pid %s) still bound to %s:%d",
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
    """Alias used by start — clear a prior node.py listener before bind."""
    _stop_node_process(host, port)


def _bootstrap_content_store_ensure():
    """Operator heal: bootstrap-tree ContentStore.ensure (default tree).

    Used by ``node ensure`` only — not by ``node start``. MeshClient does not
    call this. Fail loud if utils missing or ensure raises.
    """
    module = _load_bootstrap_content_store_module(CATS_HOME)
    module.ContentStore.ensure(cwd=CATS_HOME)
    SERVICE.meshClient._bootstrap_content_store_ensured = True


def _bootstrap_content_store_assert_ready():
    """Strict bootstrap ContentStore.is_ready (default tree; not Order-bound).

    Used by ``node start``. Does not heal — run ``node ensure`` /
    ``make content-store-ensure`` first if Kubo is down.
    """
    module = _load_bootstrap_content_store_module(CATS_HOME)
    if module.ContentStore.is_ready():
        SERVICE.meshClient._bootstrap_content_store_ensured = True
        return
    raise RuntimeError(
        'Host Kubo ContentStore API not ready. Run '
        '`make content-store-ensure` or `uv run python cats/node.py ensure` '
        'before node start (start asserts only; TF host_ipfs_daemon create '
        'is the sole automatic Order-submitted ensure).'
    )


@catNode.route('/cat/node/init', methods=['POST'])
def execute_init_cat():
    try:
        order_request = request.get_json()
        order_request["order"] = json.loads(SERVICE.meshClient.cat(order_request["order_cid"]))
        order_request['invoice'] = json.loads(SERVICE.meshClient.cat(order_request['order']['invoice_cid']))

        # IPFS checks
        # if 'bom_cid' not in bom:
        #     return jsonify({'error': 'CID not provided'}), 400

        catFactory, updated_order_request = SERVICE.initFactory(
            order_request, order_request["invoice"]["data_cid"]
        )
        bom_response = SERVICE.execute(catFactory, updated_order_request)

        # Return BOM
        response = jsonify(bom_response)
        return response

    except Exception as e:
        logger.error("An error occurred: %s", traceback.format_exc())
        response = jsonify({'error': str(e)})
        return response


def _handle_stop_signal(signum, frame):
    """Exit cleanly; leave InfraStructure content-store (host Kubo) running."""
    raise SystemExit(0)


def _cmd_start():
    """Assert bootstrap ContentStore ready (strict), then bind Flask.

    Host Kubo is InfraStructure's long-lived content-store facet — Node is
    only a client. Start does not heal; use ``node ensure`` / content-store
    CLI. SIGINT/SIGTERM must not stop Kubo.
    """
    try:
        _bootstrap_content_store_assert_ready()
    except (RuntimeError, FileNotFoundError, OSError) as exc:
        logger.error('ContentStore bootstrap assert failed: %s', exc)
        return 1

    # Debug mode's reloader re-executes this script for its worker process,
    # inheriting the listening socket the monitor already created (via
    # WERKZEUG_SERVER_FD) rather than opening its own. That worker run sets
    # WERKZEUG_RUN_MAIN, so it's skipped here - otherwise the guard would
    # mistake that legitimately-inherited socket for a stale leftover and
    # kill its own monitor process out from under itself.
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        _free_stale_port(HOST, PORT)
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
    flask_up = _flask_listening(HOST, PORT)
    try:
        module = _load_bootstrap_content_store_module(CATS_HOME)
        store_ready = module.ContentStore.is_ready()
    except (RuntimeError, FileNotFoundError, OSError) as exc:
        logger.error('ContentStore status probe failed: %s', exc)
        store_ready = False

    print(f'flask={"up" if flask_up else "down"}')
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
            'CAT Node process lifecycle. start asserts InfraStructure '
            'bootstrap ContentStore ready then binds Flask; ensure heals '
            'host Kubo via ContentStore.ensure; stop kills Flask only '
            '(never host Kubo).'
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


if __name__ == '__main__':
    raise SystemExit(main())