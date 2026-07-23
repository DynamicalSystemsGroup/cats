"""Function-owned transport port contract for Process [Composed Function].

Process transport callables (ingress / integration_cache / egress) depend on
``TransportPort`` only — ``migrate`` / ``stage_for_plant``. They must not import
InfraStructure ``transport_utils`` / ``TransportContext``.

The Executor narrows Order-submitted ``TransportContext`` with
``as_transport_port`` before invoking those callables so Process cannot call
peering/assert APIs by mistake.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TransportPort(Protocol):
    """Thin Process-facing transport surface (Function-owned contract)."""

    def migrate(self, input_dir_cid: str):
        """Migrate a CID via T&D peers; returns (cid, data_dir_name)."""
        ...

    def stage_for_plant(self, input_dir_cid: str, *, cwd, data_cache=None):
        """Stage ingress CID onto Plant-facing integration cache; host path."""
        ...


class _TransportPortView:
    """Forwards only migrate / stage_for_plant (no peering/assert surface)."""

    __slots__ = ('_inner',)

    def __init__(self, inner):
        self._inner = inner

    def migrate(self, input_dir_cid):
        return self._inner.migrate(input_dir_cid)

    def stage_for_plant(self, input_dir_cid, *, cwd, data_cache=None):
        return self._inner.stage_for_plant(
            input_dir_cid, cwd=cwd, data_cache=data_cache
        )


def as_transport_port(transport) -> TransportPort:
    """Narrow any migrate/stage adapter to the Process TransportPort surface."""
    if isinstance(transport, _TransportPortView):
        return transport
    return _TransportPortView(transport)
