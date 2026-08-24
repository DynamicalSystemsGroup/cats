# Solid control plane (Phase 2a)

CATs dual-publishes **signed ExecutionBom** envelopes to an external
[Solid](https://solidproject.org/) pod (Community Solid Server–compatible HTTP
API) when configured. The **data plane** is unchanged: **CID** remains the
address of record; peers resolve Invoice / log / Quantum bytes via
AddressStore (gateway + verify).

Node-hosted `GET /ldp/boms/` stays a **local cache/mirror**. HTTP PUT on the
Node LDP routes remains **405**. Solid is the open-world write surface under
WAC.

## Planes

| Plane | What | Address of record |
| --- | --- | --- |
| **Data** | Quantum blobs, Invoice/log, IaC | **CID** (AddressStore) |
| **Control** | Signed ExecutionBom JSON-LD | **Solid URI** when set; else Node `bom_ldp_uri` |

## Publish flow

1. `Runtime.execute` signs the BOM (Data Integrity `eddsa-jcs-2022`) and mints `bom_cid`.
2. Writes local `BomLdpStore` → response `bom_ldp_uri`.
3. If `SOLID_POD_BASE_URL` is set: PUT to `{base}/boms/{bom_cid}` → `bom_solid_uri`.
   - **Fails** `Runtime.execute` when Solid is configured and PUT fails (dual-write consistency).
4. Indexes a Node-local **BOM registry** record (`BomRegistry.put` after locators are known; fail closed).
   This is **not** a Solid dual-write — see [`BomRegistry.md`](BomRegistry.md).
5. After successful Solid PUT: best-effort LDN announce to `SOLID_LDN_INBOX_URLS`
   (Inbox down does **not** fail execute).
6. Peers: `fetch_bom_envelope(bom_solid_uri)` → verify proof → CID refs via AddressStore.

When Solid env is unset, behavior matches the Node LDP slice only
(`bom_solid_uri` is `null`); registry indexing still runs.

## Identity and ACL

- **WebID:** `cats/network/identity/webid.py` emits a minimal profile linking the
  Node `did:key` verification method. Data Integrity proofs stay on `did:key`.
  Override the agent URI with `SOLID_WEBID`; otherwise a local
  `{CATS_HOME}/.cats/webid.jsonld` `file://` URI is used.
- **WAC bootstrap:** call once after pod credentials are ready:

```bash
uv run python -c "
from cats.network.ldp import ensure_solid_bom_acl
print(ensure_solid_bom_acl())
"
```

  Grants the Node agent `acl:Write` / `acl:Append` / `acl:Control` on the BOM
  container; readers from `SOLID_BOM_READERS` (comma-separated WebIDs), or
  public `foaf:Agent` Read when unset.

## Environment

Set these in the repo-root `.env` (see [`.env.example`](../.env.example) /
[`ENV.md`](./ENV.md)). `cats` loads that file on import; already-exported
shell variables win. Unset `SOLID_POD_BASE_URL` leaves Solid off.

| Variable | Required | Description |
| --- | --- | --- |
| `SOLID_POD_BASE_URL` | for Solid | Pod base URL (e.g. `https://pod.example/user/`) |
| `SOLID_BOMS_PATH` | no | BOM container path (default `/boms`) |
| `SOLID_CLIENT_ACCESS_TOKEN` | auth* | Bearer token for CSS client credentials |
| `SOLID_CLIENT_ID` / `SOLID_CLIENT_SECRET` | auth* | HTTP Basic fallback when no access token |
| `SOLID_LDN_INBOX_URLS` | no | Comma-separated Inbox URLs for LDN Announce |
| `SOLID_WEBID` | no | Agent WebID URI (else local `.cats/webid.jsonld`) |
| `SOLID_BOM_READERS` | no | Comma-separated reader WebIDs (default public Read) |

\*One of Bearer token or client id+secret is required when Solid is configured.

This repo does **not** host a Solid server — run [Community Solid Server](https://github.com/CommunitySolidServer/CommunitySolidServer) (or compatible) separately.

## See also

- [`BOM.md`](BOM.md) — HTTP response fields `bom_cid`, `bom_ldp_uri`, `bom_solid_uri`
- [`BomRegistry.md`](BomRegistry.md) — Node-local query index (not the envelope store)
- [`NodeLifeCycle.md`](NodeLifeCycle.md) — Node LDP cache + registry query routes
- [`STORAGE.md`](STORAGE.md) — ContentStore / MinIO (data plane; unchanged by Solid)
- [`ControlFeedbackLoop.md`](ControlFeedbackLoop.md) — Control-Feedback Loop + registry intake
