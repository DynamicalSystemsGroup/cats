"""Executor-owned narrowing of Structure transport to Process TransportPort.

CFL 4A / INTEROP: Executor wires ports. ``as_transport_port`` is Node execution
machinery — not part of the Order-addressed Function CID tree. Process owns
the ``TransportPort`` Protocol (``data/input/function/process/transport_port.py``,
TYPE_CHECKING only); Structure owns ``TransportContext``. This module wraps any
migrate/stage adapter so Process callables cannot call peering/assert APIs.

Do not import the ``data`` package from ``cats``.
"""
from __future__ import annotations


class _TransportPortView:
    """Forwards only migrate / stage_for_plant (no peering/assert surface)."""

    __slots__ = ('_inner',)

    def __init__(self, inner):
        self._inner = inner

    def migrate(self, input_dir_id):
        return self._inner.migrate(input_dir_id)

    def stage_for_plant(self, input_dir_id, *, cwd, data_cache=None):
        return self._inner.stage_for_plant(
            input_dir_id, cwd=cwd, data_cache=data_cache
        )


def as_transport_port(transport):
    """Narrow any migrate/stage adapter to the Process TransportPort surface."""
    if isinstance(transport, _TransportPortView):
        return transport
    return _TransportPortView(transport)
