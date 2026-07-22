"""Function-owned plant port contract for InfraFunction [FaaS] actuators.

InfraFunction dispatches the tHOF onto Plant via ``PlantPort`` only —
``submit_job`` / ``wait``. It must not import Ray Job Submission clients.

Order-submitted Plant adapters (e.g. ``RayPlantPort``) implement this
Protocol from ``PlantContext`` / dashboard URL.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PlantPort(Protocol):
    """Thin InfraFunction-facing Plant dispatch surface (Function-owned contract)."""

    def submit_job(self, *, entrypoint: str, working_dir: str) -> str:
        """Submit a job; return opaque job id."""
        ...

    def wait(self, job_id: str) -> None:
        """Block until job succeeds; raise RuntimeError on failure (with logs if available)."""
        ...
