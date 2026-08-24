"""Function-owned transport port contract for Process [Composed Function].

Process transport callables (ingress / integration_cache / egress) depend on
``TransportPort`` only — ``migrate`` / ``stage_for_plant``. They must not import
InfraStructure ``transport_utils`` / ``TransportContext``.

The Executor (``cats.executor.function.transport_port.as_transport_port``)
narrows Order-submitted ``TransportContext`` before invoking those callables
so Process cannot call peering/assert APIs by mistake. That facade is Node
wiring, not this Function package.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TransportPort(Protocol):
    """Thin Process-facing transport surface (Function-owned contract)."""

    def migrate(self, input_dir_id: str):
        """Migrate a content id via T&D peers; returns (id, data_dir_name)."""
        ...

    def stage_for_plant(self, input_dir_id: str, *, cwd, data_cache=None):
        """Stage ingress id onto Plant-facing integration cache; host path."""
        ...
