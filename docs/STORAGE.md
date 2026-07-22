# CAT Node Storage

A CAT Node's Structure deploys **InfraStructure [IaaS]** as the Transmission & Distribution (T&D) substrate for Plant
execution and provenance. That substrate includes both **IPFS** and **MinIO** (plus Docker Compose transport).
They are not separate Architectural Quantum components — they are two operational stores inside
**InfraStructure [IaaS]**. See [`PLANTs.md`](./PLANTs.md) and [`BOM.md`](./BOM.md).

## Facets inside InfraStructure (still one Quantum component)

| Facet | What | Lifetime |
|-------|------|----------|
| **Content store** | Host Kubo (`ContentStore` in `content_store_utils.py`) | Long-lived; repo file is SoT (ships in `infrastructure_cid`); **Node start** asserts bootstrap readiness; operator/`node ensure`/TF `host_ipfs_daemon` create mutate; Executor `apply` only **asserts** Order tree; **not** killed on Structure destroy or `node stop` |
| **T&D** | Docker Kubo transport peers (`TransportContext` in `transport_utils.py`) + MinIO scratch (`ObjectStore`) | Structure lifetime (until destroy), with Plant |

### One daemon, two traffic classes

A **single** host Kubo (default `127.0.0.1:5001`, one `IPFS_PATH`) carries two traffic classes — not two Quantum components and not two daemons:

| Traffic class | Role | Lifetime |
|---------------|------|----------|
| **Content-store** | Mesh / Control-Feedback CIDs (Order, Invoice, BOM, Function/Structure-as-Code) via MeshClient | Long-lived; outlives Structure destroy and `node stop` |
| **Bitswap peer of T&D** | Host is peered to Structure Docker Kubo peers so migrate/stage can resolve host-added CIDs | Peering is Structure-lifetime; the host daemon itself is not |

That soft plane is intentional (Big Data–friendly Bitswap without a second swarm). Structure destroy and Node stop tear down T&D peers / Flask only — they **never** shut down host Kubo. A hard split into two Kubo swarms (isolation / firewall) is optional and out of scope unless isolation demand is concrete; see [`IPFS.md`](./IPFS.md).

Content-store is **two-phase** across **two on-disk copies** of the same helper (see [`IPFS.md`](./IPFS.md)):

- **Bootstrap (repo default):** `{CATS_HOME}/data/input/structure/.../content_store_utils.py` — Node `start` asserts `is_ready`; MeshClient soft-warns if not ready (no auto-ensure); operator heal via `make content-store-ensure` / `node ensure`.
- **Order-submitted:** `{INPUT_STRUCTURE_HOME}/.../content_store_utils.py` — TF `shell_script.host_ipfs_daemon` create is the sole **automatic** ensure; `InfraStructure.apply` only asserts.

**Republish lag:** repo edits do not affect live Orders until Structure is re-CID’d. Keep `ContentStore.ensure` thin (probe + heal + start). Node never owns shutdown.

### node-up vs content-store-ensure and node-start

Get Started uses [`make node-up`](../Makefile) as a **convenience wrapper** that runs
`content-store-ensure` then `node-start`. That does **not** mean the Node owns Kubo lifecycle —
the wrapper is Make-only; `cats/node.py start` remains assert-only.

| Target / CLI | Role |
|--------------|------|
| `make content-store-ensure` / `uv run python cats/node.py ensure` | Operator **mutate**: repo-tree `ContentStore.ensure` (heal/start host Kubo) |
| `make node-start` / `uv run python cats/node.py start` | Client **assert**: bind Flask only if ContentStore API is already ready; does **not** heal Kubo |
| `make node-up` | Convenience: ensure, then start |

**Why keep them separate under the hood**

- **AQ ownership:** InfraStructure / the operator heal the content-store facet; the Node client only asserts readiness before binding Flask. Putting ensure inside `node start` would blur that boundary.
- **Two trees:** Bootstrap heal uses the **repo** `content_store_utils.py`. The sole **automatic** Order-submitted ensure is TF `shell_script.host_ipfs_daemon` create (Order tree). Executor `apply` only asserts Order-tree readiness.
- **Ops flexibility:** Use the split targets when Kubo is already up (skip ensure), or when debugging ensure vs Flask bind independently. Use `node-up` for the common “bring the node online” path.

**Republish lag** still applies: repo ensure heals the host daemon against repo-tree code; live Orders only see Order-tree changes after Structure is re-CID’d.

`TransportContext` owns peer identity, `ensure_peered`, migrate, and stage-for-plant.
Process transport callables depend on Function-owned **`TransportPort`**
(`migrate` / `stage_for_plant` only); the Executor passes
`as_transport_port(transport_context())` so Process never sees peering/assert APIs.
Peering **mutate** is TF `ipfs_transport_peering` every reconcile; Executor `apply`
only **asserts** containers ready — not Process heal.

