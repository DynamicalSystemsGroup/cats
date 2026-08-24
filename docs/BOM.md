# What's Inside a BOM's Content Ids

**Addressing note (§6d–§6s):** **new** Order / Invoice / Function / Structure / stage / BOM JSON carries HTTP **`*_uri`** only (no `*_cid` keys). Equality stays **`ni:`** (envelope `contentId` / registry hash keys / URI path hex). Control-plane **Python** uses `*_id` / `content_id` and `put_dir` / `put_file` (no `cidDir` / `cidFile` aliases). Mesh / AddressStore reads take **`content_id=`** (`ni:` / `hl:` / HTTP; legacy CID fail closed §6s). Named-bind leaves use `contentId` + optional `source_uri`. Structure reconcile marker on disk is **`.applied-structure.id`** (legacy `.applied-structure.cid` readable one cycle); plant as-executed uses **`applied_structure_id`**. Order-submitted Process/Plant/Ray ABI under `data/input/` uses **`input_dir_id`**, Ray job **`input_id` / `layout_id`**, and obj_store **`structure_id`** (ER pointer write `structure_id`; read also accepts legacy `structure_cid`). Readers still accept legacy graph `*_cid` via `ref_id`. Fetch via AddressStore / `GET /ldp/cas/<hex>` / `GET /ldp/invoices|orders/…` (or mesh `cat` / `get`).

Each of the Architectural Quantum's four components (Function, InfraFunction, Structure, InfraStructure) is content-addressed independently, then paired back together as a small JSON object so the Order records both halves under a single content id:

- `order.function_uri` resolves to `{process_uri, infrafunction_uri, process_source_uri, infrafunction_source_uri}` — hybrid Function pairing. `process_uri` / `infrafunction_uri` are bind JSON maps of `*_subproc_uri` → **leaf content id**. Process [Composed Function] holds (`ingress_subproc_uri`, `integration_cache_subproc_uri`, `integrated_subproc_uri`, `egress_subproc_uri`); only `integrated_subproc_uri` is the Higher-Order Transfer Function (hotF). Each leaf is either **named-bind JSON** `{"contentId","source_uri?","module","qualname"}` (stock callables) or **pickle bytes**. `process_source_uri` / `infrafunction_source_uri` are whole-directory content ids of `function/process/` and `function/infrafunction/`. `getEnhancedBom()` materializes the source trees; Executor `resolve_subproc` imports named binds or unpickles (legacy `*_cid` graphs still read via `ref_id`).
- `order.structure_uri` resolves to `{root_uri, plant_uri, infrastructure_uri}` — apply-complete Structure pairing (compose glue / plant / infrastructure directory content ids). Recreate Orders created before `root` existed — `getEnhancedBom()` fails loud if it is missing.

Both are built in `create_order_request()` and unpacked back onto disk by `getEnhancedBom()` so the fetched Structure stays directly `terraform apply`-able from the Order alone (root files + `plant/` + `infrastructure/`) and Function source packages land under `function/process/` + `function/infrafunction/`. Directory content ids (`root` / `plant` / `infrastructure` / Function source trees) are CAS `ni:` digests via `put_dir()` (directory manifests). Function pairing maps remain small JSON objects mapping slots to leaf content ids. A real `function` payload fetched via CAS looks like:

```json
{
  "process_uri": "http://…/ldp/cas/<hex>",
  "infrafunction_uri": "http://…/ldp/cas/<hex>",
  "process_source_uri": "http://…/ldp/cas/<hex>",
  "infrafunction_source_uri": "http://…/ldp/cas/<hex>"
}
```

A stock named-bind leaf (`ipfs cat` of e.g. `integrated_subproc_cid`) looks like:

```json
{
  "contentId": "ni:///sha-256;…",
  "source_uri": "http://…/ldp/cas/<hex>",
  "module": "data.input.function.process.callables",
  "qualname": "process_0"
}
```

A real `structure_cid` fetched via `ipfs cat` looks like:

```json
{
  "root_uri": "http://…/ldp/cas/<hex>",
  "plant_uri": "http://…/ldp/cas/<hex>",
  "infrastructure_uri": "http://…/ldp/cas/<hex>"
}
```

