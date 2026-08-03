"""Function-owned compute port contract for Process [Composed Function] hotFs.

Process ``integrated_subproc`` callables depend on ``ComputePort`` only —
``run_transfer(batch_fn, input_path, ...)``. They must not import Ray or
Plant Job Submission APIs.

Demo batch ABI (adapter concern): ``batch_fn`` is
``Dict[str, np.ndarray] -> Dict[str, np.ndarray]``; the Plant's ComputePort
adapter maps engine batches onto that shape (see docs/INTEROP.md §2g).

The Ray job entrypoint wires Order-submitted ``RayComputePort`` into the
hotF so distributed Ray Data stays behind the Plant adapter.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ComputePort(Protocol):
    """Thin Process-facing compute surface (Function-owned contract)."""

    def run_transfer(
        self,
        batch_fn,
        input_path: str,
        *,
        zip_with_range: bool = False,
        num_partitions: int = 1,
    ):
        """Run distributed transfer; adapter defines return type (Ray: Dataset).

        ``num_partitions`` aligns Ray blocks with ingress CAR partition layout.
        """
        ...
