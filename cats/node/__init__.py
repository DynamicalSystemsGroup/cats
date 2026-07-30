"""CAT Node peer edge: Flask HTTP API and process lifecycle CLI.

Long-lived substrate is ``cats.runtime``; manufacturing is ``cats.factory``;
AQ execution is ``cats.executor``. This package is only the peer edge.
"""
from __future__ import annotations

import logging
import os
import sys

# Ray's `uv run` integration rebuilds an isolated per-worker virtualenv from
# pyproject.toml's base `dependencies` only, which omits `ray` itself (it
# lives under the optional `ops` extra) - workers then fail with
# `ModuleNotFoundError: No module named 'ray'`. Disabling it makes workers
# inherit this process's own environment instead, where `ray` is already
# installed. Must be set before anything below can spawn a Ray worker.
os.environ.setdefault('RAY_ENABLE_UV_RUN_RUNTIME_ENV', '0')

# `data/` (Process / InfraFunction packages) lives at the repo root, sibling
# to `cats/`, and isn't part of the installed `cats` package — so it's only
# importable once the repo root is on sys.path. InfraFunction unpickles those
# callables by `data.input.function.*` module paths, which requires
# `import data` to succeed in this process.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

logging.basicConfig(level=logging.DEBUG)

from cats.node.app import HOST, PORT, catNode, execute_init_cat
from cats.node.cli import main

__all__ = [
    'HOST',
    'PORT',
    'catNode',
    'execute_init_cat',
    'main',
]
