### Manage the Host IPFS Daemon (InfraStructure content-store facet)

CATs relies on a host [IPFS (Kubo)](https://docs.ipfs.tech/install/command-line/#system-requirements) daemon as
InfraStructure [IaaS] **content-addressed storage** — the long-lived **content-store facet** used for Order /
Invoice / BOM / stage CIDs across the [Demo](./DEMO.md) and [Test](./TEST.md) workflows. See [`DEPS.md`](./DEPS.md)
for installing Kubo itself and [`STORAGE.md`](./STORAGE.md) for how this facet relates to Docker transport peers
and MinIO (T&D).

The Python side talks to that daemon with a thin sync Kubo HTTP RPC client
(`cats/network/clients/ipfs_client.py` → `http://{IPFS_API_HOST}:{IPFS_API_PORT}/api/v0/*`,
defaults `127.0.0.1:5001`, via `requests`), not `ipfshttpclient`. **ContentMesh** uses that client
end-to-end for adds **and** reads (`cat` / `get` / `ls` / `dag export`) — it does not shell out to the
`ipfs` CLI. The CLI remains operator-only (manual `ipfs daemon` / `ipfs shutdown` / debugging).

**Same API address for ensure/status:** `ContentStore.is_ready` / `ensure` probe
`http://{IPFS_API_HOST}:{IPFS_API_PORT}/api/v0/id` (same env as `connect()`). Optional override:
`CATS_IPFS_API_ID_URL` (full URL) if you need a non-derived probe path.

Order submit URLs use the same `CAT_NODE_HOST` / `CAT_NODE_PORT` defaults as `cats.node`
(default `http://127.0.0.1:5000/cat/node/init`).

#### Ownership

Host Kubo lifecycle is owned by **InfraStructure** directory-model code. The repo file
[`data/input/structure/infrastructure/content_store_utils.py`](../data/input/structure/infrastructure/content_store_utils.py)
is the **source of truth**; it ships inside `infrastructure_cid`. After Order materialize, TF and
Executor load the **Order-submitted** copy under `INPUT_STRUCTURE_HOME/.../content_store_utils.py`.

The CAT Node and ContentMesh are **clients** only — they must not `ipfs shutdown` the content store on
process exit. Structure `terraform destroy` tears down T&D (Docker peers / MinIO) and Plant but
**does not** stop host Kubo.

#### One daemon, two traffic classes

One host Kubo (default `:5001`, one repo) serves **two traffic classes** on purpose:

1. **Content-store** — durable mesh / provenance CIDs (Order, Invoice, BOM, …) via ContentMesh.
2. **Bitswap peer of T&D** — Structure Docker peers (`TransportContext`) swarm-connect to that same host so migrate/stage can fetch host-added CIDs without a second `IPFS_PATH`.

Peers are Structure-lifetime; the host daemon is not. Destroy / `node stop` never kill host Kubo. This is the soft plane (not a dual-daemon hard split). Details: [`STORAGE.md`](./STORAGE.md#one-daemon-two-traffic-classes).

**Republish lag:** editing the repo `content_store_utils.py` does not change live Orders until Structure
is re-CID’d and a new Order is created. Ensure/heal/`IPFS_API_*` behavior changes require republishing
Structure (and recreating Orders that must pick up the fix). When demo/verification CIDs Structure from
the current checkout, repo and Order trees match (no lag).

**Thin ensure:** `ContentStore.ensure` stays probe + stale-lock heal + daemon start only — no extra side
jobs in this module.

#### Two-phase ensure — bootstrap vs Order-submitted

`ContentStore.ensure` is one implementation, but which `content_store_utils.py` tree runs depends on phase:

| Phase | When | Which tree |
|-------|------|------------|
| **Bootstrap** | Node `start` / `ensure`; ContentMesh readiness check; operator CLI | Repo default under `CATS_HOME/data/input/structure/.../content_store_utils.py` |
| **Execution (mutate)** | TF `shell_script.host_ipfs_daemon` create (bare `terraform apply` or via Executor) | Order-submitted under `INPUT_STRUCTURE_HOME/.../content_store_utils.py` |
| **Execution (assert)** | `InfraStructure.apply` after `terraform apply` | Same Order-submitted tree (`ContentStore.is_ready`) |

* **Node start** (`python -m cats.node start`) — **strict** bootstrap `ContentStore.is_ready` before Flask binds
  (assert-only; does not heal). Fail loud if Kubo is down — run `make content-store-ensure` /
  `python -m cats.node ensure` first. `stop` kills Flask only — **Node stop ≠ content-store stop**.
* **Node ensure** — operator heal facade: repo-tree `ContentStore.ensure` (no Flask).
* **ContentMesh bootstrap** (`ensure_bootstrap_content_store`) — **lazy** readiness soft-warn on the
  default tree only; does **not** call `ensure`. **Not** Order-bound.
* **Order execution** — TF `host_ipfs_daemon` create is the sole **automatic** Order-submitted ensure
  (Executor composes that à la carte unit). `InfraStructure.apply` only **asserts** readiness after TF.

Both probe the Kubo **HTTP API** (`POST http://{IPFS_API_HOST}:{IPFS_API_PORT}/api/v0/id`) before treating
the store as ready — not bare `ipfs id`, which modern Kubo can answer from the local repo with the daemon
down.

`ContentStore.ensure` (operator CLI / TF create / `node ensure`) also heals a common stuck state: API down
with a held `~/.ipfs/repo.lock` (often a hung Kubo that still holds the flock / swarm sockets while `:5001`
is dead — `ipfs shutdown` cannot clear that because it talks to the API). Heal best-effort runs
`ipfs shutdown`, terminates lock-holder / `ipfs daemon` PIDs, removes the stale lock, then starts Kubo.
If the API is already up, it reuses that daemon.

#### Optional demo / operator CLI (content-store facet only)

Ensures **only** host Kubo — no kind, Ray, MinIO, or Docker transport. Prefer this (or `node ensure`)
**before** `make node-start` so start’s assert succeeds:

```bash
# from repo root — canonical InfraStructure CLI
uv run python data/input/structure/infrastructure/content_store_utils.py ensure
uv run python data/input/structure/infrastructure/content_store_utils.py status
# or: make content-store-ensure

# Node lifecycle — full reference: NodeLifeCycle.md
make content-store-ensure   # heal/start host Kubo if needed
make node-start             # or: uv run python -m cats.node start
make node-stop              # Flask only
make node-status            # flask=up|down + content_store=ready|not_ready
uv run python -m cats.node ensure   # operator ContentStore.ensure, no Flask
```

See [`NodeLifeCycle.md`](./NodeLifeCycle.md) for the Node process lifecycle. Content-store `status` exits 0 when the
HTTP API is up, 1 otherwise. Node `status` exits 0 only when Flask is listening **and** ContentStore is
ready. ContentMesh runs a **lazy bootstrap readiness soft-warn** on first IPFS use (no
`ContentStore.ensure` / heal) if you skip Node start / the CLI — never on package import.

#### Manual start (optional)

Run this yourself only if you want the daemon's logs visible in their own terminal:
```bash
ipfs daemon
```
If a daemon is *already* running (from `ContentStore.ensure` / `node ensure`, TF `host_ipfs_daemon`
create, or you) and you run this again, you'll see:
```
Error: lock /Users/<you>/.ipfs/repo.lock: someone else has the lock
```
This is expected and harmless — it just means a daemon is already up and serving.

#### Shutdown

```bash
ipfs shutdown
# or full local teardown (Flask + Kubo): make node-down
```

Stop host Kubo only when you intend to (operator). **Do not** tie shutdown to Node exit / `make node-stop` or
Structure destroy — the content-store facet is meant to outlive those for BOM inspection and the next demo
session. `make node-down` is the Make-only convenience that chains `node-stop` then `ipfs shutdown`; see
[`NodeLifeCycle.md`](./NodeLifeCycle.md).

#### Checking status

```bash
curl -sf -X POST http://127.0.0.1:5001/api/v0/id
```
Succeeds (HTTP 200 + JSON peer info) if the daemon API is up; fails otherwise. This is the same check
`ContentStore.is_ready` / `status` use. Bare `ipfs id` is **not** sufficient — it can succeed offline without
`:5001` listening.

#### Docker transport peering (Transmission & Distribution [T&D] / TransportContext)

Peering is **Structure-owned** via InfraStructure `TransportContext.ensure_peered()` in
`data/input/structure/infrastructure/transport_utils.py` (part of `infrastructure_cid`):

* TF `shell_script.docker_compose_ipfs_transport` **create** — Compose up only (create-once)
* TF `shell_script.ipfs_transport_peering` — sole Order-submitted **mutate** (`ensure-peered`) on **every**
  `terraform apply` via `triggers = { always = timestamp() }` (plan always shows this resource replacing —
  expected; Compose is not recreated)
* `InfraStructure.apply` — only **asserts** `assert_ready` after TF (containers up); does not call `ensure_peered`

Process transport callables (`ingress` / `integration_cache` / `egress`) are a **port**: the Executor passes
`transport` from `InfraStructure.transport_context()`; they only call `migrate` / `stage_for_plant`. Process must
**not** heal or re-peer. If peers are down after TF, `transport_assert` / `assert_ready` fails fast — re-apply
Structure or run the CLI below.

```bash
# from repo root, with transport containers up — sole peering CLI (no shell script)
uv run python data/input/structure/infrastructure/transport_utils.py ensure-peered
uv run python data/input/structure/infrastructure/transport_utils.py status
```

If the host ContentStore isn't up when peering runs, host peering is skipped gracefully — Docker peers can still
connect to each other. Host Kubo remains the durable content-store facet; Docker peers are Structure-lifetime T&D.
There is no `ipfs_connect_peers.sh` — that orphan was retired in favor of `TransportContext.ensure_peered`.
