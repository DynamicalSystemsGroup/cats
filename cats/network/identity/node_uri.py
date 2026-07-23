"""CAT Node identity seam (Flask bind today; DID later)."""
from __future__ import annotations

import os


def node_uri() -> str:
    """Return the CAT Node URI string from ``CAT_NODE_*``.

    Same host/port defaults as ``cats.network.node_http`` / ``cats.node``.
    Not a DID — preparatory hook for W3C Node binding.
    """
    host = os.environ.get('CAT_NODE_HOST', '127.0.0.1')
    port = os.environ.get('CAT_NODE_PORT', '5000')
    return f'http://{host}:{port}'
