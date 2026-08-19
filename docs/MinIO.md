### Manage InfraStructure MinIO (scratch + durable Entity Relationship)

CATs runs **two hard-isolated MinIO daemons** under InfraStructure [IaaS], both
[S3-compatible](https://min.io/product/s3-compatibility):

| Daemon | Bucket | Role | Lifetime |
|--------|--------|------|----------|
| **Scratch** | `cats-scratch` | Plant parallel Ray job landing destined for IPFS (`integration_data_id` / `ni:`) | Structure: ILM expire **7 days** + destroy `down -v` hard floor |
| **Durable Entity Relationship** | `cats-durable` | Structure-namespaced Entity Relationship tables + global `er/current/` read index | Node: no ILM; survives Structure destroy; explicit `gc-er` only |

Plant workers and `ObjectStore` use standard S3 semantics (`s3://…`, bucket/key layout).
Durable **CAT product** retrieval after a run remains IPFS (`invoice` integration data id / `ni:`),
not MinIO scratch. Durable MinIO is for **Entity Relationship lookups** across Structure
generations — not an IPFS substitute. See [`STORAGE.md`](./STORAGE.md).

Access is **InfraStructure-as-Code** (directory model): `data/input/structure/infrastructure/`
is CID’d as `infrastructure_cid`. Runtime resolution is `ObjectStore` via
`InfraStructure.obj_store_context()` — **not** a Runtime field. Scratch:
`begin_job` / `write_job_scratch` / `download_job_result` / `JobHandle`. Durable Entity
Relationship: `er_uri` / `write_er` / `promote_er` / `resolve_er` / `gc_er`. Ray landing
for scratch CSV stays Plant-owned under `plant_cid`. There is **no CAT Node HTTP API** —
use Consoles, S3 API, or `obj_store_utils.py` CLI.

#### Automatic lifecycle

Structure Terraform (`Structure.deploy()` / `redeploy()` / `reconcile()`) starts both
MinIOs in `data/input/structure/infrastructure/main.tf`:

**Scratch** (`shell_script.docker_compose_minio_scratch` + `minio_scratch_compose.yaml`):

1. `docker-compose -p structure -f …/minio_scratch_compose.yaml up -d --wait`
2. Health: `http://127.0.0.1:9000/minio/health/ready`
3. `mc mb -p local/cats-scratch` + ILM expire 7 days
4. Destroy: `docker-compose … down -v` (wipes `structure_minio_scratch_data`)

**Durable** (`shell_script.docker_compose_minio_durable` + `minio_durable_compose.yaml`):

1. `docker-compose -p structure -f …/minio_durable_compose.yaml up -d --wait`
2. Health: `http://127.0.0.1:9100/minio/health/ready`
3. `mc mb -p local/cats-durable` (no ILM)
4. Destroy: **no-op** — leave daemon/volume (`node_minio_durable_data`) for the Node

Both attach to the external `kind` network so Ray pods reach S3 via the kind gateway
(`minio_scratch_endpoint_pod` / `minio_durable_endpoint_pod`).

#### Endpoints

| Surface | Scratch | Durable Entity Relationship |
|---------|---------|------------------------------|
| S3 API | http://127.0.0.1:9000 | http://127.0.0.1:9100 |
| Console | http://127.0.0.1:9001 | http://127.0.0.1:9101 |
| Default user | `cats-scratch` | `cats-durable` |
| Default password | `cats-scratch-secret` | `cats-durable-secret` |

Change credentials before exposing consoles. See [`DASHBOARDS.md`](./DASHBOARDS.md).

#### Object layout

**Scratch** (JobHandle):

```text
cats-scratch/jobs/<uuid>/result/*.csv
```

BOM `log.object_store_result_uri`: `s3://cats-scratch/jobs/<uuid>/result`

**Durable Entity Relationship** (structure namespace + global pointer):

```text
cats-durable/structures/<applied_structure_id>/er/<name>/…
cats-durable/er/current/<name>          # pointer JSON → structure-scoped URI
```

Pointer shape:

```json
{"uri":"s3://cats-durable/structures/<id>/er/<name>","structure_id":"<id>","name":"<name>"}
```

New promotes write `structure_id`. `gc_er` / pointer reads still accept legacy
`structure_cid` for one migration cycle. Path segments under `structures/<id>/`
stay opaque (not renamed).

Writes go under the structure namespace; ambient Node reads use `resolve_er` after an
explicit `promote_er`. BOM `log` may record `durable_er_uri` / `durable_er_pointer`
when promote is used (otherwise `null`).

#### CLI (no Node API)

```bash
# Scratch
uv run python data/input/structure/infrastructure/obj_store_utils.py list-jobs
uv run python data/input/structure/infrastructure/obj_store_utils.py list-files <job_uuid>
uv run python data/input/structure/infrastructure/obj_store_utils.py get-file <job_uuid> <name.csv>

# Durable Entity Relationship
uv run python data/input/structure/infrastructure/obj_store_utils.py write-er <structure_id> <name> <local_path>
uv run python data/input/structure/infrastructure/obj_store_utils.py list-er <structure_id>
uv run python data/input/structure/infrastructure/obj_store_utils.py promote-er <structure_id> <name>
uv run python data/input/structure/infrastructure/obj_store_utils.py resolve-er <name>

# Pointer-aware GC (roots = er/current/*; never runs on Structure destroy)
uv run python data/input/structure/infrastructure/obj_store_utils.py gc-er --dry-run
uv run python data/input/structure/infrastructure/obj_store_utils.py gc-er --delete
uv run python data/input/structure/infrastructure/obj_store_utils.py gc-er --structure-id <id> --delete --force
```

Env overrides: `MINIO_SCRATCH_*` (scratch; `MINIO_*` still accepted as fallback),
`MINIO_DURABLE_*` (durable).

**Nuclear wipe** (not normal GC): remove Docker volume `node_minio_durable_data` or
`mc rb --force` on `cats-durable`.

#### Related docs

- [`STORAGE.md`](./STORAGE.md) — scratch vs durable Entity Relationship vs IPFS
- [`IPFS.md`](./IPFS.md) — host Kubo content-store facet
- [`DASHBOARDS.md`](./DASHBOARDS.md) — both MinIO Consoles
- [`BOM.md`](./BOM.md#cat-node-http-bom-response) — `object_store_as_executed_cid` / log correlators
