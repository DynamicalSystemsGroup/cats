### Manage the Structure MinIO Shared Object Store

CATs uses MinIO as InfraStructure [IaaS] **shared object store / scratch** for Plant-side parallel Ray
writes (bucket `cats-scratch`). Durable post-run retrieval of integration outputs is via IPFS
(`invoice.integration_data_cid`), not MinIO. See [`STORAGE.md`](./STORAGE.md).

MinIO access is **InfraStructure-as-Code** (directory model): the module under
`data/input/structure/infrastructure/` is what `create_order_request()` CIDs as
`infrastructure_cid`. Object-store config is resolved at runtime as `ObjectStore` via
`InfraStructure.obj_store_context()` (importlib seam into `obj_store_utils.py`) — it is **not** a
Service field. Job scratch write/download (`ObjectStore.begin_job` / `write_job_scratch` /
`download_job_result`), `JobHandle`, Order-submitted `ray_job_result_entrypoint.py`, and
`ray_compute_utils.py` (`RayComputePort`) live in that module tree so InfraFunction only
orchestrates Plant dispatch via `PlantPort`. There is **no CAT Node HTTP API**
for job scratch — use the Console, S3 API, or the module’s local CLI (`obj_store_utils.py`).

#### Automatic lifecycle — usually nothing to do

Structure’s Terraform (`Structure.deploy()` / `redeploy()` / `reconcile()`) starts MinIO via
`shell_script.docker_compose_minio` in
`data/input/structure/infrastructure/main.tf`:

1. `docker-compose -p structure -f …/minio_compose.yaml up -d --wait`
2. Wait until `http://127.0.0.1:9000/minio/health/ready` succeeds
3. Bootstrap bucket `cats-scratch` with `minio/mc`

Compose attaches MinIO to the external `kind` Docker network so Ray pods can reach the S3 API through
that network’s gateway IP (`minio_endpoint_pod`). Named volume `structure_minio_data` keeps objects
across container recreate for the Structure’s lifetime.

On Structure destroy, Terraform runs `docker-compose … down -v`, which removes the container **and**
the named volume (scratch is cleared with InfraStructure).

#### Endpoints

| Surface | URL |
|---------|-----|
| S3 API | http://127.0.0.1:9000 |
| Console | http://127.0.0.1:9001 |

Default credentials (`local.minio_root_user` / `local.minio_root_password` in
`data/input/structure/infrastructure/main.tf`):

- User: `cats-minio`
- Password: `cats-minio-secret`

Change these before deploying a Structure whose console would be reachable by anyone else. See also
[`DASHBOARDS.md`](./DASHBOARDS.md).

#### Health check

```bash
curl -sf http://127.0.0.1:9000/minio/health/ready
```

Succeeds (HTTP 200) when MinIO is ready; fails otherwise.

#### Object layout

Ray job result CSVs land under:

```text
cats-scratch/jobs/<uuid>/result/*.csv
```

After a CAT run, the BOM `log` records a non-secret correlator:

```text
object_store_result_uri: s3://cats-scratch/jobs/<uuid>/result
```

Use that URI (or the Console) to find Structure-lifetime scratch objects. Host download + `cidDir` still
produce `invoice.integration_data_cid` for durable IPFS access. Objects are **not** deleted after each
`cidDir`; they remain until Structure destroy (`down -v`).

#### Accessing job scratch (no Node API)

Preferred UI: [MinIO Console](http://127.0.0.1:9001) — browse `cats-scratch/jobs/…`.

Optional CLI shipped in the InfraStructure module (rides in `infrastructure_cid`):

```bash
# from repo root, with Structure MinIO up
uv run python data/input/structure/infrastructure/obj_store_utils.py list-jobs
uv run python data/input/structure/infrastructure/obj_store_utils.py list-files <job_uuid>
uv run python data/input/structure/infrastructure/obj_store_utils.py get-file <job_uuid> <name.csv>
```

Override connection via `MINIO_ENDPOINT`, `MINIO_BUCKET`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` if needed.
Correlate jobs with `log.object_store_result_uri` from the BOM.

#### Related docs

- [`STORAGE.md`](./STORAGE.md) — MinIO vs IPFS roles under InfraStructure [IaaS]
- [`IPFS.md`](./IPFS.md) — host Kubo content-store facet (`ContentStore.ensure`)
- [`DASHBOARDS.md`](./DASHBOARDS.md) — MinIO Console link
- [`BOM.md`](./BOM.md) — `infrastructure_snapshot_cid` and Invoice stage CIDs
