# What's Inside a BOM's CIDs

Each of the Architectural Quantum's four components (Function, InfraFunction, Structure, InfraStructure) is content-addressed independently, then paired back together as a small JSON object so the Order records both halves under a single CID:

- `order.function_cid` resolves to `{process_cid, infrafunction_cid}` — `process_cid` is Process [REPL(aC)]: a Read-Eval-Print Loop as Code that composes and submits callables as (`ingress_subproc_cid`, `integration_cache_subproc_cid`, `integrated_subproc_cid`, `egress_subproc_cid`). Of those, only `integrated_subproc_cid` is the Transfer Higher-Order Function (tHOF) — Plant-agnostic `ComputePort.run_transfer` (see [transfer function](https://en.wikipedia.org/wiki/Transfer_function)); ingress / integration_cache / egress are transport **port** callables that require Executor-wired `TransportPort`. `infrafunction_cid` is InfraFunction (FaaS): the actuator (`infrafunction_subproc_cid`) that dispatches that tHOF onto Plant via **`PlantPort`** and scratch via **`JobHandle`**. Source packages live under `data/input/function/process/` (callables + `TransportPort` / `ComputePort`) and `data/input/function/infrafunction/` (actuator + `PlantPort`); unlike Structure, `process_cid` / `infrafunction_cid` remain JSON of pickled `*_subproc_cid`s, not directory CIDs. Recreate Orders after Process/InfraFunction signature or module-path changes (old pickled tHOFs without `compute`, or pickled against prior flat module paths, will fail). Compose Orders with **named imports** of the Process public surface only (`ingress`, `egress`, `integration_cache`, `function_*`, `process_*` — see `process.__all__`); never `from data.input.function.process import *`.
- `order.structure_cid` resolves to `{plant_cid, infrastructure_cid}` — `plant_cid` is the CID of the whole `plant/` Terraform directory (kind cluster + Helm releases that constitute Plant, SaaS); `infrastructure_cid` is the CID of the whole `infrastructure/` Terraform directory (Docker Kubo transport + `transport_utils.py` / `TransportContext`, MinIO + `obj_store_utils.py`, host ContentStore helpers, and `ray_job_result_entrypoint.py` that constitute InfraStructure, IaaS).

Both are built in `create_order_request()` (`cats/network/__init__.py:193-248`) and unpacked back into modules on disk by `getEnhancedBom()` (`cats/network/__init__.py:379-410`) so the fetched Structure stays directly `terraform apply`-able. `plant_cid`/`infrastructure_cid` are each a whole-directory CID (added recursively via `cidDir()`, `cats/network/__init__.py:172-185`) — `ipfs ls`-ing one lists that Terraform module's actual files (e.g. `main.tf`, `outputs.tf`, `variables.tf` for `plant_cid`; `main.tf`, `outputs.tf`, `minio_compose.yaml`, `ipfs_transport_compose.yaml`, `transport_utils.py`, `content_store_utils.py`, `obj_store_utils.py`, `ray_job_result_entrypoint.py` for `infrastructure_cid`) — whereas `process_cid`/`infrafunction_cid` are each a CID of a small JSON object of `*_subproc_cid`s, not a directory. A real `structure_cid` fetched via `ipfs cat` looks like:

```json
{
  "plant_cid": "QmaxYkAmJogHAmHMgYLLuxETjeUxQMqu1NkowmM12EEqMM",
  "infrastructure_cid": "Qmf1SZni9CyMhTQCCCp2qVYxwGSPGojdPS7DDGgTR1xwkt"
}
```

The sibling `order.structure_filepath` field just records the directory name (e.g. `structure`) so `getEnhancedBom()` knows where to materialize each fetched module locally (`structure_filepath/plant`, `structure_filepath/infrastructure`); `flatten_bom()` (`cats/network/__init__.py:250-271`) surfaces the parsed `{plant_cid, infrastructure_cid}` object under `invoice.order.flat.structure` for inspection.

The resulting BOM then pairs each of those *specified-as-code* CIDs with an *observed-at-execution-time* snapshot CID, recorded by `Service.execute()` (`cats/service/__init__.py:132-160`) from `enhanced_bom['plant']`/`enhanced_bom['infrastructure']`, which `Executor.execute()` sets right after `Structure.reconcile()` runs (`cats/factory/__init__.py`):

- `bom.plant_snapshot_cid` — what `Plant.snapshot()` / `PlantContext.snapshot()` records after `Structure.reconcile()` ran (via `Plant.context()` and Order-submitted `plant/plant_utils.py`): the live kind cluster name, kubeconfig context, Ray release name, Ray dashboard address (BOM observation; dispatch uses `PlantContext.job_endpoint`), the `structure_cid` currently applied, and whether this reconcile reused the existing Plant or destroyed/rebuilt it (`rebuilt`). Plant-specific kind/TF stale-state repair before apply also lives in `plant_utils.cleanup_stale_plant_state` (not Quantum package constants). Example content:
  ```json
  {"applied_structure_cid":"QmXe7n5auVw94fv3Xu6rZQqQWfGpXZnMq5u6ubKCM6yYK1","kind_cluster_name":"cats","kubeconfig_context":"kind-cats","ray_dashboard_address":"http://127.0.0.1:8265","ray_release_name":"raycluster","rebuilt":false}
  ```
- `bom.infrastructure_snapshot_cid` — what `ObjectStore.snapshot()` returns after `InfraStructure.obj_store_context()`: the shared MinIO bucket and its host- and pod-reachable S3 endpoints (credentials deliberately excluded, so they never get CID'ed into the BOM/Invoice graph). Example content:
  ```json
  {"minio_bucket":"cats-scratch","minio_endpoint_host":"http://127.0.0.1:9000","minio_endpoint_pod":"http://172.19.0.1:9000"}
  ```

Concretely, `InfraFunction` (`infrafunction_subproc`) dispatches `integrated_subproc` (Process `process_0` / `process_1` via **`ComputePort`** — no Ray in Process) onto Plant through **`PlantPort`** (this demo: `RayPlantPort` / Ray Job Submission). The job entrypoint wires **`RayComputePort`**, then `ObjectStore.write_job_scratch` lands CSV shards under a **`JobHandle`** prefix in MinIO. Host-side retrieval uses `ObjectStore.download_job_result`. `bom.infrastructure_snapshot_cid` records which shared store that write landed in.

Neither snapshot CID is re-consumed downstream to drive further behavior — their purpose is purely to make the executed Plant/InfraStructure state part of the CAT's permanent, content-addressed record. `flatten_bom()` currently only fetches `plant_snapshot_cid` back out into `flat_bom['plant']` for human-readable inspection; `infrastructure_snapshot_cid` isn't flattened the same way yet, so it's only reachable by `ipfs cat`-ing it directly out of the raw `bom` dict.

### Invoice stage CIDs (interim feedback; Seed deferred)

After `Executor.execute()` (`cats/factory/__init__.py`), the Invoice records stage products for Control-Feedback Loop feedback until Seed is implemented ([#187](https://github.com/DynamicalSystemsGroup/cats/issues/187)):

- `invoice.data_cid` — egress / output data CID (existing)
- `invoice.ingress_data_cid` — CID produced by ingress transport
- `invoice.integration_data_cid` — CID of Plant integration outputs after the tHOF runs (durable IPFS copy of data downloaded from MinIO scratch)
- `invoice.seed_cid` — still `null` until Seed is populated

The BOM `log` mirrors those stage CIDs as `ingress_data_cid` / `integration_data_cid` / `egress_data_cid` (plus `plant_rebuilt`), and records `object_store_result_uri` (`s3://cats-scratch/jobs/<uuid>/result`) as a non-secret correlator for Structure-lifetime MinIO scratch — not a substitute for `integration_data_cid`. MinIO objects are retained until Structure destroy. Scratch access is InfraStructure-as-Code (Console / S3 / `infrastructure/obj_store_utils.py` / `ObjectStore` / `JobHandle`); there is no CAT Node jobs API (see [`MinIO.md`](./MinIO.md) / [`STORAGE.md`](./STORAGE.md)). Plant, object-store, and transport config are not Service fields — Executor threads `Plant.plant_port()`, `obj_store_context()`, and `as_transport_port(transport_context())` into Function stages. Plant input for the tHOF is the host path returned by `integration_cache` under `INTEGRATION_INPUT_DATA_CACHE`, not an Ingress side-channel path.

See also: [Design: How the Architectural Quantum is realized as content-addressed CIDs](DESIGN.md#how-the-architectural-quantum-is-realized-as-content-addressed-cids) and [Lineage of Provenance: How are CATs composed as a Lineage of Data Provenance on a Data Mesh?](LineageOfProvenance.md#how-are-cats-composed-as-a-lineage-of-data-provenance-on-a-data-mesh).