Process tHOFs depend on Function-owned **`ComputePort`** (`run_transfer`); the Plant-owned
Ray job entrypoint (staged by **`RayPlantPort.submit_job`**) wires **`RayComputePort`**
(no `import ray` in Process). Demo **batch ABI** is
`Dict[str, np.ndarray] -> Dict[str, np.ndarray]` — the ComputePort adapter maps engine
batches onto that shape (see [`INTEROP.md`](./INTEROP.md) §2g). InfraFunction dispatches
via Function-owned **`PlantPort`** (`submit_job` / `wait`); Executor passes
`Plant.plant_port()` → Structure **`RayPlantPort`**. `ObjectStore.write_job_scratch`
stages MinIO config only. Scratch correlator is
**`ObjectStore.begin_job()` → `JobHandle`** (BOM `object_store_result_uri`;
`result_uri` / `download_job_result` are JobHandle-only).

There is no separate Quantum label such as “ScratchStore” vs “ProvenanceStore.” Content-store vs T&D is an
operational lifetime split inside InfraStructure; the host daemon’s two traffic classes (above) sit on that
same soft plane.

## Canonical names

| Store | Component (Architectural Quantum) | Role name in CATs docs |
|-------|-----------------------------------|------------------------|
| **IPFS** | InfraStructure [IaaS] | **Content-addressed storage** (CID / Data Provenance Records) — content-store facet (host Kubo); transport peers are T&D |
| **MinIO** | InfraStructure [IaaS] | **Shared object store** / **shared store** (bucket `cats-scratch`) — T&D facet |

## What each store is for

| | **MinIO** (shared object store / scratch) | **IPFS** (content-addressed storage) |
|---|-------------------------------------------|--------------------------------------|
| **Type** | S3-compatible shared object store | Content-addressed store (CID graph) |
| **Role** | Plant parallel-write landing zone during a job | Durable provenance / retrieval of CAT products |
| **What lands there** | Ray result CSV shards under `cats-scratch/jobs/<uuid>/result/` | Order, Invoice, BOM, stage data (`integration_data_cid`, `data_cid`, …), Function/Structure as Code |
| **Addressing** | Bucket + key (`s3://…`) | Content hash (CID) |
| **Lifetime** | Structure lifetime (until destroy) | Host Kubo content-store outlives Structure destroy; CIDs survive as long as the node still has them |
| **Who writes** | Ray workers (distributed) | Host after stages (`cidDir` / `add_json` / etc.) |

**One line:** MinIO is temporary shared disk for parallel Ray writes; IPFS is the content-addressed record you
use after the run (`integration_data_cid` and related Invoice/BOM CIDs).

## How they connect in one CAT execution

1. InfraFunction dispatches Process’s tHOF (`integrated_subproc`) onto Plant via **PlantPort**
   (this demo: Ray Job on KubeRay).
2. Plant stages entrypoint + **ComputePort** (`RayComputePort`) into the job working_dir;
   workers write CSV shards to MinIO (`cats-scratch/jobs/<uuid>/result/`) — genuinely distributed.
3. The host downloads that **JobHandle** prefix into `…/integration/outputs/`.
4. `cidDir` adds that directory to IPFS → `invoice.integration_data_cid` (and the BOM `log` mirror).

Post-run retrieval of integration outputs is via **IPFS** and that CID — not by reading MinIO. MinIO’s observed endpoints (without credentials) come from `ObjectStore.snapshot()` after `InfraStructure.obj_store_context()` and are recorded on `bom.infrastructure_snapshot_cid` so verifiers can see which shared store the distributed write landed in. Object-store, Plant, and transport config are **not** Service fields — Executor passes `object_store`, **`PlantPort`** (`Plant.plant_port()`), and a narrowed **`TransportPort`** into Function stages. Structure-lifetime scratch inspection uses the MinIO Console / S3 API or InfraStructure’s directory-model CLI (`obj_store_utils.py`) — not a CAT Node HTTP API:

```bash
# from repo root, with Structure MinIO up
uv run python data/input/structure/infrastructure/obj_store_utils.py list-jobs
```

See [`MinIO.md`](./MinIO.md) for `list-files` / `get-file`, and [`BOM.md`](./BOM.md) for Invoice stage CIDs.

## Related docs

- [`INTEROP.md`](./INTEROP.md) — prove Plant/T&D interoperability per AQ component (incl. second Plant)
- [`MinIO.md`](./MinIO.md) — operate the Structure MinIO shared object store
- [`IPFS.md`](./IPFS.md) — host Kubo content-store facet + transport peering (`TransportContext`)
- [`DASHBOARDS.md`](./DASHBOARDS.md) — MinIO Console and IPFS WebUI
- [`LineageOfProvenance.md`](./LineageOfProvenance.md) — CIDs as Data Provenance Records
- [`DESIGN.md`](./DESIGN.md#how-the-architectural-quantum-is-realized-as-content-addressed-cids) — Order CID graph
