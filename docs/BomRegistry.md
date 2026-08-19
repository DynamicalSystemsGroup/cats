# Node-local BOM registry (`BomRegistry`)

`BomRegistry` (`cats/network/registry/`) is the Node-local **query index** of verified
[ExecutionBom](BOM.md#cat-node-http-bom-response) envelopes. It is how the
[Control-Feedback Loop](ControlFeedbackLoop.md) discovers the next **Order** from a
prior BOM (`content_id` → Order equality id) and recovers *which* BOM produced a given
output (`data` / `content_id` → `[bom_ids, …]`) without a caller-held HTTP `cat_response`.

Digest/`ni:` remains the **equality / lineage key** for Invoice / Order / stage bytes;
**new** mints carry HTTP `*_uri` only as the data-plane address of record (§6d — no `*_cid`
JSON keys). The registry is an append-only **projection** of those envelopes — not a second
store of provenance payloads. `LocatorIndex` (`by-content/`) maps content ids to HTTP CAS /
Order / Invoice locators. Index **keys** stay hash-based (`by-data` / `by-order`), not URL-based.
HTTP projections use `project_record` (`content_id`, `order`, `data`, `*_uri` — no `*_cid`).

| This is | This is not |
| --- | --- |
| Queryable index of verified BOMs | The envelope store ([`BomLdpStore`](SOLID.md) / Solid) |
| Written on `Runtime.execute` (fail closed) | [LDN](https://www.w3.org/TR/ldn/) Announce (push-only, best-effort) |
| Node-local under `{CATS_HOME}/.cats/registry/` | Mesh-federated / Action Plane catalog |
| GET `/ldp/registry/…` | HTTP PUT of records (405; Runtime indexes only) |

Always on (same policy as the Node LDP cache): no env gate. Index write failure
fails `Runtime.execute`. Needed even if Kubo stays forever — lineage / `init` /
`link*` still cannot find a BOM from data equality alone without this index.

## Why it exists

The Control-Feedback Loop specifies that the next Order is consumed **from within
a BOM** (`invoice.order_uri` / equality id) rather than only supplied out-of-band.
Lineage chains by carrying each CAT’s output data digest into the next Invoice —
a BOM’s own `content_id` is never written into the signed envelope (it is response / LDP only).

Without a registry:

- `POST /cat/node/init` could only take a bootstrap Order locator.
- `linkProcess` / `linkStructure` / `linkOrder` required a prior HTTP
  `cat_response` in the caller’s process.

The registry closes those gaps **on one Node**. §6d hard-drop of `*_cid` names and
§6f `hl:` handoff are **landed**; remaining work is mesh federation of the index
(§6g–§6h). See [`W3C.md`](W3C.md).

```mermaid
flowchart LR
  Runtime[Runtime.execute]
  Sign[sign_execution_bom]
  Ldp[BomLdpStore]
  Solid[optional Solid PUT]
  Reg[BomRegistry.put]
  Init["POST /cat/node/init"]
  Link["linkProcess / linkStructure / linkOrder"]
  Lookup[lookup_order / lookup_bom]
  Flatten[flatten_bom]
  Data[AddressStore CID reads]

  Runtime --> Sign --> Ldp --> Solid --> Reg
  Init -->|"order_uri / content_id / hl"| Data
  Init -->|"bom_uri or data_uri / hl:"| Lookup
  Link -->|"cat_response"| Flatten
  Link -->|"content_id / data_uri / bom_uri / hl"| Lookup
  Lookup --> Flatten --> Data
```

## Record shape

`build_record(bom, bom_cid, *, content_mesh, locators)` **verifies** the signed
envelope (`verify_execution_bom`), then extracts Invoice / Order fields via
AddressStore. It does **not** trust client-supplied index fields beyond optional
locators. Unsigned or tampered proofs raise `RegistryError`.

```text
{
  content_id, invoice_uri, order, order_uri, data, data_uri,
  input_data, node_did,
  function, structure,
  locators: { bom_ldp_uri, bom_solid_uri, invoice_uri, order_uri },
  ingress_data / ingress_data_uri,
  integration_data / integration_data_uri,
  seed / seed_uri
}
```

Stage equality ids / URIs are stored on the record but **not** reverse-indexed in
this MVP. If the Order graph is only partially available, `build_record` still
indexes BOM → Order / data and leaves `function` / `structure` / `input_data` unset.
Legacy on-disk records with `*_cid` remain readable via `_record_*_id` helpers.

## Disk layout

JSON under `{CATS_HOME}/.cats/registry/` (mirrors `BomLdpStore`; no SQLite).
Path segments are CID- or digest-safe (`content_id_fs_key`). `put` is idempotent
on `content_id`. Reverse-index files are append-if-absent lists, **newest first**.
CAS locators live under `by-content/` (hex digest keys).

```text
{CATS_HOME}/.cats/registry/
├── boms/<content_id>.json       # record (fields above)
├── by-data/<data>.json          # [bom_ids, …]  (replay / re-execute)
├── by-order/<order>.json        # [bom_ids, …]  (many BOMs per Order)
└── by-content/<digest>.json     # { content_id, locators: [{ uri, … }] }
```

Python API (`cats.network.registry.BomRegistry`):

| Method | Returns |
| --- | --- |
| `put(record)` | Writes record; appends reverse indexes if absent |
| `get(content_id)` | Record dict or `None` (also accepts legacy path keys) |
| `lookup_order(content_id)` | Order equality id or `None` |
| `lookup_bom(data)` | `[bom_ids, …]` (newest first) |
| `lookup_by_order(order)` | `[bom_ids, …]` |
| `resolve_unique_bom(data)` | Sole BOM `content_id`, else `RegistryError` / `AmbiguousBomError` |
| `list_boms()` | BOM `content_id` keys by mtime descending |

## Publish on execute

`Runtime.execute` signs the BOM, mints content id on **CAS** (`ni:`), writes
`BomLdpStore`, then (when Solid is configured) dual-writes the envelope.
**After locators are known**, it indexes:

```python
BomRegistry(self.CATS_HOME).put(build_record(
    bom, bom_cid,
    content_mesh=self.contentMesh,
    locators={'bom_ldp_uri': ..., 'bom_solid_uri': ...},
))
```

Fail closed (same policy as Solid PUT). LDN stays best-effort and is **not**
the index. Registry indexing still runs when Solid env is unset
(`bom_solid_uri` is `null`).

## Query HTTP (GET only)

Registered from [`cats/node/app.py`](../cats/node/app.py) next to LDP
(`register_registry_routes`). Writes are Runtime-only.

| Route | Response |
| --- | --- |
| `GET /ldp/registry/` | LDP Basic Container listing newest BOM content-id URIs |
| `GET /ldp/registry/boms/<digest>` | Projected record JSON (`content_id` + `*_uri`); missing → 404; **PUT → 405** |
| `GET /ldp/registry/by-data/<data>` | `{content_id, bom_ids: [...]}` (newest first) |
| `GET /ldp/registry/by-order/<order>` | `{content_id, bom_ids: [...]}` |
| `GET /ldp/registry/by-content/<digest>` | `{ content_id, locators: [...] }` (CAS locator index) |

Invalid CID path segments → 400. `HEAD` / `OPTIONS` follow the LDP resource /
container header pattern used by `/ldp/boms/`.

**Not the registry:** `GET /ldp/boms/` (local envelope list), Solid GET by a
known `bom_cid`, LDN Announce. Those are locators / notifies; this is the
**queryable index**.

## `POST /cat/node/init` intake

Body may identify the Order via §6d intake keys. Legacy `order_cid` / `bom_cid` /
`data_cid` → **HTTP 400**.

| Body | Resolution |
| --- | --- |
| `{order_uri}` | Resolve URI → Order equality id → Factory |
| `{bom_uri}` / `{bom_ldp_uri}` / `{bom_solid_uri}` | Resolve URI → `lookup_order` → Factory |
| `{content_id}` / `{data_uri}` | Data equality → unique BOM → Order; 0 → **404**; several → **409** `{bom_ids}` |
| none of the above | **400** |

Unique `{content_id}` / `{data_uri}` execute **that** Order (consume the plan from
the indexed BOM). Forward chaining remains `link*`.

## `linkProcess` / `linkStructure` / `linkOrder`

Each helper still accepts a prior HTTP `cat_response`. When that object is
omitted, pass `content_id=` / `data_uri=` / `bom_uri=` instead. Explicit `bom_uri` always
wins if both are set.

`OrderOps._response_from_registry` loads the registry record, then the signed
envelope from local `BomLdpStore` (fallback `fetch_bom_envelope` via
`bom_ldp_uri` / `bom_solid_uri`), and returns `{bom, content_id, bom_ldp_uri,
bom_solid_uri}` for the existing `flatten_bom` path. Same 404 / 409 rules as
`init` for ambiguous data (`AmbiguousBomError.bom_ids`). Passing `bom_cid=` or
`data_cid=` raises `RuntimeError`.

## Ambiguous reverse lookup

Replay can mint many BOMs per Order and many BOMs per data digest.
`lookup_bom` / `lookup_by_order` therefore return **lists**. Intake that must
pick a single producer (`init` / `link*` with only `content_id` / `data_uri`)
succeeds only when the list has exactly one entry; otherwise **409** with the
candidate `bom_ids`. Pass `bom_uri` / a specific BOM locator to disambiguate.

A “downstream” pointer (who later consumed this output) is still deferred:
no BOM can know at creation time who will consume it. That link is only
discoverable from the consuming CAT’s side, going forward — see
[`LineageOfProvenance.md`](LineageOfProvenance.md).

## Out of scope (later)

Beyond Phase 2b / §6d / §6f (URI-only graph + `ni:` equality + `hl:` handoff landed):

- Mesh federation of the index / Action Plane catalog filters
- Solid PUT of registry records
- Mesh-federated / Solid dual-write of CAS locator maps
- Required Invoice `hl:` (§6i)
- SPARQL over the index
- Consumer-side downstream edges
- Plant / MinIO / Ray

## Tests

```bash
uv run pytest -s tests/test_bom_registry.py
```

Covers store put/get, idempotent `content_id`, reverse-index append, path
rejection, unsigned/tampered `build_record`, Invoice `data` equality (not a lying
hint), Flask GET / PUT 405, `init` legacy `*_cid` → 400 / `{content_id}` /
`{data_uri}` / 409, and `linkProcess(content_id=…)` (rejects `bom_cid=` /
`data_cid=`). Runtime execute indexing is asserted in
[`tests/test_ldp_bom_control_plane.py`](../tests/test_ldp_bom_control_plane.py).
CAS put/get/verify, manifests, and locators: [`tests/test_cas_http.py`](../tests/test_cas_http.py).
Phase 2b URI + §6d hard-drop: [`tests/test_phase2b_uri.py`](../tests/test_phase2b_uri.py).

See also [`TEST.md`](TEST.md).

## Related docs

- [`BOM.md`](BOM.md) — signed envelope, Invoice/Order CID nest, HTTP response
- [`ControlFeedbackLoop.md`](ControlFeedbackLoop.md) — Order-from-BOM intake (notes 2 & 5)
- [`LineageOfProvenance.md`](LineageOfProvenance.md) — `data_cid` reverse lookup; `link*`
- [`NodeLifeCycle.md`](NodeLifeCycle.md) — Flask routes served by `node-start`
- [`SOLID.md`](SOLID.md) — envelope locators vs this index
- [`W3C.md`](W3C.md) — provenance discovery; CAS-over-HTTP + Phase 2b MVP landed; remaining federation / hard-drop `*_cid`
- [`DESIGN.md`](DESIGN.md) — next Order discovered via registry, not only `order_cid`
- [`INTEROP.md`](INTEROP.md) — `link*` as Structure-lineage ops for second-Plant prove