The sibling `order.structure_filepath` field just records the directory name (e.g. `structure`) so `getEnhancedBom()` knows where to materialize root glue and each fetched module locally (`structure_filepath/` for root files, `structure_filepath/plant`, `structure_filepath/infrastructure`); `flatten_bom()` surfaces the parsed `{root_cid, plant_cid, infrastructure_cid}` object under `invoice.order.flat.structure` for inspection.

### CAT Node HTTP BOM response

`Runtime.execute()` returns `{ content_id, bom, bom_ldp_uri, bom_solid_uri, hl, … }` (**no** `bom_cid`). When the BOM id is a digest and a locator exists, **`hl`** is `to_hl(content_id, bom_solid_uri or bom_ldp_uri)`. Loopback `CAT_NODE_HOST` only **warns** (Solid URI preferred for mesh-reachable hints). The HTTP envelope's `bom` is a **JSON-LD + PROV-O** package (`build_execution_bom`) holding address refs only: `invoice_uri`, `log_uri`, `node_did`, plus `@context` / `@type` / `prov:wasAttributedTo` / `prov:wasGeneratedBy` (`#executorRun`), and **`stageLineage`** (`prov:Entity` nodes with `prov:wasDerivedFrom` along Invoice stage content ids), then **signed** with a W3C Data Integrity proof (`sign_execution_bom`, cryptosuite `eddsa-jcs-2022`). Observed Plant / InfraStructure state is nested under the Invoice as `structure_as_executed_uri` — parallel to as-Code `order.structure_uri`, but different bytes (observation, not IaC). Executor mints that nest bottom-up **before** the Invoice content id. `infrastructure_as_executed` currently carries only `object_store_as_executed_uri` (`InfraStructure.snapshot`). `content_id` is response-only (never written into the signed `bom` object) and is the digest of the **signed** BOM. `bom_ldp_uri` is the Phase 2a Node LDP cache locator (`http://{CAT_NODE_HOST}:{CAT_NODE_PORT}/ldp/boms/{hex}`) — also persisted under `{CATS_HOME}/.cats/ldp/boms/` for `GET`. When Solid is configured (`SOLID_POD_BASE_URL`), `bom_solid_uri` is the dual-published pod locator; peers may `fetch_bom_envelope` on either URI, verify the proof, and resolve refs via AddressStore. See [`SOLID.md`](SOLID.md). HTTP Flask bind is Node lifecycle — **not** BOM attribution; attribution is `node_did` (`did:key:…` from `{CATS_HOME}/.cats/node_did.json`, or `CAT_NODE_DID` when it matches that keyfile).

```text
HTTP JSON response  (Runtime.execute → jsonify)
├── content_id    →  content-address of the `bom` object below (ni:/digest)
├── bom_ldp_uri   →  Node LDP GET locator (local cache)
├── bom_solid_uri →  Solid pod URI when configured (else null)
│
└── bom  →  signed JSON-LD / PROV-O ExecutionBom (Data Integrity)
    │
    ├── @context / @type  (includes data-integrity/v2)
    ├── invoice_uri  →  output Invoice JSON
    │   │   Minted by Executor after as-executed refs are written.
    │   │
    │   ├── order_uri  →  Order JSON  (as-Code Quantum input)
    │   │   ├── invoice_uri          input Invoice
    │   │   ├── function_uri
    │   │   │   ├── process_uri / infrafunction_uri
    │   │   │   └── process_source_uri / infrafunction_source_uri
    │   │   └── structure_uri        as-Code Structure pairing
    │   │       ├── root_uri
    │   │       ├── plant_uri
    │   │       └── infrastructure_uri
    │   │
    │   ├── data_uri                 # egress bytes (link*/registry equality)
    │   ├── data_stages_uri  →  stage nest JSON
    │   │       ├── egressed_data_uri    # same content as data_uri
    │   │       ├── integrated_data_uri
    │   │       └── ingressed_data_uri
    │   ├── seed_uri  →  Seed JSON  (#187)
    │   │       {seed, rng_seed, num_partitions} — replay dictionary
    │   │
    │   └── structure_as_executed_uri  →  observed Structure pairing JSON
    │       ├── plant_as_executed_uri  →  Plant.snapshot() dict
    │       │       kind/Ray/applied_structure_id/rebuilt, …
    │       └── infrastructure_as_executed_uri  →  InfraStructure.snapshot() dict
    │           └── object_store_as_executed_uri  →  ObjectStore.snapshot() dict
    │                   minio endpoints/bucket (no secrets)
    │                   # later: transport_*, content_store_*, …
    │
    ├── log_uri  →  log JSON
    │       stage ref mirrors, plant_rebuilt, object_store_result_uri,
    │       durable_er_uri / durable_er_pointer (optional)
    │
    ├── node_did  (DID string, not a content id; not the Flask HTTP URL)
    │       did:key:…  (keyfile; CAT_NODE_DID only if it matches)
    ├── prov:wasAttributedTo  →  { @id: node_did }
    ├── prov:wasGeneratedBy   →  #executorRun Activity
    │       prov:used → Order / Invoice entities (@id URI + contentId)
    ├── stageLineage  →  [ prov:Entity … ]  (URI @id + contentId)
    │       wasGeneratedBy #executorRun;
    │       wasDerivedFrom along data←integration←ingress←input
    │       structure_as_executed: generated-by only (observation)
    └── proof  →  DataIntegrityProof (eddsa-jcs-2022)
            type, cryptosuite, created, verificationMethod,
            proofPurpose, proofValue (multibase z…)
```

