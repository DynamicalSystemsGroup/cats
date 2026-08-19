### Host IPFS / Kubo (optional operator tooling)

**CAS-over-HTTP** is the content-store address of record for live Orders (§6p–§6s).
Host [Kubo](https://docs.ipfs.tech/install/command-line/#system-requirements) is **optional**
operator tooling (`ContentStore.ensure` / `make content-store-ensure` / `node ensure`) — not required
for Node start, Structure apply, or Process migrate/stage. See [`DEPS.md`](./DEPS.md) and
[`STORAGE.md`](./STORAGE.md).

**ContentMesh** writes (`put_bytes` / `put_json` / `put_tree` / `put_dir` / `put_file`) require
`CATS_HOME` and mint on CAS (`ni:`). Reads (`cat` / `catObj` / `get`) go through
`cats.network.address_store.AddressStore`:

| Id form | Read path |
|---------|-----------|
| `ni:` / hex digest | Locator index → `GET /ldp/cas/<hex>` → sha256 verify |
| `hl:` | Hint HTTP URIs then bare `ni:` fallback → sha256 verify |
| `http(s)://…` URI | Local LDP / HTTP GET → sha256 verify when digest known |
| Legacy CID (`Qm…` / `bafy…`) | **Fail closed** (§6s) — remint to `ni:` / HTTP |

`CatsIPFSClient` (`cats/network/clients/ipfs_client.py`) remains available for optional Kubo RPC
smoke / tooling; the Node constructs `ContentMesh(ipfsClient=None)`.

**Partition layout (Process IoPort, §6p):** when `CATS_IO_PARTITIONS>1`, Plant `RayIoPort` builds a directory of opaque `part-XXXXX` files/dirs and `put_dir`s them onto CAS (`ni:` digest-keyed manifest). No Kubo `add` / `getCar` / `dag_export`. Legacy `part-*.car` layouts remain readable one cycle.

Process `migrate` / `stage_for_plant` are **CAS-only** (`ni:` / hex / HTTP). Docker Kubo T&D peers are
**retired** (§6s). No `ipfs` CLI from ContentMesh.

**Same API address for optional ensure/status:** `ContentStore.is_ready` / `ensure` probe
`http://{IPFS_API_HOST}:{IPFS_API_PORT}/api/v0/id`. Optional override: `CATS_IPFS_API_ID_URL`.

Order submit URLs use `CAT_NODE_HOST` / `CAT_NODE_PORT` (default `http://127.0.0.1:5000/cat/node/init`).

#### Ownership

Optional host Kubo lifecycle helpers live in
[`data/input/structure/infrastructure/content_store_utils.py`](../data/input/structure/infrastructure/content_store_utils.py).
The CAT Node and ContentMesh are **clients** only — they must not `ipfs shutdown` on process exit.
Structure `terraform destroy` tears down MinIO scratch / Plant; it does **not** stop host Kubo if you
left one running for tooling.

#### Optional ContentStore ensure

| Phase | When | Which tree |
|-------|------|------------|
| **Bootstrap** | Node `start` / `ensure`; ContentMesh soft-warn; operator CLI | Repo default under `CATS_HOME/data/input/structure/.../content_store_utils.py` |
| **Order soft probe** | `InfraStructure.apply` after terraform | Order-submitted tree (`ContentStore.is_ready` — soft-warn only §6s) |

* **Node start** — soft bootstrap probe; does not heal or hard-require Kubo (§6r/§6s).
* **Node ensure** — operator heal facade: repo-tree `ContentStore.ensure` (no Flask).
* **ContentMesh bootstrap** — lazy soft-warn; `put_dir` / `put_file` require `CATS_HOME`.
* **Order apply** — soft-probes ContentStore; does **not** TF-ensure host Kubo or assert Docker peers.

`ContentStore.ensure` (operator CLI / `node ensure`) heals stale `~/.ipfs/repo.lock` then starts Kubo
when you want the optional daemon.

#### Optional demo / operator CLI

```bash
uv run python data/input/structure/infrastructure/content_store_utils.py ensure
uv run python data/input/structure/infrastructure/content_store_utils.py status
# or: make content-store-ensure

make node-start             # soft-probe; Kubo optional
make node-stop              # Flask only
make node-status            # flask=up|down + content_store=ready|not_ready
uv run python -m cats.node ensure
```

See [`NodeLifeCycle.md`](./NodeLifeCycle.md). Node `status` exits 0 only when Flask is up **and**
ContentStore reports ready (useful when you still run Kubo for tooling).

#### Manual start (optional)

```bash
ipfs daemon
# …
ipfs shutdown
```

### Process transport (CAS-only §6s)

[`transport_utils.py`](../data/input/structure/infrastructure/transport_utils.py) → `TransportContext`
exposes `migrate` / `stage_for_plant` for Function-owned `TransportPort`. Docker Kubo peer Compose /
`ensure_peered` / `assert_ready` are **removed**. Legacy CIDs fail closed.

InfraStructure TF brings up **MinIO** scratch/durable only (no `ipfs_transport` Compose).
