"""Function-owned I/O port for partitioned ingress / egress (Plant-backed).

Process transport callables use ``IoPort`` when ``num_partitions > 1``.
They must not import Ray or Plant Job Submission APIs.

Order-submitted Plant adapters (e.g. ``RayIoPort``) implement this Protocol.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IoPort(Protocol):
    """Thin Process-facing partitioned I/O surface (Function-owned contract)."""

    def partition_ingress(
        self, input_dir_cid: str, *, num_partitions: int
    ) -> tuple[str, str]:
        """Split input CID into a partition-layout dir CID.

        Returns ``(layout_cid, dirname)`` for Invoice / integration_cache.
        """
        ...

    def partition_egress(
        self, input_dir_cid: str, *, num_partitions: int
    ) -> str:
        """Publish partition layout (or single CID) as Invoice ``data_cid`` root."""
        ...
