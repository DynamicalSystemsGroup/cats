# Dashboards

Once a CAT Node's Structure is deployed — Terraform runs from `Structure.reconcile()` /
`deploy()` / `redeploy()` during CAT execution (`cats.node` hosts the HTTP API; see
[Demo](./DEMO.md) / [Test](./TEST.md)) — these UIs stay at fixed `localhost` addresses for
the Structure's lifetime.

### [Ray Dashboard](http://127.0.0.1:8265)

- **URL:** http://127.0.0.1:8265
- Plant [SaaS] (`module.plant`) KubeRay UI — jobs, actors, resources, logs for Ray Jobs that
  InfraFunction dispatches (`Processor.Integration()` — runtime of Process [Composed Function] → Job Submission API).
- Live address is `Plant.snapshot()['ray_dashboard_address']`, threaded into
  `Function.execute(…, dashboard_address=…)`. It is **not** a Service field.
- `RayPlantPort` connect wait is **180s** (kind/KubeRay cold start); failures mention dashboard readiness.
- Static NodePort `30265` → host `8265` via kind `extraPortMappings`
  (`data/input/structure/plant/main.tf`).

### [MinIO Console — scratch](http://127.0.0.1:9001)

- **URL:** http://127.0.0.1:9001 (S3 API: http://127.0.0.1:9000)
- **Credentials:** `cats-scratch` / `cats-scratch-secret`
- Structure-lifetime scratch (`cats-scratch` / `jobs/<uuid>/result`). Volume
  `structure_minio_scratch_data`; ILM 7 days + Structure destroy `down -v`. Integration
  outputs for provenance remain IPFS (`invoice` integration data id / `ni:`).
  Compose: `infrastructure/minio_scratch_compose.yaml`.

### [MinIO Console — durable Entity Relationship](http://127.0.0.1:9101)

- **URL:** http://127.0.0.1:9101 (S3 API: http://127.0.0.1:9100)
- **Credentials:** `cats-durable` / `cats-durable-secret`
- Node-lifetime Entity Relationship store (`cats-durable`):
  `structures/<applied_structure_id>/er/<name>/` plus `er/current/<name>` pointers
  (`structure_id` in pointer JSON; legacy `structure_cid` readable one cycle).
  Volume `node_minio_durable_data` survives Structure destroy; GC via `gc-er` only.
  Compose: `infrastructure/minio_durable_compose.yaml`.

Both are resolved as one `ObjectStore` from `InfraStructure.obj_store_context()` — **not**
Runtime fields. BOM `log` may record `object_store_result_uri` (scratch) and optional
`durable_er_uri` / `durable_er_pointer`; credential-free endpoints land in Invoice
`object_store_as_executed_cid` via `ObjectStore.snapshot()` (see
[`BOM.md`](./BOM.md#cat-node-http-bom-response)). No CAT Node HTTP API — Consoles, S3, or:

```bash
uv run python data/input/structure/infrastructure/obj_store_utils.py list-jobs
uv run python data/input/structure/infrastructure/obj_store_utils.py resolve-er <name>
```

Details: [`MinIO.md`](./MinIO.md), roles: [`STORAGE.md`](./STORAGE.md).

### [IPFS WebUI](http://127.0.0.1:5001/webui) (optional)

- **URL:** http://127.0.0.1:5001/webui
- Optional host Kubo daemon UI when you run Kubo for operator tooling (§6s — not required for
  CAS-only Orders). See [`IPFS.md`](./IPFS.md) / `make content-store-ensure`.
- Live content-store reads/writes use Node CAS (`GET /ldp/cas/<hex>`), not the gateway.
