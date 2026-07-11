# What's Inside a BOM's CIDs

Each of the Architectural Quantum's four components (Function, InfraFunction, Structure, InfraStructure) is content-addressed independently, then paired back together as a small JSON object so the Order records both halves under a single CID:

- `order.function_cid` resolves to `{process_cid, infrafunction_cid}` — `process_cid` is Process (FaaS): the Functional Data Processors themselves (`ingress_subproc_cid`, `integrated_subproc_cid`, `egress_subproc_cid`, `integration_cache_subproc_cid`); `infrafunction_cid` is InfraFunction (FaaS): the orchestrator that dispatches Process onto the Plant (`infrafunction_subproc_cid`).
- `order.structure_cid` resolves to `{plant_cid, infrastructure_cid}` — `plant_cid` is the CID of the whole `modules/plant` Terraform directory (kind cluster + Helm releases that constitute Plant, SaaS); `infrastructure_cid` is the CID of the whole `modules/infrastructure` Terraform directory (the IPFS/Docker transport layer and MinIO deployment that constitute InfraStructure, IaaS).

Both are built in `create_order_request()` (`cats/network/__init__.py:193-248`) and unpacked back into modules on disk by `getEnhancedBom()` (`cats/network/__init__.py:379-410`) so the fetched Structure stays directly `terraform apply`-able. `plant_cid`/`infrastructure_cid` are each a whole-directory CID (added recursively via `cidDir()`, `cats/network/__init__.py:172-185`) — `ipfs ls`-ing one lists that Terraform module's actual files (e.g. `main.tf`, `outputs.tf`, `variables.tf` for `plant_cid`; `main.tf`, `outputs.tf`, `minio_compose.yaml`, `ipfs_transport_compose.yaml`, `ipfs_connect_peers.sh` for `infrastructure_cid`) — whereas `process_cid`/`infrafunction_cid` are each a CID of a small JSON object of `*_subproc_cid`s, not a directory. A real `structure_cid` fetched via `ipfs cat` looks like:

```json
{
  "plant_cid": "QmaxYkAmJogHAmHMgYLLuxETjeUxQMqu1NkowmM12EEqMM",
  "infrastructure_cid": "Qmf1SZni9CyMhTQCCCp2qVYxwGSPGojdPS7DDGgTR1xwkt"
}
```

The sibling `order.structure_filepath` field just records the directory name (e.g. `structure`) so `getEnhancedBom()` knows where to materialize each fetched module locally (`structure_filepath/modules/plant`, `structure_filepath/modules/infrastructure`); `flatten_bom()` (`cats/network/__init__.py:250-271`) surfaces the parsed `{plant_cid, infrastructure_cid}` object under `invoice.order.flat.structure` for inspection.

The resulting BOM then pairs each of those *specified-as-code* CIDs with an *observed-at-execution-time* snapshot CID, recorded by `Service.execute()` (`cats/service/__init__.py:132-160`) from `enhanced_bom['plant']`/`enhanced_bom['infrastructure']`, which `Executor.execute()` sets right after `Structure.reconcile()` runs (`cats/factory/__init__.py`):

- `bom.plant_snapshot_cid` — what `Plant.snapshot()` actually found after `Structure.reconcile()` ran: the live kind cluster name, kubeconfig context, Ray release name, the Ray dashboard address InfraFunction dispatches jobs to, the `structure_cid` currently applied, and whether this reconcile reused the existing Plant or destroyed/rebuilt it (`rebuilt`) (`cats/executor/structure/__init__.py:324-335`). Example content:
  ```json
  {"applied_structure_cid":"QmXe7n5auVw94fv3Xu6rZQqQWfGpXZnMq5u6ubKCM6yYK1","kind_cluster_name":"cats","kubeconfig_context":"kind-cats","ray_dashboard_address":"http://127.0.0.1:8265","ray_release_name":"raycluster","rebuilt":false}
  ```
- `bom.infrastructure_snapshot_cid` — what `InfraStructure.minio_snapshot()` actually found: the shared MinIO bucket and its host- and pod-reachable S3 endpoints (credentials deliberately excluded, so they never get CID'ed into the BOM/Invoice graph). Example content:
  ```json
  {"minio_bucket":"cats-scratch","minio_endpoint_host":"http://127.0.0.1:9000","minio_endpoint_pod":"http://172.19.0.1:9000"}
  ```

Concretely, `InfraFunction` (`data/input/function/infrafunction.py`'s `infrafunction_subproc`, the actuator) dispatches `integrated_subproc` (Process's `_run_ray_batches`, a pure transfer function in `data/input/function/process.py` with no knowledge of MinIO) as a real Ray Job via the Ray Job Submission API onto the Plant's live Ray cluster rather than running it in-process; the job's entrypoint script (`infrafunction.py`'s `_INFRAFUNCTION_ENTRYPOINT_SCRIPT`) then delivers the returned Dataset by writing its output blocks directly to the shared MinIO bucket from whichever node executes each write task — genuinely distributed, rather than gathering the whole result set onto one node first. `bom.infrastructure_snapshot_cid` is what lets a downstream verifier confirm which shared store that distributed write actually landed in.

Neither snapshot CID is re-consumed downstream to drive further behavior — their purpose is purely to make the executed Plant/InfraStructure state part of the CAT's permanent, content-addressed record. `flatten_bom()` currently only fetches `plant_snapshot_cid` back out into `flat_bom['plant']` for human-readable inspection; `infrastructure_snapshot_cid` isn't flattened the same way yet, so it's only reachable by `ipfs cat`-ing it directly out of the raw `bom` dict.

See also: [Design: How the Architectural Quantum is realized as content-addressed CIDs](DESIGN.md#how-the-architectural-quantum-is-realized-as-content-addressed-cids) and [Lineage of Provenance: How are CATs composed as a Lineage of Data Provenance on a Data Mesh?](LineageOfProvenance.md#how-are-cats-composed-as-a-lineage-of-data-provenance-on-a-data-mesh).
