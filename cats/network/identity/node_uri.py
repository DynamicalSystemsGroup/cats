"""CAT Node HTTP service URI (Flask bind; not BOM attribution).

BOM attribution uses ``node_did()`` — see ``cats.network.identity.node_did``.
Order HTTP endpoints use ``cats.network.node_http``.
"""
from __future__ import annotations

import os


def node_uri() -> str:
    """Return the CAT Node HTTP URI string from ``CAT_NODE_*``.

    Same host/port defaults as ``cats.network.node_http`` / ``cats.node``.
    Not used on the BOM envelope — use ``node_did`` for attribution.
    """
    host = os.environ.get('CAT_NODE_HOST', '127.0.0.1')
    port = os.environ.get('CAT_NODE_PORT', '5000')
    return f'http://{host}:{port}'
