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
| **Content store** | Host Kubo (**legacy CID** reader / mid-migration ensure) + Node **CAS-over-HTTP** (`CasHttpStore` under `.cats/ldp/cas/`) for **new** digests | Long-lived; Kubo repo file still SoT for legacy; Node start asserts Kubo readiness for legacy/T&D; **new** mesh writes do not require Kubo add |
| **T&D** | Docker Kubo transport peers (`TransportContext`) + MinIO **scratch** (`cats-scratch`) | Structure lifetime (ILM 7d + destroy `down -v`) |
| **Durable Entity Relationship** | Second MinIO (`cats-durable`) via same `ObjectStore` façade | Node lifetime; no ILM; Structure destroy leaves volume; GC via `gc-er` only |

### One daemon, two traffic classes

A **single** host Kubo (default `127.0.0.1:5001`, one `IPFS_PATH`) carries two traffic classes — not two Quantum components and not two daemons:

| Traffic class | Role | Lifetime |
|---------------|------|----------|
| **Content-store** | Mesh / Control-Feedback content ids (Order, Invoice, BOM, Function/Structure-as-Code) via ContentMesh — **`ni:`** on CAS for new mints; legacy **CID** via Kubo | Long-lived; outlives Structure destroy and `node stop` |
| **Bitswap peer of T&D** | Host is peered to Structure Docker Kubo peers so migrate/stage can resolve host-added CIDs | Peering is Structure-lifetime; the host daemon itself is not |

**ContentMesh** (`cats.network.content_mesh`) owns content-store mesh I/O and Order compose/submit. **New writes** (`put_bytes` / `put_json` / `put_tree` / `cidDir` when `CATS_HOME` is set) go to **CAS-over-HTTP** (`CasHttpStore` + `LocatorIndex`) and return `ni:` — no Kubo add. **Legacy CID reads** (`cat` / `catObj` / `get` / `getCar` for `Qm…` / `bafy…`) go through **`AddressStore`**: when `IPFS_GATEWAY_URL` is set, prefer gateway fetch then verify; on miss/failure, fall back to Kubo RPC. **`ni:` / hex** reads resolve via locator index → `GET /ldp/cas/<hex>` → sha256 verify (fail closed). Directory trees for new content use digest-keyed manifests (`CasDirectoryManifest`); legacy directory CIDs still use CAR + UnixFS extract. Bitswap/DHT are not required for new CAS content (optional fill for legacy CIDs; T&D peering unchanged). Set `CATS_CID_VERIFY=1` to also verify RPC cats of legacy CIDs.
JSON-LD + PROV-O BOM packaging (`build_execution_bom`) with Data Integrity signing (`sign_execution_bom`, `eddsa-jcs-2022`) and Node `node_did` key material live under `cats.network.feedback` / `identity` (Phase 1b — not Plant).
The Phase 2a **control plane** (Node LDP cache + optional Solid pod dual-write / LDN) publishes signed envelopes at HTTP URIs; the **data plane** for new runs is CAS (`ni:` + `/ldp/cas/`) — see [`SOLID.md`](SOLID.md), [`BOM.md`](BOM.md), and [`W3C.md`](W3C.md). The Node-local **BOM registry** is a query index of those envelopes (plus `by-content` locators) — [`BomRegistry.md`](BomRegistry.md).
Plant CoD transport (IPFS↔MinIO job orchestration) is separate —
`cats.network.plant_transport.CoDTransport` (forthcoming; not ContentMesh).

That soft plane is intentional (Big Data–friendly Bitswap without a second swarm). Structure destroy and Node stop tear down T&D peers / Flask only — they **never** shut down host Kubo. A hard split into two Kubo swarms (isolation / firewall) is optional and out of scope unless isolation demand is concrete; see [`IPFS.md`](./IPFS.md).

Content-store is **two-phase** across **two on-disk copies** of the same helper (see [`IPFS.md`](./IPFS.md)):

- **Bootstrap (repo default):** `{CATS_HOME}/data/input/structure/.../content_store_utils.py` — Node `start` asserts `is_ready`; ContentMesh soft-warns if not ready (no auto-ensure); operator heal via `make content-store-ensure` / `node ensure`.
- **Order-submitted:** `{INPUT_STRUCTURE_HOME}/.../content_store_utils.py` — TF `shell_script.host_ipfs_daemon` ensure on **create**; `InfraStructure.apply` asserts and soft-heals once if needed.

