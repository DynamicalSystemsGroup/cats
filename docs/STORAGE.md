# CAT Node Storage

A CAT Node's Structure deploys **InfraStructure [IaaS]** as the Transmission & Distribution (T&D) substrate for Plant
execution and provenance. That substrate includes both **IPFS** and **MinIO** (plus Docker Compose transport).
They are not separate Architectural Quantum components — they are two operational stores inside
**InfraStructure [IaaS]**. See [`PLANTs.md`](./PLANTs.md) and [`BOM.md`](./BOM.md).

**MinIO is [S3-compatible](https://min.io/product/s3-compatibility):** Plant scratch and durable
Entity Relationship use the S3 API (`s3://…` URIs, bucket/key layout) via InfraStructure’s
`ObjectStore` / `JobHandle`. Two hard-isolated MinIO daemons (scratch + durable) share that
contract; object-store config is **not** a Runtime field — see [`MinIO.md`](./MinIO.md) and
[`INTEROP.md`](./INTEROP.md).

## Facets inside InfraStructure (still one Quantum component)

| Facet | What | Lifetime |
|-------|------|----------|
| **Content store** | Node **CAS-over-HTTP** (`CasHttpStore` under `.cats/ldp/cas/`) — address of record for live Orders; optional host Kubo for operator tooling only (§6s) | Long-lived CAS; Kubo optional |
| **T&D** | MinIO **scratch** (`cats-scratch`) for Plant parallel writes (Docker Kubo peers retired §6s) | Structure lifetime (ILM 7d + destroy `down -v`) |
| **Durable Entity Relationship** | Second MinIO (`cats-durable`) via same `ObjectStore` façade | Node lifetime; no ILM; Structure destroy leaves volume; GC via `gc-er` only |

### ContentMesh + Process transport

**ContentMesh** (`cats.network.content_mesh`) owns content-store mesh I/O and Order compose/submit. Writes (`put_bytes` / `put_json` / `put_tree` / `put_dir` / `put_file`) require **`CATS_HOME`** and go to **CAS-over-HTTP** (`CasHttpStore` + `LocatorIndex`) → `ni:` (§6r). Reads resolve `ni:` / hex / `hl:` / `http(s)` via AddressStore (sha256 verify; fail closed). **Legacy CIDs fail closed** (§6s).

JSON-LD + PROV-O BOM packaging (`build_execution_bom`) with Data Integrity signing (`sign_execution_bom`, `eddsa-jcs-2022`) and Node `node_did` key material live under `cats.network.feedback` / `identity` (Phase 1b — not Plant).
The Phase 2a **control plane** (Node LDP cache + optional Solid pod dual-write / LDN) publishes signed envelopes at HTTP URIs; the **data plane** is CAS (`ni:` + `/ldp/cas/`) — see [`SOLID.md`](SOLID.md), [`BOM.md`](BOM.md), and [`W3C.md`](W3C.md). The Node-local **BOM registry** is a query index of those envelopes (plus `by-content` locators) — [`BomRegistry.md`](BomRegistry.md).

Optional Kubo: Node `start` / Structure `apply` soft-probe ContentStore; operator heal via `make content-store-ensure` / `node ensure` ([`IPFS.md`](./IPFS.md)).

### node-up vs content-store-ensure and node-start

Get Started uses [`make node-up`](../Makefile) as a **convenience wrapper** that runs
`content-store-ensure` then `node-start`. That does **not** mean the Node owns Kubo lifecycle —
the wrapper is Make-only; `python -m cats.node start` soft-probes and does not hard-require Kubo (§6r/§6s).

| Target / CLI | Role |
|--------------|------|
| `make content-store-ensure` / `uv run python -m cats.node ensure` | Optional operator **mutate**: repo-tree `ContentStore.ensure` |
| `make node-start` / `uv run python -m cats.node start` | Soft probe + bind Flask; Kubo not required |
| `make node-up` | Convenience: ensure, then start |

`TransportContext` owns CAS `migrate` / `stage_for_plant` only (§6s — no Docker peers).
Process transport callables depend on Function-owned **`TransportPort`**; the Executor
narrows Structure `TransportContext` with **`cats.executor.function.as_transport_port`**
(CFL 4A — Node wiring, not the Function CID tree).

**CAS-only content ids:** `migrate` and `stage_for_plant` accept `ni:` / hex / HTTP only.
Legacy CIDs fail closed (§6s).

Process hotFs depend on Function-owned **`ComputePort`** (`run_transfer`); the Plant-owned
Ray job entrypoint (staged by **`RayPlantPort.submit_job`**) wires **`RayComputePort`**
(no `import ray` in Process). Demo **batch ABI** is
`Dict[str, np.ndarray] -> Dict[str, np.ndarray]` — the ComputePort adapter maps engine
batches onto that shape (see [`INTEROP.md`](./INTEROP.md) §2g). InfraFunction dispatches
via Function-owned **`PlantPort`** (`submit_job` / `wait`); Executor passes
`Plant.plant_port()` → Structure **`RayPlantPort`**. `ObjectStore.write_job_scratch`
stages scratch MinIO config only. Scratch correlator is
**`ObjectStore.begin_job()` → `JobHandle`** (BOM `object_store_result_uri`;
`result_uri` / `download_job_result` are JobHandle-only). Durable Entity Relationship
uses structure namespaces (`structures/<applied_structure_id>/er/<name>/`) plus
`er/current/<name>` pointers (`promote_er` / `resolve_er`; pointer JSON key
`structure_id`, with legacy `structure_cid` readable one cycle). GC is `gc-er`
(pointer roots; CLI `--structure-id`).

There is no separate Quantum label such as “ScratchStore” vs “ProvenanceStore.” Content-store,
T&D scratch, and durable Entity Relationship are lifetime facets inside InfraStructure.

## Canonical names

| Store | Component (Architectural Quantum) | Role name in CATs docs |
|-------|-----------------------------------|------------------------|
| **IPFS** | InfraStructure [IaaS] | **Legacy CID** content-store + T&D transport peers; **new** digests on Node CAS (`ni:` / `/ldp/cas/`) |
| **MinIO scratch** | InfraStructure [IaaS] | **S3-compatible scratch** (`cats-scratch`) — T&D / job landing → IPFS |
| **MinIO durable** | InfraStructure [IaaS] | **S3-compatible Entity Relationship store** (`cats-durable`) — structure NS + `er/current` index |

## What each store is for

| | **Scratch MinIO** | **Durable Entity Relationship MinIO** | **IPFS** |
|---|-------------------------------------------|--------------------------------------|----------|
| **Type** | S3-compatible (Structure-lifetime) | S3-compatible (Node-lifetime) | Content-addressed store (CID graph) |
| **Role** | Plant parallel-write landing → IPFS | Ray Entity Relationship lookups across Structures | Durable provenance / CAT products |
| **What lands there** | `cats-scratch/jobs/<uuid>/result/` | `cats-durable/structures/<cid>/er/<name>/` + `er/current/<name>` | Order, Invoice, BOM, stage CIDs |
| **Addressing** | Bucket + key (`s3://…`) | Bucket + key (`s3://…`) | Content hash (CID) |
| **Lifetime** | ILM 7d + Structure destroy `down -v` | No ILM; survives destroy; `gc-er` only | Host Kubo outlives Structure destroy |
| **Who writes** | Ray workers (distributed) | Host/`ObjectStore` (promote explicit) | Host after stages (`put_dir` / `put_json`) |

**One line:** scratch MinIO is temporary S3 disk for parallel Ray writes before IPFS; durable
MinIO is the Node Entity Relationship corpus (structure-scoped + pointer index); IPFS is the
content-addressed record after the run.

## How they connect in one CAT execution

1. InfraFunction dispatches Process’s hotF (`integrated_subproc`) onto Plant via **PlantPort**
   (this demo: Ray Job on KubeRay).
2. Plant stages entrypoint + **ComputePort** (`RayComputePort`) into the job working_dir;
   workers write CSV shards to MinIO (`cats-scratch/jobs/<uuid>/result/`) — genuinely distributed.
3. The host downloads that **JobHandle** prefix into `…/integration/outputs/`.
4. `put_dir` / `put_tree` addresses that directory → `invoice.data_uri` (and the BOM `log` mirror).

Post-run retrieval of integration outputs is via **IPFS** and that CID — not by reading scratch
MinIO. `ObjectStore.snapshot()` records credential-free scratch **and** durable endpoints/buckets
as `object_store_as_executed_cid` under Invoice `structure_as_executed_cid` (see
[`BOM.md` Nest tree](BOM.md#cat-node-http-bom-response)). Object-store, Plant, and transport
config are **not** Runtime fields. Inspection uses MinIO Consoles / S3 / `obj_store_utils.py`
CLI — not a CAT Node HTTP API:

```bash
uv run python data/input/structure/infrastructure/obj_store_utils.py list-jobs
uv run python data/input/structure/infrastructure/obj_store_utils.py resolve-er <name>
uv run python data/input/structure/infrastructure/obj_store_utils.py gc-er --dry-run
```

See [`MinIO.md`](./MinIO.md) and [`BOM.md`](./BOM.md) for Invoice stage CIDs.

## Related docs

- [`NodeLifeCycle.md`](./NodeLifeCycle.md) — start / stop / status / ensure (Node process lifecycle)
- [`INTEROP.md`](./INTEROP.md) — prove Plant/T&D interoperability per AQ component (incl. second Plant)
- [`MinIO.md`](./MinIO.md) — operate the Structure MinIO shared object store
- [`IPFS.md`](./IPFS.md) — optional host Kubo content-store facet; CAS-only `TransportContext` (§6s)
- [`DASHBOARDS.md`](./DASHBOARDS.md) — MinIO Console and IPFS WebUI
- [`LineageOfProvenance.md`](./LineageOfProvenance.md) — CIDs as Data Provenance Records
- [`DESIGN.md`](./DESIGN.md#how-the-architectural-quantum-is-realized-as-content-addressed-cids) — Order CID graph
