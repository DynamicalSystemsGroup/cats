### Manage the Structure MinIO Shared Object Store

CATs uses MinIO as InfraStructure [IaaS] **shared object store / scratch** for Plant-side parallel Ray
writes (bucket `cats-scratch`). Durable post-run retrieval of integration outputs is via IPFS
(`invoice.integration_data_cid`), not MinIO. See [`STORAGE.md`](./STORAGE.md).

#### Automatic lifecycle — usually nothing to do

Structure’s Terraform (`Structure.deploy()` / `redeploy()` / `reconcile()`) starts MinIO via
`shell_script.docker_compose_minio` in
`data/input/structure/modules/infrastructure/main.tf`:

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
`data/input/structure/modules/infrastructure/main.tf`):

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
minio_result_uri: s3://cats-scratch/jobs/<uuid>/result
```

Use that URI (or the Console) to find Structure-lifetime scratch objects. Host download + `cidDir` still
produce `invoice.integration_data_cid` for durable IPFS access. Objects are **not** deleted after each
`cidDir`; they remain until Structure destroy (`down -v`).

#### Opt-in CAT Node jobs API (default: off)

By default the CAT Node does **not** expose MinIO job data (`GET /cat/node/minio/jobs…` returns `403`).

Enable Structure-lifetime read access:

```bash
export CAT_MINIO_JOBS_API=1
# then start / restart cats/node.py
```

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/cat/node/minio/jobs` | List job UUIDs under `cats-scratch/jobs/` |
| `GET` | `/cat/node/minio/jobs/<job_uuid>` | List files under `…/result/` |
| `GET` | `/cat/node/minio/jobs/<job_uuid>/files/<name>` | Stream a CSV |

When enabled but MinIO/Structure config is unavailable, those routes return `503`. Credentials are never
returned in API responses. Correlate jobs via `log.minio_result_uri`.

Unset `CAT_MINIO_JOBS_API` (or set it to anything other than `1` / `true` / `yes`) to keep the default:
no access.

#### Related docs

- [`STORAGE.md`](./STORAGE.md) — MinIO vs IPFS roles under InfraStructure [IaaS]
- [`IPFS.md`](./IPFS.md) — host Kubo daemon lifecycle
- [`DASHBOARDS.md`](./DASHBOARDS.md) — MinIO Console link
- [`BOM.md`](./BOM.md) — `infrastructure_snapshot_cid` and Invoice stage CIDs
