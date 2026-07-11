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
# [FaaS]'s ingress/egress/integration functions in
# data/input/function/process.py and InfraFunction [FaaS]'s dispatch
# functions in data/input/function/infrafunction.py) lives at the repo
# root, sibling to `cats/`, and isn't part of the installed `cats`
# package - so it's only importable once the repo root is on sys.path.
# That's needed here because InfraFunction unpickles those functions by
# their `data.input.function.process`/`data.input.function.infrafunction`
# module paths (see cats/executor/function/__init__.py), which requires
# `import data` to succeed in *this* process.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import logging, json, signal, socket, subprocess, time, traceback

from flask import Flask, request, jsonify
from cats import SERVICE

catNode = Flask(__name__)

# Overridable so multiple CAT Node peers can eventually run side-by-side
# (e.g. simulating a local mesh) - callers/peers still need to know a
# node's address out-of-band, since `cats/network/__init__.py`'s
# MeshClient hardcodes `http://127.0.0.1:5000/cat/node/*` for now.
HOST = os.environ.get('CAT_NODE_HOST', '127.0.0.1')
PORT = int(os.environ.get('CAT_NODE_PORT', 5000))


def _free_stale_port(host: str, port: int) -> None:
    """Kill any leftover node.py still bound to our port.

    Agent/chat sessions launch this server in the background and don't
    always terminate it when the session ends, so a stale process can be
    left holding the port for a future run to collide with. Only processes
    whose command line matches this script are killed - other programs on
    the port (e.g. macOS's AirPlay Receiver on 5000) are left alone.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        if probe.connect_ex((host, port)) != 0:
            return  # nothing listening, nothing to do

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
                "Killing stale node.py process (pid %s) still bound to %s:%d",
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
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.2)
                if probe.connect_ex((host, port)) != 0:
                    return  # port is free now

# Configure logging
logging.basicConfig(level=logging.DEBUG)  # Set level to DEBUG for more detailed logging
logger = logging.getLogger(__name__)


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


if __name__ == '__main__':
    # Debug mode's reloader re-executes this script for its worker process,
    # inheriting the listening socket the monitor already created (via
    # WERKZEUG_SERVER_FD) rather than opening its own. That worker run sets
    # WERKZEUG_RUN_MAIN, so it's skipped here - otherwise the guard would
    # mistake that legitimately-inherited socket for a stale leftover and
    # kill its own monitor process out from under itself.
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        _free_stale_port(HOST, PORT)
    # Run the Flask application, by default on http://127.0.0.1:5000/
    catNode.run(host=HOST, port=PORT, debug=True)