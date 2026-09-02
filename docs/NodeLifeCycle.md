# Node Lifecycle

CAT Node process lifecycle: **ensure** host ContentStore, **start** / **stop** Flask, and **status**.

CLI: `uv run python -m cats.node {start|stop|status|ensure}` (default: `start`).
Make targets wrap the same commands.

**Ownership rule:** Node is a client of InfraStructure’s long-lived **content-store facet**.
Host Kubo is **optional** operator tooling (`ContentStore.ensure`); **new** content lives on
Node **CAS-over-HTTP** (`GET /ldp/cas/<hex>`). `start` **[soft-probes](W3C.md#6r-soft-kubo-probe)** ContentStore
(Kubo optional for [CAS-only Orders](W3C.md#6s-cas-only-node)); `ensure` **heals**/starts Kubo if you want it; `stop` kills
Flask only — never host Kubo.

## Quick reference

| Goal | Make | Equivalent CLI |
|------|------|----------------|
| Bring node online (common path) | `make node-up` | ensure, then start |
| Tear down Flask + host Kubo | `make node-down` | stop, then `ipfs shutdown` (Make-only) |
| Heal / start host Kubo only | `make content-store-ensure` | `uv run python -m cats.node ensure` |
| Bind Flask (soft ContentStore probe; Kubo optional) | `make node-start` | `uv run python -m cats.node start` |
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
`python -m cats.node start` [soft-probes](W3C.md#6r-soft-kubo-probe) ContentStore and binds Flask even when Kubo is down.

| Target / CLI | Role |
|--------------|------|
| `make content-store-ensure` / `uv run python -m cats.node ensure` | Operator **mutate**: repo-tree `ContentStore.ensure` (heal/start host Kubo) |
| `make node-start` / `uv run python -m cats.node start` | Client **soft probe**: bind Flask; warn if ContentStore API is down; does **not** heal Kubo |
| `make node-up` | Convenience: ensure, then start |
| `make node-down` | Convenience: `node-stop` then `ipfs shutdown` (Make-only; not in `cats.node`) |

**Why keep them separate**

- **AQ ownership:** InfraStructure / the operator heal optional host Kubo tooling; the Node client soft-probes and does not own Kubo lifecycle.
- **Ops flexibility:** Skip ensure for CAS-only Orders (default). Use `node-up` when you also want Kubo tooling online. Use `node-stop` when Kubo should keep running; use `node-down` for full local teardown.

Details: [`STORAGE.md`](./STORAGE.md#node-up-vs-content-store-ensure-and-node-start). Content-store phases and heal behavior: [`IPFS.md`](./IPFS.md).

## Commands

### Ensure ContentStore (host Kubo)

Optional operator tooling. Live Orders use Node CAS and do not require Kubo.
`node-start` soft-warns when Kubo is not ready; it does not fail.

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

- Soft-probes bootstrap ContentStore, then binds Flask (does not hard-require Kubo).
- Clears a prior `cats.node` listener on the Node port (does not kill unrelated processes, e.g. AirPlay on 5000).
- Fails loud if the port is still held by a non-`cats.node` process — set `CAT_NODE_PORT` (e.g. `5002`) when macOS AirPlay owns `:5000`.
- On SIGINT / SIGTERM, exits without stopping host Kubo.
- Serves Order entry at `POST /cat/node/init`, Phase 2a LDP control plane, registry,
  and CAS-over-HTTP data plane (Solid dual-write is separate — see [`SOLID.md`](SOLID.md);
  registry: [`BomRegistry.md`](BomRegistry.md); storage: [`STORAGE.md`](STORAGE.md)):
  - `GET /ldp/boms/` — Basic Container listing published BOM URIs
  - `GET /ldp/boms/<content_id>` — signed ExecutionBom JSON-LD (publish via `Runtime.execute` only; HTTP PUT → 405)
  - `GET /ldp/registry/` — BOM registry container (Node-local index)
  - `GET /ldp/registry/boms/<content_id>` — registry record JSON (`project_record`; no `*_cid`); PUT → 405
  - `GET /ldp/registry/by-data/<data>` — `{content_id, bom_ids: [...]}`
  - `GET /ldp/registry/by-order/<order>` — `{content_id, bom_ids: [...]}`
  - `GET /ldp/registry/by-content/<digest>` — CAS locator map `{ content_id, locators }`
  - `GET /ldp/cas/<digest>` — raw CAS blob bytes (sha256 identity); PUT → 405
  - `GET /ldp/invoices/<id>` — Invoice JSON (Phase 2b URI address); PUT → 405
  - `GET /ldp/orders/<id>` — Order JSON (Phase 2b URI address); PUT → 405
  - `POST /cat/node/init` — body may use `order_uri`, or `bom_uri` / `bom_ldp_uri` / `bom_solid_uri` / unique `content_id` / `data_uri` / `hl` (values may be `hl:` / `ni:` / http) via the registry (legacy `order_cid` / `bom_cid` / `data_cid` → 400; ambiguous → 409 `{bom_ids}`). Set `CAT_NODE_HOST` to a peer-reachable address (or rely on Solid `bom_solid_uri` in `hl:` hints); `127.0.0.1` is not mesh-usable.
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

Stops the Flask Node process only. Host Kubo stays up on purpose when you started it
(optional operator tooling outlives Structure destroy and Node exit).

### Down (Flask + host Kubo)

```bash
make node-down
# equivalent: make node-stop && ipfs shutdown
```

Make-only convenience: runs `node-stop`, then `ipfs shutdown`. Does **not** live in `python -m cats.node stop` — the Node CLI remains a ContentStore client and must not shut down host Kubo. Prefer `node-stop` when Kubo should keep running for the next session; use `node-down` when you intend to tear down the local daemon too. `ipfs shutdown` is best-effort (ignored if the API is already down).

## Related docs

- [`INSTALL.md`](./INSTALL.md) / [`ENV.md`](./ENV.md) — clone, `uv sync`, environment
- [`DEMO.md`](./DEMO.md) — mesh demo after the Node is up
- [`TEST.md`](./TEST.md) — integration tests that need a live Node
- [`BomRegistry.md`](./BomRegistry.md) — Node-local BOM query index (`GET /ldp/registry/…`)
- [`STORAGE.md`](./STORAGE.md) — content-store vs scratch ownership; why ensure ≠ start
- [`IPFS.md`](./IPFS.md) — optional host Kubo facet, two-phase ensure (no Docker peers)
- [`DASHBOARDS.md`](./DASHBOARDS.md) — Ray / MinIO / IPFS WebUI once Structure is deployed