**Republish lag:** repo edits do not affect live Orders until Structure is re-CID’d. Keep `ContentStore.ensure` thin (probe + heal + start). Node never owns shutdown.

### node-up vs content-store-ensure and node-start

Get Started uses [`make node-up`](../Makefile) as a **convenience wrapper** that runs
`content-store-ensure` then `node-start`. That does **not** mean the Node owns Kubo lifecycle —
the wrapper is Make-only; `python -m cats.node start` remains assert-only.

| Target / CLI | Role |
|--------------|------|
| `make content-store-ensure` / `uv run python -m cats.node ensure` | Operator **mutate**: repo-tree `ContentStore.ensure` (heal/start host Kubo) |
| `make node-start` / `uv run python -m cats.node start` | Client **assert**: bind Flask only if ContentStore API is already ready; does **not** heal Kubo |
| `make node-up` | Convenience: ensure, then start |

**Why keep them separate under the hood**

- **AQ ownership:** InfraStructure / the operator heal the content-store facet; the Node client only asserts readiness before binding Flask. Putting ensure inside `node start` would blur that boundary.
- **Two trees:** Bootstrap heal uses the **repo** `content_store_utils.py`. Order-submitted ensure is TF `shell_script.host_ipfs_daemon` on **create** (Order tree); `InfraStructure.apply` asserts and soft-heals once if the API is down.
- **Ops flexibility:** Use the split targets when Kubo is already up (skip ensure), or when debugging ensure vs Flask bind independently. Use `node-up` for the common “bring the node online” path.

**Republish lag** still applies: repo ensure heals the host daemon against repo-tree code; live Orders only see Order-tree changes after Structure is re-CID’d.

`TransportContext` owns peer identity, `ensure_peered`, migrate, and stage-for-plant.
Process transport callables depend on Function-owned **`TransportPort`**
(`migrate` / `stage_for_plant` only); the Executor passes
`as_transport_port(transport_context())` so Process never sees peering/assert APIs.

**Dual-path content ids:** when the stage id is `ni:` / hex, `migrate` and `stage_for_plant`
materialize via **CAS** (`materialize_tree` / `put_tree`) — no Docker Bitswap and no
unquoted `ipfs get ni:///…;…` shell split. Legacy CIDs still use Docker peer
`ipfs get`→re-add (quoted). Peering **mutate** is TF `ipfs_transport_peering` every
reconcile; Executor `apply` only **asserts** containers ready — not Process heal.
Host Kubo TF ensure is **create-once** (`host_ipfs_daemon`); `InfraStructure.apply`
soft-heals ContentStore once if the API is down after terraform (no `triggers.always`
on the host daemon — that killed live Kubo).

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
uses structure namespaces (`structures/<applied_structure_cid>/er/<name>/`) plus
`er/current/<name>` pointers (`promote_er` / `resolve_er`); GC is `gc-er` (pointer roots).

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
| **Who writes** | Ray workers (distributed) | Host/`ObjectStore` (promote explicit) | Host after stages (`cidDir` / `add_json`) |

**One line:** scratch MinIO is temporary S3 disk for parallel Ray writes before IPFS; durable
MinIO is the Node Entity Relationship corpus (structure-scoped + pointer index); IPFS is the
content-addressed record after the run.

## How they connect in one CAT execution

1. InfraFunction dispatches Process’s hotF (`integrated_subproc`) onto Plant via **PlantPort**
   (this demo: Ray Job on KubeRay).
2. Plant stages entrypoint + **ComputePort** (`RayComputePort`) into the job working_dir;
   workers write CSV shards to MinIO (`cats-scratch/jobs/<uuid>/result/`) — genuinely distributed.
3. The host downloads that **JobHandle** prefix into `…/integration/outputs/`.
4. `cidDir` adds that directory to IPFS → `invoice.integration_data_cid` (and the BOM `log` mirror).

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
- [`IPFS.md`](./IPFS.md) — host Kubo content-store facet + transport peering (`TransportContext`)
- [`DASHBOARDS.md`](./DASHBOARDS.md) — MinIO Console and IPFS WebUI
- [`LineageOfProvenance.md`](./LineageOfProvenance.md) — CIDs as Data Provenance Records
- [`DESIGN.md`](./DESIGN.md#how-the-architectural-quantum-is-realized-as-content-addressed-cids) — Order CID graph
