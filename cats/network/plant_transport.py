"""Plant CoD transport façade (Bacalhau Orchestrator + ObjectStore).

``CoDTransport`` will submit/wait/parse IPFS↔MinIO jobs using
``PlantContext.bacalhau_orchestrator_address`` and InfraStructure ``ObjectStore``.

Helper patterns to mine: ``cats.network.legacy.cod.CoD`` (submit/wait/parse).
Implementation tracked by the Bacalhau MinIO transport plan
(``.cursor/plans/bacalhau_minio_transport_*.plan.md``).

Mesh content-store + Order lifecycle stays on
``cats.network.content_mesh.ContentMesh``.
"""


class CoDTransport:
    """Plant-facing CoD / Bacalhau transport (not yet implemented)."""

    def __init__(self, *, orchestrator_address: str, object_store):
        self.orchestrator_address = orchestrator_address
        self.object_store = object_store
