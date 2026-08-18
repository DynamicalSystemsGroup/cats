# Node Lifecycle

CAT Node process lifecycle: **ensure** host ContentStore, **start** / **stop** Flask, and **status**.

CLI: `uv run python -m cats.node {start|stop|status|ensure}` (default: `start`).
Make targets wrap the same commands.

**Ownership rule:** Node is a client of InfraStructure’s long-lived **content-store facet** (host Kubo).
`start` **asserts** readiness only; `ensure` **heals**/starts Kubo; `stop` kills Flask only — never host Kubo.

## Quick reference

| Goal | Make | Equivalent CLI |
|------|------|----------------|
| Bring node online (common path) | `make node-up` | ensure, then start |
| Tear down Flask + host Kubo | `make node-down` | stop, then `ipfs shutdown` (Make-only) |
| Heal / start host Kubo only | `make content-store-ensure` | `uv run python -m cats.node ensure` |
| Bind Flask (ContentStore must already be ready) | `make node-start` | `uv run python -m cats.node start` |
| Flask listen + ContentStore ready | `make node-status` | `uv run python -m cats.node status` |
| Stop Flask only | `make node-stop` | `uv run python -m cats.node stop` |

```bash
# from repo root
make node-up                 # content-store-ensure && node-start
make node-status             # flask=up|down + content_store=ready|not_ready
make node-stop               # Flask only — host Kubo left running
make node-down               # node-stop then ipfs shutdown (full local teardown)
```

## Why ensure and start are separate

`make node-up` is a **Make-only** convenience that runs `content-store-ensure` then `node-start`.
`python -m cats.node start` remains assert-only.

| Target / CLI | Role |
|--------------|------|
| `make content-store-ensure` / `uv run python -m cats.node ensure` | Operator **mutate**: repo-tree `ContentStore.ensure` (heal/start host Kubo) |
| `make node-start` / `uv run python -m cats.node start` | Client **assert**: bind Flask only if ContentStore API is already ready; does **not** heal Kubo |
| `make node-up` | Convenience: ensure, then start |
| `make node-down` | Convenience: `node-stop` then `ipfs shutdown` (Make-only; not in `cats.node`) |

**Why keep them separate**

- **AQ ownership:** InfraStructure / the operator heal the content-store facet; the Node client only asserts readiness before binding Flask.
- **Ops flexibility:** Skip ensure when Kubo is already up, or debug ensure vs Flask bind independently. Use `node-up` for the common “bring the node online” path. Use `node-stop` when Kubo should keep serving CIDs; use `node-down` for full local teardown.

Details: [`STORAGE.md`](./STORAGE.md#node-up-vs-content-store-ensure-and-node-start). Content-store phases and heal behavior: [`IPFS.md`](./IPFS.md).

## Commands

### Ensure ContentStore (host Kubo)

Required **before** `node-start` if the ContentStore HTTP API (`:5001` by default) is down.
Start fails loud if Kubo is not ready.

```bash
make content-store-ensure
# or: uv run python -m cats.node ensure
# or: uv run python data/input/structure/infrastructure/content_store_utils.py ensure
```

- Heals stale `~/.ipfs/repo.lock` when the API is down but a lock is held, then starts Kubo.
- Does **not** start Flask, kind, Ray, MinIO, or Docker transport.
- Exit `0` when ready; non-zero on failure.

### Start

```bash
make node-start
# or: uv run python -m cats.node start
```

- Strict bootstrap `ContentStore.is_ready` before Flask binds.
- Clears a prior `cats.node` listener on the Node port (does not kill unrelated processes, e.g. AirPlay on 5000).
- Fails loud if the port is still held by a non-`cats.node` process — set `CAT_NODE_PORT` (e.g. `5002`) when macOS AirPlay owns `:5000`.
- On SIGINT / SIGTERM, exits without stopping host Kubo.
- Serves Order entry at `POST /cat/node/init` and Phase 2a LDP control plane
  (local cache; Solid dual-write is separate — see [`SOLID.md`](SOLID.md);
  registry contract: [`BomRegistry.md`](BomRegistry.md)):
  - `GET /ldp/boms/` — Basic Container listing published BOM URIs
  - `GET /ldp/boms/<bom_cid>` — signed ExecutionBom JSON-LD (publish via `Runtime.execute` only; HTTP PUT → 405)
  - `GET /ldp/registry/` — BOM registry container (Node-local index)
  - `GET /ldp/registry/boms/<bom_cid>` — registry record JSON; PUT → 405
  - `GET /ldp/registry/by-data/<data_cid>` — `{data_cid, bom_cids: [...]}`
  - `GET /ldp/registry/by-order/<order_cid>` — `{order_cid, bom_cids: [...]}`
  - `POST /cat/node/init` — body may use `order_cid` (bootstrap), or `bom_cid` / unique `data_cid` via the registry (ambiguous `data_cid` → 409)
### Status

```bash
make node-status
# or: uv run python -m cats.node status
```

Prints:

```text
flask=up|down
content_store=ready|not_ready
```

Exit `0` only when Flask is listening **and** ContentStore is ready; otherwise `1`.

Content-store-only status (API up/down, no Flask check):

```bash
uv run python data/input/structure/infrastructure/content_store_utils.py status
```

### Stop

```bash
make node-stop
# or: uv run python -m cats.node stop
```

Stops the Flask Node process only. Host Kubo stays up on purpose (mesh CIDs / ContentMesh outlive Structure destroy and Node exit).

### Down (Flask + host Kubo)

```bash
make node-down
# equivalent: make node-stop && ipfs shutdown
```

Make-only convenience: runs `node-stop`, then `ipfs shutdown`. Does **not** live in `python -m cats.node stop` — the Node CLI remains a ContentStore client and must not shut down host Kubo. Prefer `node-stop` when you still want BOM / CID inspection or the next session to reuse Kubo; use `node-down` when you intend to tear down the local daemon too. `ipfs shutdown` is best-effort (ignored if the API is already down).

## Related docs

- [`INSTALL.md`](./INSTALL.md) / [`ENV.md`](./ENV.md) — clone, `uv sync`, environment
- [`DEMO.md`](./DEMO.md) — mesh demo after the Node is up
- [`TEST.md`](./TEST.md) — integration tests that need a live Node
- [`BomRegistry.md`](./BomRegistry.md) — Node-local BOM query index (`GET /ldp/registry/…`)
- [`STORAGE.md`](./STORAGE.md) — content-store vs scratch ownership; why ensure ≠ start
- [`IPFS.md`](./IPFS.md) — host Kubo facet, two-phase ensure, peering
- [`DASHBOARDS.md`](./DASHBOARDS.md) — Ray / MinIO / IPFS WebUI once Structure is deployed
