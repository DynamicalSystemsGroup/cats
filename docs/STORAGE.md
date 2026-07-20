# CAT Node Storage

A CAT Node's Structure deploys **InfraStructure [IaaS]** as the Transmission & Distribution (T&D) substrate for Plant
execution and provenance. That substrate includes both **IPFS** and **MinIO** (plus Docker Compose transport).
They are not separate Architectural Quantum components — they are two operational stores inside
**InfraStructure [IaaS]**. See [`PLANTs.md`](./PLANTs.md) and [`BOM.md`](./BOM.md).

## Canonical names

| Store | Component (Architectural Quantum) | Role name in CATs docs |
|-------|-----------------------------------|------------------------|
| **IPFS** | InfraStructure [IaaS] | **Content-addressed storage** (CID / Data Provenance Records) |
| **MinIO** | InfraStructure [IaaS] | **Shared object store** / **shared store** (bucket `cats-scratch`) |

There is no separate Quantum label such as “ScratchStore” vs “ProvenanceStore.” That split is operational
inside InfraStructure.

## What each store is for

| | **MinIO** (shared object store / scratch) | **IPFS** (content-addressed storage) |
|---|-------------------------------------------|--------------------------------------|
| **Type** | S3-compatible shared object store | Content-addressed store (CID graph) |
| **Role** | Plant parallel-write landing zone during a job | Durable provenance / retrieval of CAT products |
| **What lands there** | Ray result CSV shards under `cats-scratch/jobs/<uuid>/result/` | Order, Invoice, BOM, stage data (`integration_data_cid`, `data_cid`, …), Function/Structure as Code |
| **Addressing** | Bucket + key (`s3://…`) | Content hash (CID) |
| **Lifetime** | Structure lifetime (until destroy) | Survives as long as the node still has the CID |
| **Who writes** | Ray workers (distributed) | Host after stages (`cidDir` / `add_json` / etc.) |

**One line:** MinIO is temporary shared disk for parallel Ray writes; IPFS is the content-addressed record you
use after the run (`integration_data_cid` and related Invoice/BOM CIDs).

## How they connect in one CAT execution

1. InfraFunction dispatches Process’s tHOF (`integrated_subproc`) as a Ray Job on Plant [SaaS].
2. Ray workers write output CSV shards to MinIO (`cats-scratch/jobs/<uuid>/result/`) — genuinely distributed,
   without gathering onto one node’s disk.
3. The host downloads that prefix into `…/integration/outputs/`.
4. `cidDir` adds that directory to IPFS → `invoice.integration_data_cid` (and the BOM `log` mirror).

Post-run retrieval of integration outputs is via **IPFS** and that CID — not by reading MinIO. MinIO’s observed endpoints (without credentials) come from `ObjectStore.snapshot()` after `InfraStructure.obj_store_context()` and are recorded on `bom.infrastructure_snapshot_cid` so verifiers can see which shared store the distributed write landed in. Object-store and Plant config are **not** Service fields — Executor passes `object_store` and `plant` (`Plant.context()` / `PlantContext`) into Integration. Structure-lifetime scratch inspection uses the MinIO Console / S3 API or InfraStructure’s directory-model CLI (`obj_store_utils.py`) — not a CAT Node HTTP API:

```bash
# from repo root, with Structure MinIO up
uv run python data/input/structure/modules/infrastructure/obj_store_utils.py list-jobs
```

See [`MinIO.md`](./MinIO.md) for `list-files` / `get-file`, and [`BOM.md`](./BOM.md) for Invoice stage CIDs.

## Related docs

- [`MinIO.md`](./MinIO.md) — operate the Structure MinIO shared object store
- [`IPFS.md`](./IPFS.md) — host Kubo daemon lifecycle
- [`DASHBOARDS.md`](./DASHBOARDS.md) — MinIO Console and IPFS WebUI
- [`LineageOfProvenance.md`](./LineageOfProvenance.md) — CIDs as Data Provenance Records
- [`DESIGN.md`](./DESIGN.md#how-the-architectural-quantum-is-realized-as-content-addressed-cids) — Order CID graph