Example `plant_as_executed` content (`Plant.snapshot()` after `Structure.reconcile()`):

```json
{"applied_structure_id":"QmXe7n5auVw94fv3Xu6rZQqQWfGpXZnMq5u6ubKCM6yYK1","kind_cluster_name":"cats","kubeconfig_context":"kind-cats","ray_dashboard_address":"http://127.0.0.1:8265","ray_release_name":"raycluster","rebuilt":false}
```

Example `object_store_as_executed` content (`ObjectStore.snapshot()` after `InfraStructure.obj_store_context()` — credentials excluded; scratch + durable Entity Relationship):

```json
{"minio_scratch_bucket":"cats-scratch","minio_scratch_endpoint_host":"http://127.0.0.1:9000","minio_scratch_endpoint_pod":"http://172.19.0.1:9000","minio_durable_bucket":"cats-durable","minio_durable_endpoint_host":"http://127.0.0.1:9100","minio_durable_endpoint_pod":"http://172.19.0.1:9100"}
```

Concretely, `InfraFunction` (`infrafunction_subproc`) dispatches `integrated_subproc` (Process `process_0` / `process_1` via **`ComputePort`** — no Ray in Process) onto Plant through **`PlantPort`** (this demo: `RayPlantPort` / Ray Job Submission). `ObjectStore.write_job_scratch` writes scratch MinIO config only; `RayPlantPort.submit_job` stages the Plant-owned entrypoint + **`RayComputePort`**. Demo batch ABI is `Dict[str, np.ndarray]` column batches. Workers land CSV shards under a **`JobHandle`** prefix in scratch MinIO; host-side retrieval uses `ObjectStore.download_job_result`. Durable Entity Relationship (structure namespace + `er/current` pointers) is a separate hard-isolated MinIO on the same `ObjectStore` façade — see [`MinIO.md`](./MinIO.md). `object_store_as_executed_cid` records both stores’ credential-free endpoints.

Neither as-executed content id is re-consumed downstream to drive further behavior — their purpose is the permanent content-addressed record. `flatten_bom()` expands `invoice.structure_as_executed_uri` (or legacy `*_cid`) into `flat_bom['structure_as_executed']`, `flat_bom['plant']`, `flat_bom['infrastructure_as_executed']`, and `flat_bom['object_store_as_executed']` for inspection, and expands `invoice.data_stages_uri` into `flat_bom['data_stages']` / `flat_bom.invoice['data_stages']`.

Lineage helpers (all chain Invoice `data` equality from a prior BOM): `linkProcess()` rebuilds Function and carries Structure; `linkStructure()` rebuilds apply-complete Structure and carries Function; `linkOrder()` mutates Function and/or Structure in one lineage step (single Invoice chain). Each accepts a prior HTTP `cat_response` **or** `content_id=` / `data_uri=` / `bom_uri=` resolved through the Node-local `BomRegistry` (indexed on `Runtime.execute`; see [`BomRegistry.md`](BomRegistry.md) / [`ControlFeedbackLoop.md`](ControlFeedbackLoop.md)). Legacy `bom_cid=` / `data_cid=` kwargs are rejected.

