# Dashboards

Once a CAT Node's Structure is deployed — Terraform runs from `Structure.reconcile()` /
`deploy()` / `redeploy()` during CAT execution (`cats/node.py` hosts the HTTP API; see
[Demo](./DEMO.md) / [Test](./TEST.md)) — these UIs stay at fixed `localhost` addresses for
the Structure's lifetime.

### [Ray Dashboard](http://127.0.0.1:8265)

- **URL:** http://127.0.0.1:8265
- Plant [SaaS] (`module.plant`) KubeRay UI — jobs, actors, resources, logs for Ray Jobs that
  InfraFunction dispatches (`Processor.Integration()` → Job Submission API).
- Live address is `Plant.snapshot()['ray_dashboard_address']`, threaded into
  `Function.execute(…, dashboard_address=…)`. It is **not** a Service field.
- Static NodePort `30265` → host `8265` via kind `extraPortMappings`
  (`data/input/structure/modules/plant/main.tf`).

### [MinIO Console](http://127.0.0.1:9001)

- **URL:** http://127.0.0.1:9001 (S3 API: http://127.0.0.1:9000)
- **Credentials:** `cats-minio` / `cats-minio-secret`
  (`local.minio_root_user` / `local.minio_root_password` in
  `data/input/structure/modules/infrastructure/main.tf`) — change these before deploying a
  Structure whose console would be reachable by anyone else.
- Console for InfraStructure [IaaS] shared object store / scratch (`cats-scratch`) used for
  Plant parallel Ray writes (`jobs/<uuid>/result`). Named volume `structure_minio_data` retains
  objects for the Structure's lifetime; durable integration outputs are IPFS
  (`invoice.integration_data_cid`), not MinIO. Compose:
  `data/input/structure/modules/infrastructure/minio_compose.yaml`.
- Runtime config is `ObjectStore` from `InfraStructure.obj_store_context()` (Order-submitted
  `modules/infrastructure/obj_store_utils.py`) — **not** Service fields. BOM `log` may record
  `object_store_result_uri` for Structure-lifetime correlation; credential-free endpoints land in
  `bom.infrastructure_snapshot_cid` via `ObjectStore.snapshot()` (see [`BOM.md`](./BOM.md)).
- There is **no CAT Node HTTP API** for scratch — use this Console, the S3 API, or:

  ```bash
  uv run python data/input/structure/modules/infrastructure/obj_store_utils.py list-jobs
  ```

  Details: [`MinIO.md`](./MinIO.md), roles: [`STORAGE.md`](./STORAGE.md).

### [IPFS WebUI](http://127.0.0.1:5001/webui)

- **URL:** http://127.0.0.1:5001/webui
- Host Kubo daemon UI — pinned content, peers, repo stats for BOM / Invoice / Order CIDs.
  Python talks to the same daemon via `cats/network/ipfs_client.py` (Kubo HTTP RPC). See
  [`IPFS.md`](./IPFS.md) for how/when the daemon starts.
- Gateway: `http://127.0.0.1:8080/ipfs/<cid>` for raw CID bytes without the WebUI.
