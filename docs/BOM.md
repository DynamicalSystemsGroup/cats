# What's Inside a BOM's Content Ids

**Addressing note:** **new** Order / Invoice / Function / Structure / stage / BOM bytes mint as **`ni:`** digests on [CAS-over-HTTP](STORAGE.md) and also carry HTTP **`*_uri`** (Phase 2b dual-field: URI = address of record for fetch; `*_cid` / `ni:` = equality / lineage). Historical examples and field names still say `*_cid` / `ipfs cat` / `ipfs ls` — those apply to **legacy CID** content; for `ni:` / URI use AddressStore / `GET /ldp/cas/<hex>` / `GET /ldp/invoices|orders/…` (or mesh `cat` / `get`).

Each of the Architectural Quantum's four components (Function, InfraFunction, Structure, InfraStructure) is content-addressed independently, then paired back together as a small JSON object so the Order records both halves under a single content id:

- `order.function_cid` resolves to `{process_cid, infrafunction_cid, process_source_cid, infrafunction_source_cid}` — hybrid Function pairing. `process_cid` / `infrafunction_cid` are bind JSON maps of `*_subproc_cid` → **leaf CID** (still a single string per slot). Process [Composed Function] holds (`ingress_subproc_cid`, `integration_cache_subproc_cid`, `integrated_subproc_cid`, `egress_subproc_cid`); only `integrated_subproc_cid` is the Higher-Order Transfer Function (hotF) — Plant-agnostic `ComputePort.run_transfer` (see [transfer function](https://en.wikipedia.org/wiki/Transfer_function)); ingress / integration_cache / egress are transport **port** callables that require Executor-wired `TransportPort`. `infrafunction_cid` bind JSON holds InfraFunction [Actuator] (`infrafunction_subproc_cid`). Each leaf CID is either **named-bind JSON** `{"source_cid","module","qualname"}` (stock public callables from `create_order_request` / `linkProcess`) or **pickle bytes** (REPL escape hatch for non-stock callables). `process_source_cid` / `infrafunction_source_cid` are whole-directory CIDs of `function/process/` and `function/infrafunction/`; named binds must pin those package CIDs. `getEnhancedBom()` materializes the source trees; Executor `resolve_subproc` imports named binds or unpickles. Recreate Orders created before source keys existed — `getEnhancedBom()` / `linkProcess()` / Executor fail loud if they are missing. Compose Orders with **named imports** of the Process public surface only (`ingress`, `egress`, `integration_cache`, `function_*`, `process_*` — see `process.__all__`); never `from data.input.function.process import *`.
- `order.structure_cid` resolves to `{root_cid, plant_cid, infrastructure_cid}` — apply-complete Structure pairing. `root_cid` is the directory CID of compose glue only (`main.tf`, `outputs.tf`, `.terraform.lock.hcl` — providers + `module "plant"` / `module "infrastructure"` wiring). `plant_cid` is the CID of the whole `plant/` Terraform directory (kind cluster + Helm releases, `plant_utils.py` / `RayPlantPort`, and Ray landing `ray_job_result_entrypoint.py` + `ray_compute_utils.py` / `RayComputePort` that constitute Plant, SaaS); `infrastructure_cid` is the CID of the whole `infrastructure/` Terraform directory (Docker Kubo transport + `transport_utils.py` / `TransportContext`, MinIO + `obj_store_utils.py` / `JobHandle`, host ContentStore helpers that constitute InfraStructure, IaaS). Recreate Orders created before `root_cid` existed — `getEnhancedBom()` fails loud if it is missing.

Both are built in `create_order_request()` and unpacked back onto disk by `getEnhancedBom()` so the fetched Structure stays directly `terraform apply`-able from the Order alone (root files + `plant/` + `infrastructure/`) and Function source packages land under `function/process/` + `function/infrafunction/`. `root_cid`/`plant_cid`/`infrastructure_cid` and `process_source_cid`/`infrafunction_source_cid` are each whole-directory CIDs (via `cidDir()`) — `ipfs ls`-ing plant/infra lists that Terraform module's actual files (e.g. `main.tf`, `outputs.tf`, `variables.tf`, `plant_utils.py`, `ray_job_result_entrypoint.py`, `ray_compute_utils.py` for `plant_cid`; `main.tf`, `outputs.tf`, `minio_scratch_compose.yaml`, `minio_durable_compose.yaml`, `ipfs_transport_compose.yaml`, `transport_utils.py`, `content_store_utils.py`, `obj_store_utils.py` for `infrastructure_cid`); `ipfs ls`-ing a Function source CID lists that package's Python modules. `process_cid`/`infrafunction_cid` remain CIDs of small JSON objects mapping slots to leaf CIDs. A real `function_cid` fetched via `ipfs cat` looks like:

```json
{
  "process_cid": "QmProcessBindJson…",
  "infrafunction_cid": "QmInfraFunctionBindJson…",
  "process_source_cid": "QmProcessPackageDir…",
  "infrafunction_source_cid": "QmInfraFunctionPackageDir…"
}
```

A stock named-bind leaf (`ipfs cat` of e.g. `integrated_subproc_cid`) looks like:

```json
{
  "source_cid": "QmProcessPackageDir…",
  "module": "data.input.function.process.callables",
  "qualname": "process_0"
}
```

A real `structure_cid` fetched via `ipfs cat` looks like:

```json
{
  "root_cid": "QmRootComposeGlueAllowlistDir…",
  "plant_cid": "QmaxYkAmJogHAmHMgYLLuxETjeUxQMqu1NkowmM12EEqMM",
  "infrastructure_cid": "Qmf1SZni9CyMhTQCCCp2qVYxwGSPGojdPS7DDGgTR1xwkt"
}
```

The sibling `order.structure_filepath` field just records the directory name (e.g. `structure`) so `getEnhancedBom()` knows where to materialize root glue and each fetched module locally (`structure_filepath/` for root files, `structure_filepath/plant`, `structure_filepath/infrastructure`); `flatten_bom()` surfaces the parsed `{root_cid, plant_cid, infrastructure_cid}` object under `invoice.order.flat.structure` for inspection.

### CAT Node HTTP BOM response

`Runtime.execute()` returns `{ bom_cid, bom, bom_ldp_uri, bom_solid_uri }`. The HTTP envelope's `bom` is a **JSON-LD + PROV-O** package (`build_execution_bom`) holding address refs only: `invoice_cid`, `log_cid`, `node_did`, plus `@context` / `@type` / `prov:wasAttributedTo` / `prov:wasGeneratedBy` (`#executorRun`), and **`stageLineage`** (`prov:Entity` nodes with `prov:wasDerivedFrom` along Invoice stage CIDs), then **signed** with a W3C Data Integrity proof (`sign_execution_bom`, cryptosuite `eddsa-jcs-2022`). Observed Plant / InfraStructure state is nested under the Invoice as `structure_as_executed_cid` — parallel to as-Code `order.structure_cid`, but a different CID/bytes (observation, not IaC); that CID also appears in `stageLineage` as generated-by the same activity (not on the payload derivation chain). Executor mints that nest bottom-up **before** `invoice_cid`. `infrastructure_as_executed` currently carries only `object_store_as_executed_cid` (`InfraStructure.snapshot`); transport / ContentStore facets may widen later. `bom_cid` is response-only (never written into the CID'd `bom` object) and is the CID of the **signed** BOM (proof included). `bom_ldp_uri` is the Phase 2a Node LDP cache locator (`http://{CAT_NODE_HOST}:{CAT_NODE_PORT}/ldp/boms/{bom_cid}`) — also persisted under `{CATS_HOME}/.cats/ldp/boms/` for `GET`. When Solid is configured (`SOLID_POD_BASE_URL`), `bom_solid_uri` is the dual-published pod locator; peers may `fetch_bom_envelope` on either URI, verify the proof, and resolve CID refs via AddressStore. See [`SOLID.md`](SOLID.md). HTTP Flask bind is Node lifecycle — **not** BOM attribution; attribution is `node_did` (`did:key:…` from `{CATS_HOME}/.cats/node_did.json`, or `CAT_NODE_DID` when it matches that keyfile).

```text
HTTP JSON response  (Runtime.execute → jsonify)
├── bom_cid       →  content-address of the `bom` object below
├── bom_ldp_uri   →  Node LDP GET locator (local cache)
├── bom_solid_uri →  Solid pod URI when configured (else null)
│
└── bom  →  signed JSON-LD / PROV-O ExecutionBom (Data Integrity)
    │
    ├── @context / @type  (includes data-integrity/v2)
    ├── invoice_cid  →  output Invoice JSON
    │   │   Minted by Executor after as-executed CIDs are written.
    │   │
    │   ├── order_cid  →  Order JSON  (as-Code Quantum input)
    │   │   ├── invoice_cid          input Invoice
    │   │   ├── function_cid
    │   │   │   ├── process_cid / infrafunction_cid
    │   │   │   └── process_source_cid / infrafunction_source_cid
    │   │   └── structure_cid        as-Code Structure pairing
    │   │       ├── root_cid
    │   │       ├── plant_cid
    │   │       └── infrastructure_cid
    │   │
    │   ├── data_cid
    │   ├── ingress_data_cid
    │   ├── integration_data_cid
    │   ├── seed_cid  →  Seed JSON  (#187)
    │   │       {seed, rng_seed, num_partitions} — replay dictionary
    │   │
    │   └── structure_as_executed_cid  →  observed Structure pairing JSON
    │       ├── plant_as_executed_cid  →  Plant.snapshot() dict
    │       │       kind/Ray/applied_structure_cid/rebuilt, …
    │       └── infrastructure_as_executed_cid  →  InfraStructure.snapshot() dict
    │           └── object_store_as_executed_cid  →  ObjectStore.snapshot() dict
    │                   minio endpoints/bucket (no secrets)
    │                   # later: transport_*, content_store_*, …
    │
    ├── log_cid  →  log JSON
    │       stage CID mirrors, plant_rebuilt, object_store_result_uri,
    │       durable_er_uri / durable_er_pointer (optional)
    │
    ├── node_did  (DID string, not a CID; not the Flask HTTP URL)
    │       did:key:…  (keyfile; CAT_NODE_DID only if it matches)
    ├── prov:wasAttributedTo  →  { @id: node_did }
    ├── prov:wasGeneratedBy   →  #executorRun Activity
    │       prov:used → ipfs://<order_cid>, ipfs://<invoice_cid>
    ├── stageLineage  →  [ prov:Entity … ]  (ipfs:// stage CIDs)
    │       wasGeneratedBy #executorRun;
    │       wasDerivedFrom along data←integration←ingress←input
    │       structure_as_executed: generated-by only (observation)
    └── proof  →  DataIntegrityProof (eddsa-jcs-2022)
            type, cryptosuite, created, verificationMethod,
            proofPurpose, proofValue (multibase z…)
```

Example `plant_as_executed` content (`Plant.snapshot()` after `Structure.reconcile()`):

```json
{"applied_structure_cid":"QmXe7n5auVw94fv3Xu6rZQqQWfGpXZnMq5u6ubKCM6yYK1","kind_cluster_name":"cats","kubeconfig_context":"kind-cats","ray_dashboard_address":"http://127.0.0.1:8265","ray_release_name":"raycluster","rebuilt":false}
```

Example `object_store_as_executed` content (`ObjectStore.snapshot()` after `InfraStructure.obj_store_context()` — credentials excluded; scratch + durable Entity Relationship):

```json
{"minio_scratch_bucket":"cats-scratch","minio_scratch_endpoint_host":"http://127.0.0.1:9000","minio_scratch_endpoint_pod":"http://172.19.0.1:9000","minio_durable_bucket":"cats-durable","minio_durable_endpoint_host":"http://127.0.0.1:9100","minio_durable_endpoint_pod":"http://172.19.0.1:9100"}
```

Concretely, `InfraFunction` (`infrafunction_subproc`) dispatches `integrated_subproc` (Process `process_0` / `process_1` via **`ComputePort`** — no Ray in Process) onto Plant through **`PlantPort`** (this demo: `RayPlantPort` / Ray Job Submission). `ObjectStore.write_job_scratch` writes scratch MinIO config only; `RayPlantPort.submit_job` stages the Plant-owned entrypoint + **`RayComputePort`**. Demo batch ABI is `Dict[str, np.ndarray]` column batches. Workers land CSV shards under a **`JobHandle`** prefix in scratch MinIO; host-side retrieval uses `ObjectStore.download_job_result`. Durable Entity Relationship (structure namespace + `er/current` pointers) is a separate hard-isolated MinIO on the same `ObjectStore` façade — see [`MinIO.md`](./MinIO.md). `object_store_as_executed_cid` records both stores’ credential-free endpoints.

Neither as-executed CID is re-consumed downstream to drive further behavior — their purpose is the permanent content-addressed record. `flatten_bom()` expands `invoice.structure_as_executed_cid` into `flat_bom['structure_as_executed']`, `flat_bom['plant']`, `flat_bom['infrastructure_as_executed']`, and `flat_bom['object_store_as_executed']` for inspection.

Lineage helpers (all chain Invoice `data_cid` from a prior BOM): `linkProcess()` rebuilds `function_cid` and carries `structure_cid`; `linkStructure()` rebuilds apply-complete `structure_cid` and carries `function_cid`; `linkOrder()` mutates Function and/or Structure in one lineage step (single Invoice chain). Each accepts a prior HTTP `cat_response` **or** `bom_cid=` / `data_cid=` resolved through the Node-local `BomRegistry` (indexed on `Runtime.execute`; see [`BomRegistry.md`](BomRegistry.md) / [`ControlFeedbackLoop.md`](ControlFeedbackLoop.md)).

### Node-local BOM registry

Full contract: **[`BomRegistry.md`](BomRegistry.md)** — append-only query index (`cats/network/registry/`), not the envelope store (`BomLdpStore` / Solid) and not LDN. `Runtime.execute` writes after LDP/Solid locators are known (fail closed). `POST /cat/node/init` accepts `order_cid` (bootstrap), or `bom_cid` / unique `data_cid` / `data_uri` via the index (`GET /ldp/registry/…`). **CAS-over-HTTP** mints new Order/Invoice/stage bytes as `ni:` and registers `GET /ldp/registry/by-content/…` locators; **Phase 2b** dual-field adds HTTP `*_uri` (Order/Invoice LDP). Remaining gaps: mesh federation, Solid dual-write of registry records, hard-drop of `*_cid` names.

### Invoice stage CIDs + Seed

After `Executor.execute()` (`cats/executor/executor.py`), the Invoice records both the data-product stage CIDs (Control-Feedback Loop feedback) and the Process replay dictionary ([#187](https://github.com/DynamicalSystemsGroup/cats/issues/187)):

- `invoice.data_cid` / `invoice.data_uri` — egress / output (equality id + Phase 2b fetch URI)
- `invoice.ingress_data_cid` / `ingress_data_uri` — ingress transport
- `invoice.integration_data_cid` / `integration_data_uri` — Plant integration outputs after the hotF (durable CAS copy of data downloaded from MinIO scratch)
- `invoice.seed_cid` / `seed_uri` — Process replay dictionary, minted fresh each execution: `{'seed': <hex>, 'rng_seed': <31-bit int>, 'num_partitions': <int>}`. `seed` is a `uuid4().hex` identity string (differs per run, e.g. across CAT0/CAT1); `rng_seed` is derived from it (`int(seed[:8], 16) & 0x7FFFFFFF`) and is directly usable by `np.random.default_rng` / Ray Data `seed=`, though no Process step consumes it yet; `num_partitions` mirrors `Processor.num_partitions` (env `CATS_IO_PARTITIONS`-selected today) as observed provenance, not yet as the control-plane source of `n`. `ContentMesh.flatten_bom()` resolves `seed_cid` → `flat_bom.invoice.seed` the same way it resolves `order_cid` → `order`.
- `invoice.structure_as_executed_cid` / `structure_as_executed_uri` — observed Structure pairing (see Nest tree above)
- `invoice.order_cid` / `order_uri` — Order content id + Order LDP URI when published

The BOM `log` mirrors those stage CIDs as `ingress_data_cid` / `integration_data_cid` / `egress_data_cid` (plus `plant_rebuilt`), and records `object_store_result_uri` (`s3://cats-scratch/jobs/<uuid>/result`) as a non-secret correlator for Structure-lifetime scratch MinIO — not a substitute for `integration_data_cid`. Scratch objects expire via ILM (7 days) and are wiped on Structure destroy (`down -v`). Optional `durable_er_uri` / `durable_er_pointer` correlators are set when Entity Relationship promote is used (otherwise `null`); durable MinIO is Node-lifetime and GC’d only via `gc-er`. Access is InfraStructure-as-Code (Consoles / S3 / `infrastructure/obj_store_utils.py` / `ObjectStore` / `JobHandle`); there is no CAT Node jobs API (see [`MinIO.md`](./MinIO.md) / [`STORAGE.md`](./STORAGE.md)). Plant, object-store, and transport config are not Runtime fields — Executor threads `Plant.plant_port()`, `obj_store_context()`, and `as_transport_port(transport_context())` into Function stages. Plant input for the hotF is the host path returned by `integration_cache` under `INTEGRATION_INPUT_DATA_CACHE`, not an Ingress side-channel path.

See also: [Design: How the Architectural Quantum is realized as content-addressed CIDs](DESIGN.md#how-the-architectural-quantum-is-realized-as-content-addressed-cids) and [Lineage of Provenance: How are CATs composed as a Lineage of Data Provenance on a Data Mesh?](LineageOfProvenance.md#how-are-cats-composed-as-a-lineage-of-data-provenance-on-a-data-mesh).