### Node-local BOM registry

Full contract: **[`BomRegistry.md`](BomRegistry.md)** — append-only query index (`cats/network/registry/`), not the envelope store (`BomLdpStore` / Solid) and not LDN. `Runtime.execute` writes after LDP/Solid locators are known (fail closed). `POST /cat/node/init` accepts `order_uri`, `bom_ldp_uri` / `bom_solid_uri`, unique `content_id` / `data_uri` / `hl`, or `hl:` as a URI value via the index (`GET /ldp/registry/…`). Legacy `order_cid` / `bom_cid` / `data_cid` body keys → **400**. **CAS-over-HTTP** mints new Order/Invoice/stage bytes as `ni:` and registers `GET /ldp/registry/by-content/…` locators; **§6d** new mints are URI-only (`*_uri` + envelope `contentId`); **§6f** emits response/LDN `hl:` and resolves `hl:` on intake / AddressStore. Remaining gaps: mesh federation, Solid dual-write of registry records.

### Invoice stage refs + Seed

After `Executor.execute()` (`cats/executor/executor.py`), the Invoice records both the data-product stage refs (Control-Feedback Loop feedback) and the Process replay dictionary ([#187](https://github.com/DynamicalSystemsGroup/cats/issues/187)):

- `invoice.data_uri` — egress / output (fetch; equality via URI path / `ni:`; CAT N+1 `link*` / registry by-data)
- `invoice.data_stages_uri` — nest `{egressed_data_uri, integrated_data_uri, ingressed_data_uri}` (Executor-minted; no flat `ingress_data_uri` / `integration_data_uri` on new Invoices)
- `invoice.seed_uri` — Process replay dictionary, minted fresh each execution: `{'seed': <hex>, 'rng_seed': <31-bit int>, 'num_partitions': <int>}`. `seed` is a `uuid4().hex` identity string (differs per run, e.g. across CAT0/CAT1); `rng_seed` is derived from it (`int(seed[:8], 16) & 0x7FFFFFFF`) and is directly usable by `np.random.default_rng` / Ray Data `seed=`, though no Process step consumes it yet; `num_partitions` mirrors `Processor.num_partitions` (env `CATS_IO_PARTITIONS`-selected today) as observed provenance, not yet as the control-plane source of `n`. `ContentMesh.flatten_bom()` resolves `seed_uri` → `flat_bom.invoice.seed` the same way it resolves `order_uri` → `order`.
- `invoice.structure_as_executed_uri` — observed Structure pairing (see Nest tree above)
- `invoice.order_uri` — Order LDP URI when published

The BOM `log` mirrors those stage refs as `ingress_data_uri` / `integration_data_uri` / `egress_data_uri` (plus `plant_rebuilt`), and records `object_store_result_uri` (`s3://cats-scratch/jobs/<uuid>/result`) as a non-secret correlator for Structure-lifetime scratch MinIO — not a substitute for integration data equality. Scratch objects expire via ILM (7 days) and are wiped on Structure destroy (`down -v`). Optional `durable_er_uri` / `durable_er_pointer` correlators are set when Entity Relationship promote is used (otherwise `null`); durable MinIO is Node-lifetime and GC’d only via `gc-er`. Access is InfraStructure-as-Code (Consoles / S3 / `infrastructure/obj_store_utils.py` / `ObjectStore` / `JobHandle`); there is no CAT Node jobs API (see [`MinIO.md`](./MinIO.md) / [`STORAGE.md`](./STORAGE.md)). Plant, object-store, and transport config are not Runtime fields — Executor threads `Plant.plant_port()`, `obj_store_context()`, and `as_transport_port(transport_context())` into Function stages. Plant input for the hotF is the host path returned by `integration_cache` under `INTEGRATION_INPUT_DATA_CACHE`, not an Ingress side-channel path.

See also: [Design: How the Architectural Quantum is realized as content-addressed CIDs](DESIGN.md#how-the-architectural-quantum-is-realized-as-content-addressed-cids) and [Lineage of Provenance: How are CATs composed as a Lineage of Data Provenance on a Data Mesh?](LineageOfProvenance.md#how-are-cats-composed-as-a-lineage-of-data-provenance-on-a-data-mesh).
