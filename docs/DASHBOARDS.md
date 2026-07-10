# Dashboards

Once a CAT Node's Structure is deployed — `terraform apply` runs automatically from `cats/node.py` and the
[Demo](./DEMO.md)/[Test](./TEST.md) workflows, so this normally requires no manual step — the following web
dashboards are reachable on `localhost`. All three stay at fixed addresses across reconciles/rebuilds, so
these links keep working for the lifetime of the Structure.

### [Ray Dashboard](http://127.0.0.1:8265)

- **URL:** http://127.0.0.1:8265
- Ray's own dashboard for the Plant's (`module.plant`) KubeRay cluster — job status, actors, cluster/node
  resource usage, and logs for every Ray Job InfraFunction dispatches via the Ray Job Submission API
  (`Processor.Integration()`, `cats/executor/function/__init__.py`).
- Exposed via a static Kubernetes NodePort (`30265`), mapped to this fixed host port by `kind`'s
  `extraPortMappings` (`data/input/structure/modules/plant/main.tf`) — the address never changes across
  reconciles or rebuilds.

### [MinIO Console](http://127.0.0.1:9001)

- **URL:** http://127.0.0.1:9001
- **Credentials:** `cats-minio` / `cats-minio-secret` (`local.minio_root_user`/`local.minio_root_password` in
  `data/input/structure/modules/infrastructure/main.tf`) — change these before deploying this Structure
  anywhere the console would be reachable by anyone else.
- Web console for the shared MinIO bucket (`cats-scratch`) that Ray Data's distributed write tasks and
  `infrafunction_subproc`'s result retrieval use instead of a local filesystem — browse objects, buckets,
  and access policies (`data/input/structure/modules/infrastructure/minio_compose.yaml`).
- See [`LineageOfProvenance.md`](./LineageOfProvenance.md#whats-inside-a-boms-cids) for how this bucket's
  observed state is recorded as `bom.infrastructure_snapshot_cid`.

### [IPFS WebUI](http://127.0.0.1:5001/webui)

- **URL:** http://127.0.0.1:5001/webui
- The host [IPFS (Kubo)](https://docs.ipfs.tech/install/command-line/#system-requirements) daemon's own web
  UI — browse pinned content, peers, and repo stats for everything CID'ed into a BOM/Invoice/Order. See
  [`IPFS.md`](./IPFS.md) for how and when this daemon starts.
- The daemon's Gateway (`http://127.0.0.1:8080/ipfs/<cid>`) is also available for fetching any CID's raw
  content directly in a browser, without needing the WebUI.
