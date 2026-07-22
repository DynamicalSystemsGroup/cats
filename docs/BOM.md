# What's Inside a BOM's CIDs

Each of the Architectural Quantum's four components (Function, InfraFunction, Structure, InfraStructure) is content-addressed independently, then paired back together as a small JSON object so the Order records both halves under a single CID:

- `order.function_cid` resolves to `{process_cid, infrafunction_cid, process_source_cid, infrafunction_source_cid}` — hybrid Function pairing. `process_cid` / `infrafunction_cid` are bind JSON maps of `*_subproc_cid` → **leaf CID** (still a single string per slot). Process [REPL(aC)] composes (`ingress_subproc_cid`, `integration_cache_subproc_cid`, `integrated_subproc_cid`, `egress_subproc_cid`); only `integrated_subproc_cid` is the Transfer Higher-Order Function (tHOF) — Plant-agnostic `ComputePort.run_transfer` (see [transfer function](https://en.wikipedia.org/wiki/Transfer_function)); ingress / integration_cache / egress are transport **port** callables that require Executor-wired `TransportPort`. `infrafunction_cid` bind JSON holds the actuator (`infrafunction_subproc_cid`). Each leaf CID is either **named-bind JSON** `{"source_cid","module","qualname"}` (stock public callables from `create_order_request` / `linkProcess`) or **pickle bytes** (REPL escape hatch for non-stock callables). `process_source_cid` / `infrafunction_source_cid` are whole-directory CIDs of `function/process/` and `function/infrafunction/`; named binds must pin those package CIDs. `getEnhancedBom()` materializes the source trees; Executor `resolve_subproc` imports named binds or unpickles. Recreate Orders created before source keys existed — `getEnhancedBom()` / `linkProcess()` / Executor fail loud if they are missing. Compose Orders with **named imports** of the Process public surface only (`ingress`, `egress`, `integration_cache`, `function_*`, `process_*` — see `process.__all__`); never `from data.input.function.process import *`.
- `order.structure_cid` resolves to `{root_cid, plant_cid, infrastructure_cid}` — apply-complete Structure pairing. `root_cid` is the directory CID of compose glue only (`main.tf`, `outputs.tf`, `.terraform.lock.hcl` — providers + `module "plant"` / `module "infrastructure"` wiring). `plant_cid` is the CID of the whole `plant/` Terraform directory (kind cluster + Helm releases, `plant_utils.py` / `RayPlantPort`, and Ray landing `ray_job_result_entrypoint.py` + `ray_compute_utils.py` / `RayComputePort` that constitute Plant, SaaS); `infrastructure_cid` is the CID of the whole `infrastructure/` Terraform directory (Docker Kubo transport + `transport_utils.py` / `TransportContext`, MinIO + `obj_store_utils.py` / `JobHandle`, host ContentStore helpers that constitute InfraStructure, IaaS). Recreate Orders created before `root_cid` existed — `getEnhancedBom()` fails loud if it is missing.

Both are built in `create_order_request()` and unpacked back onto disk by `getEnhancedBom()` so the fetched Structure stays directly `terraform apply`-able from the Order alone (root files + `plant/` + `infrastructure/`) and Function source packages land under `function/process/` + `function/infrafunction/`. `root_cid`/`plant_cid`/`infrastructure_cid` and `process_source_cid`/`infrafunction_source_cid` are each whole-directory CIDs (via `cidDir()`) — `ipfs ls`-ing plant/infra lists that Terraform module's actual files (e.g. `main.tf`, `outputs.tf`, `variables.tf`, `plant_utils.py`, `ray_job_result_entrypoint.py`, `ray_compute_utils.py` for `plant_cid`; `main.tf`, `outputs.tf`, `minio_compose.yaml`, `ipfs_transport_compose.yaml`, `transport_utils.py`, `content_store_utils.py`, `obj_store_utils.py` for `infrastructure_cid`); `ipfs ls`-ing a Function source CID lists that package's Python modules. `process_cid`/`infrafunction_cid` remain CIDs of small JSON objects mapping slots to leaf CIDs. A real `function_cid` fetched via `ipfs cat` looks like:

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

The resulting BOM then pairs each of those *specified-as-code* CIDs with an *observed-at-execution-time* snapshot CID, recorded by `Service.execute()` (`cats/service/__init__.py:132-160`) from `enhanced_bom['plant']`/`enhanced_bom['infrastructure']`, which `Executor.execute()` sets right after `Structure.reconcile()` runs (`cats/factory/__init__.py`):

- `bom.plant_snapshot_cid` — what `Plant.snapshot()` / `PlantContext.snapshot()` records after `Structure.reconcile()` ran (via `Plant.context()` and Order-submitted `plant/plant_utils.py`): the live kind cluster name, kubeconfig context, Ray release name, Ray dashboard address (BOM observation; dispatch uses `PlantContext.job_endpoint`), the `structure_cid` currently applied, and whether this reconcile reused the existing Plant or destroyed/rebuilt it (`rebuilt`). Plant-specific kind/TF stale-state repair before apply also lives in `plant_utils.cleanup_stale_plant_state` (not Quantum package constants). Example content:
  ```json
  {"applied_structure_cid":"QmXe7n5auVw94fv3Xu6rZQqQWfGpXZnMq5u6ubKCM6yYK1","kind_cluster_name":"cats","kubeconfig_context":"kind-cats","ray_dashboard_address":"http://127.0.0.1:8265","ray_release_name":"raycluster","rebuilt":false}
  ```
- `bom.infrastructure_snapshot_cid` — what `ObjectStore.snapshot()` returns after `InfraStructure.obj_store_context()`: the shared MinIO bucket and its host- and pod-reachable S3 endpoints (credentials deliberately excluded, so they never get CID'ed into the BOM/Invoice graph). Example content:
  ```json
  {"minio_bucket":"cats-scratch","minio_endpoint_host":"http://127.0.0.1:9000","minio_endpoint_pod":"http://172.19.0.1:9000"}
  ```

Concretely, `InfraFunction` (`infrafunction_subproc`) dispatches `integrated_subproc` (Process `process_0` / `process_1` via **`ComputePort`** — no Ray in Process) onto Plant through **`PlantPort`** (this demo: `RayPlantPort` / Ray Job Submission). `ObjectStore.write_job_scratch` writes MinIO config only; `RayPlantPort.submit_job` stages the Plant-owned entrypoint + **`RayComputePort`** (another Plant would stage its own landing under its `plant_cid`). Demo batch ABI is `Dict[str, np.ndarray]` column batches — the ComputePort adapter maps engine batches onto that shape. Workers land CSV shards under a **`JobHandle`** prefix in MinIO; `result_uri` / `download_job_result` are JobHandle-only. Host-side retrieval uses `ObjectStore.download_job_result`. `bom.infrastructure_snapshot_cid` records which shared store that write landed in.

Neither snapshot CID is re-consumed downstream to drive further behavior — their purpose is purely to make the executed Plant/InfraStructure state part of the CAT's permanent, content-addressed record. `flatten_bom()` currently only fetches `plant_snapshot_cid` back out into `flat_bom['plant']` for human-readable inspection; `infrastructure_snapshot_cid` isn't flattened the same way yet, so it's only reachable by `ipfs cat`-ing it directly out of the raw `bom` dict.

Lineage helpers (all chain Invoice `data_cid` from a prior BOM response): `linkProcess()` rebuilds `function_cid` and carries `structure_cid`; `linkStructure()` rebuilds apply-complete `structure_cid` and carries `function_cid`; `linkOrder()` mutates Function and/or Structure in one lineage step (single Invoice chain).

### Invoice stage CIDs (interim feedback; Seed deferred)

After `Executor.execute()` (`cats/factory/__init__.py`), the Invoice records stage products for Control-Feedback Loop feedback until Seed is implemented ([#187](https://github.com/DynamicalSystemsGroup/cats/issues/187)):

- `invoice.data_cid` — egress / output data CID (existing)
- `invoice.ingress_data_cid` — CID produced by ingress transport
- `invoice.integration_data_cid` — CID of Plant integration outputs after the tHOF runs (durable IPFS copy of data downloaded from MinIO scratch)
- `invoice.seed_cid` — still `null` until Seed is populated

The BOM `log` mirrors those stage CIDs as `ingress_data_cid` / `integration_data_cid` / `egress_data_cid` (plus `plant_rebuilt`), and records `object_store_result_uri` (`s3://cats-scratch/jobs/<uuid>/result`) as a non-secret correlator for Structure-lifetime MinIO scratch — not a substitute for `integration_data_cid`. MinIO objects are retained until Structure destroy. Scratch access is InfraStructure-as-Code (Console / S3 / `infrastructure/obj_store_utils.py` / `ObjectStore` / `JobHandle`); there is no CAT Node jobs API (see [`MinIO.md`](./MinIO.md) / [`STORAGE.md`](./STORAGE.md)). Plant, object-store, and transport config are not Service fields — Executor threads `Plant.plant_port()`, `obj_store_context()`, and `as_transport_port(transport_context())` into Function stages. Plant input for the tHOF is the host path returned by `integration_cache` under `INTEGRATION_INPUT_DATA_CACHE`, not an Ingress side-channel path.

See also: [Design: How the Architectural Quantum is realized as content-addressed CIDs](DESIGN.md#how-the-architectural-quantum-is-realized-as-content-addressed-cids) and [Lineage of Provenance: How are CATs composed as a Lineage of Data Provenance on a Data Mesh?](LineageOfProvenance.md#how-are-cats-composed-as-a-lineage-of-data-provenance-on-a-data-mesh).
