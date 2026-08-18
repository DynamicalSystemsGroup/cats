# Provenance on the W3C path

Scope: **how provenance is modeled, attributed, signed, published, and discovered** — not Plant/MinIO/transport rewrites.

Phases **1 / 1b / 2a** (signed JSON-LD/PROV envelope, AddressStore gateway, Node LDP, optional Solid dual-write), the **Node-local BOM registry**, and **CAS-over-HTTP** (before 2b) are **on mainline**. The `w3c` vs `dev` columns below are a **historical** comparison of pre-merge `dev` (implicit CID threading) against that stack — branches are now tip-aligned. Remaining gaps are mesh federation of the index and Phase 2b URI-as-address — not signing, and not “no reverse lookup at all.”

## One-line verdict (provenance)

* **Before (pre-merge `dev`):** provenance was mostly **implicit** [CID](https://docs.ipfs.tech/concepts/content-addressing/) **threading**.
* **Now (mainline):** lineage is an **explicit,** [DID](https://www.w3.org/TR/did-core/)**-attributed**, [Data Integrity](https://www.w3.org/TR/vc-data-integrity/)**-signed** [JSON-LD](https://www.w3.org/TR/json-ld11/)/[PROV-O](https://www.w3.org/TR/prov-o/) **envelope**, published at [LDP](https://www.w3.org/TR/ldp/)/[Solid](https://solidproject.org/) **HTTP locators** peers can fetch and verify — while **new** data-plane content uses **`ni:`** / digest ([CAS-over-HTTP](STORAGE.md)); legacy **CID** remains readable via Kubo/gateway. Node-local **BOM registry** reverse lookup (`data_cid` → BOM / BOM → Order) is landed ([`BomRegistry.md`](BomRegistry.md)).

## Envelope vs stage payloads (unchanged discipline)

Provenance package stays cheap:

* **In envelope:** Invoice/log CIDs, `node_did`, [PROV-O](https://www.w3.org/TR/prov-o/) edges, [Data Integrity](https://www.w3.org/TR/vc-data-integrity/) proof
* **Out of band:** Ray/MinIO bytes, directory DAGs — Invoice stage CIDs + optional `object_store_result_uri` / durable ER correlators

That split is the design doc’s core packaging rule: Control-Feedback **graph + proofs**, not inlined datasets.

---

## What “provenance” means in CATs

The Control-Feedback Loop’s provenance surface is:

1. **Order** (plan / as-Code Quantum) → [CID](https://docs.ipfs.tech/concepts/content-addressing/) graph
2. **Executor run** (activity) → Invoice + stage CIDs
3. **BOM** (HTTP / control-plane package) → points at Invoice + logs + agent
4. **Registry** (Node-local index) → `bom_cid` → Order; `data_cid` → BOM — so `init` / `link*` need not hold a prior HTTP response

Stage products (`ingress_data_cid`, `integration_data_cid`, `data_cid`, `structure_as_executed_cid`, `seed_cid`) stay **out of the envelope as bytes** — only addresses; `seed_cid` now resolves to a populated Process replay dictionary ([#187](https://github.com/DynamicalSystemsGroup/cats/issues/187)). See also [`LineageOfProvenance.md`](LineageOfProvenance.md) and [`BOM.md`](BOM.md).

### Planes

| Plane | What | Address of record |
| --- | --- | --- |
| **Data** | Quantum blobs, Invoice/log, IaC | **CID** (AddressStore) |
| **Control** | Signed ExecutionBom JSON-LD | **Solid URI** when set; else Node `bom_ldp_uri` |
| **Index** | Verified BOM query projection (`BomRegistry`) | Node-local `{CATS_HOME}/.cats/registry/` (CID keys; not the envelope store) |

---

## Provenance properties: before / now

| Property | Before (pre-merge `dev`) | Now (mainline) |
| --- | --- | --- |
| **Model** | Mostly **implicit** — CID equality between linked objects | **Explicit graph** — [JSON-LD](https://www.w3.org/TR/json-ld11/) + [PROV-O](https://www.w3.org/TR/prov-o/) on the ExecutionBom (`prov:wasAttributedTo`, `prov:wasGeneratedBy`) |
| **Who produced it** | Weak / Node HTTP lifecycle | **`node_did` ([did:key](https://w3c-ccg.github.io/did-method-key/))** as PROV agent; Flask bind is **not** attribution |
| **Tamper-evidence** | CID of unsigned (or ad-hoc) BOM JSON | CID of **signed** object + [Data Integrity](https://www.w3.org/TR/vc-data-integrity/) `proof` ([`eddsa-jcs-2022`](https://www.w3.org/TR/vc-di-eddsa/) / [RFC 8785 JCS](https://www.rfc-editor.org/rfc/rfc8785)) |
| **Envelope contents** | BOM fields in execute response | Address refs only: `invoice_cid`, `log_cid`, `node_did` + `@context` / `@type` + proof |
| **Publish / locator** | Response / Kubo only | + **`bom_ldp_uri`** ([LDP](https://www.w3.org/TR/ldp/) Node cache); optional **`bom_solid_uri`** ([Solid](https://solidproject.org/) dual-write) |
| **Peer verify path** | Trust fetch + CID | `fetch_bom_envelope` → **`verify_execution_bom`** (Node or Solid URL) |
| **Announce to mesh** | — | Best-effort [LDN](https://www.w3.org/TR/ldn/) Announce (`bom_cid`, `bom_solid_uri`) when Solid configured |
| **ACL on write** | N/A (no Solid) | Solid [WAC](https://solid.github.io/web-access-control-spec/) (Node Write; readers / public Read); Node LDP **and** registry PUT stay **405** |
| **Discovery / reverse lookup** | Gap — `init` needed out-of-band `order_cid`; `link*` needed a caller-held `cat_response` ([`LineageOfProvenance.md`](LineageOfProvenance.md)) | **Node-local registry** ([`BomRegistry.md`](BomRegistry.md) / `GET /ldp/registry/…`); `init` / `link*` accept `bom_cid` / unique `data_cid` (ambiguous → 409). Mesh federation still deferred |
| **Intra-run stage lineage** | Invoice stage CIDs only | Same CID addresses on Invoice; signed BOM also carries `stageLineage` PROV entities (`wasDerivedFrom`; reachable after envelope verify via [AddressStore](IPFS.md)) |
| **Large payloads** | [MinIO](https://min.io/) + IPFS CIDs | Same discipline — envelope never embeds stage bytes ([`STORAGE.md`](STORAGE.md)) |

### Discovery (Node-local BOM registry)

The registry is an append-only **query index** of verified envelopes — not `BomLdpStore` / Solid (locators) and not LDN (push). `Runtime.execute` writes after locators are known (fail closed). **New** content ids are `ni:` digests; index keys accept CID **or** digest/hex. Locator map: `GET /ldp/registry/by-content/<digest>`.

| Need | Status |
| --- | --- |
| BOM → Order for `POST /cat/node/init` | Landed (`bom_cid` / unique `data_cid`; `order_cid` still bootstrap) |
| `data_cid` → BOM for `link*` | Landed (`bom_cid=` / `data_cid=` as alternatives to `cat_response`) |
| Intra-run `wasDerivedFrom` on `stageLineage` | Landed (signed envelope; not the registry) |
| `content_id` → HTTP locators | **Landed** (CAS `LocatorIndex` + `/ldp/registry/by-content/`) |
| Mesh federation of the index | Deferred |
| Downstream “who consumed me?” | Deferred (consumer-side only) |

Full contract, record shape, disk layout, and routes: [`BomRegistry.md`](BomRegistry.md).

### Remaining path

| Step | What | Address of record | Status |
| --- | --- | --- | --- |
| **2a** | CID + AddressStore; LDP/Solid envelope locators | **CID** (legacy) | Landed |
| **Registry (before 2b)** | BOM→Order, `data_cid`→BOM; `init` / `link*` via index | **CID / `ni:`** (index keys) | **Landed** (Node-local) |
| **CAS-over-HTTP (before 2b)** | Digest-keyed LDP/`ni:` store; locator index; Kubo = legacy CID read | **digest / `ni:`** | **Landed** |
| **Phase 2b (later)** | URI as address; CID/hashlink as proof only | **HTTP URI** | Deferred |

---

## W3C / web technologies that changed provenance

| Technology | Spec / reference | Provenance role | Before | Now |
| --- | --- | --- | --- | --- |
| **JSON-LD 1.1** | [W3C TR](https://www.w3.org/TR/json-ld11/) | Semantic shape of the BOM package | No | Yes |
| **PROV-O** | [W3C TR](https://www.w3.org/TR/prov-o/) | Explicit Agent / Activity / Entity edges | No | Yes for intra-run (attribution + `#executorRun` + `stageLineage` `wasDerivedFrom`); reverse `data_cid`→BOM via Node-local registry; mesh-federated registry still open |
| **DID Core** | [W3C TR](https://www.w3.org/TR/did-core/) | Decentralized agent identity framework | No | Yes (method below) |
| **did:key** | [W3C CCG](https://w3c-ccg.github.io/did-method-key/) | Node DID from Ed25519 public key | No | Yes |
| **Verifiable Credentials Data Model 2.0** | [W3C TR](https://www.w3.org/TR/vc-data-model-2.0/) | Framing for cryptographically verifiable claims (DI proofs on envelope) | No | Partial (DI proof on ExecutionBom; not a full VC issuance pipeline) |
| **Data Integrity** | [W3C TR](https://www.w3.org/TR/vc-data-integrity/) | Tamper-evident binding of agent + document | No | Yes |
| **EdDSA Cryptosuite (`eddsa-jcs-2022`)** | [W3C TR](https://www.w3.org/TR/vc-di-eddsa/) | Sign/verify cryptosuite used by CATs | No | Yes |
| **JSON Canonicalization Scheme (JCS)** | [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) | Deterministic JSON before hash/sign | No | Yes (`rfc8785` dep) |
| **Ed25519** | [RFC 8032](https://www.rfc-editor.org/rfc/rfc8032) | Node signing key algorithm | No | Yes (`cryptography`) |
| **Linked Data Platform (LDP)** | [W3C TR](https://www.w3.org/TR/ldp/) | Stable HTTP locator/cache for the provenance package; GET-only registry + CAS containers | No | Yes (`GET /ldp/boms/`, `GET /ldp/registry/`, `GET /ldp/cas/`; PUT → 405) |
| **Solid** | [Solid Project](https://solidproject.org/) / [Solid Protocol](https://solidproject.org/TR/protocol) | Open-world HTTP publish of envelopes | No | Optional (CSS-compatible); registry records are **not** dual-written |
| **Community Solid Server (CSS)** | [GitHub](https://github.com/CommunitySolidServer/CommunitySolidServer) | Reference Solid implementation CATs talks to (external) | No | Operator-run (not in Structure) |
| **WebID** | [W3C Incubator](https://www.w3.org/2005/Incubator/webid/spec/) | Solid agent identity bridged from `did:key` | No | Yes |
| **Web Access Control (WAC)** | [Solid WAC](https://solid.github.io/web-access-control-spec/) | ACL on BOM container (Write/Append/Read) | No | Yes (`ensure_solid_bom_acl`) |
| **Linked Data Notifications (LDN)** | [W3C TR](https://www.w3.org/TR/ldn/) | Announce new provenance packages to Inboxes | No | Best-effort when Solid set (not the query index) |
| **ActivityPub** | [W3C TR](https://www.w3.org/TR/activitypub/) | Richer HTTP federation (design option) | No | **Not** landed (LDN only) |
| **RDF Dataset Canonicalization (RDFC-1.0)** | [W3C TR](https://www.w3.org/TR/rdf-canon/) | Design-doc integrity option alongside DI | No | **Not** used yet (JCS path instead) |
| **Hashlink (`hl:`)** | [IETF draft / hashlink](https://datatracker.ietf.org/doc/html/draft-sporny-hashlink) | Design-doc CID analog for URI integrity | No | **Not** landed (`ni:` / digest used for CAS; `hl:` optional later / 2b) |
| **Named Information (`ni:`)** | [RFC 6920](https://www.rfc-editor.org/rfc/rfc6920) | Digest address of record for CAS-over-HTTP | No | Yes (`ni:///sha-256;<base64url>`; hex on disk) |

### Supporting (not provenance standards, but used after verify)

| Technology | Spec / reference | Role on mainline |
| --- | --- | --- |
| **IPFS / CID** | [Content addressing](https://docs.ipfs.tech/concepts/content-addressing/), [CIDs](https://docs.ipfs.tech/concepts/content-addressing/#identifier-formats) | Legacy address of record; registry keys for historical CIDs |
| **IPFS HTTP Gateway** | [Gateway API](https://docs.ipfs.tech/reference/http/gateway/) | Opt-in AddressStore reads for **legacy CIDs** (`IPFS_GATEWAY_URL`) |
| **Kubo** | [Kubo](https://docs.ipfs.tech/install/command-line/) | **Legacy CID** RPC/gateway reads + mid-migration ensure; **not** used for new CAS mints |
| **CAS-over-HTTP** | Node LDP `/ldp/cas/` | Digest-keyed put/get + sha256 verify; directory manifests |
| **Multibase** | [multibase](https://github.com/multiformats/multibase) | `did:key` / proofValue encoding helpers |

---

## Semantic mapping (design §4)

| Loop concept | PROV-ish role | Implementation on mainline |
| --- | --- | --- |
| Order | Plan / [`prov:Entity`](https://www.w3.org/TR/prov-o/#Entity) | Still CID on Invoice (`order_cid`); also `prov:used` by `#executorRun`; discovered via registry `lookup_order` |
| Executor run | [`prov:Activity`](https://www.w3.org/TR/prov-o/#Activity) | `#executorRun` on signed BOM (`prov:wasGeneratedBy`) |
| Invoice + stage CIDs | Generated entities / feedback | Minted on Invoice; mirrored as `stageLineage` `prov:Entity` + `wasDerivedFrom` |
| CAT Node | [`prov:Agent`](https://www.w3.org/TR/prov-o/#Agent) | `node_did` + proof `verificationMethod` |
| BOM | Signed provenance **package** | `build_execution_bom` + `sign_execution_bom`; published at LDP/Solid |
| Registry record | Query projection (not a PROV document) | `build_record` after `verify_execution_bom`; `GET /ldp/registry/…` |

---

## Implementation seams (provenance-only)

| Concern | Path | Change vs pre-merge `dev` |
| --- | --- | --- |
| Build envelope | `cats/network/feedback/envelope.py` | Structured LD/[PROV-O](https://www.w3.org/TR/prov-o/) BOM + `stageLineage` |
| Sign / verify | `cats/network/feedback/data_integrity.py` | [Data Integrity](https://www.w3.org/TR/vc-data-integrity/) [`eddsa-jcs-2022`](https://www.w3.org/TR/vc-di-eddsa/) |
| Agent keys | `cats/network/identity/node_did.py` | [did:key](https://w3c-ccg.github.io/did-method-key/) keyfile |
| WebID bridge | `cats/network/identity/webid.py` | [WebID](https://www.w3.org/2005/Incubator/webid/spec/) ↔ same VM |
| Local publish | `ldp/bom_store.py` + routes | [LDP](https://www.w3.org/TR/ldp/) persist + GET cache (`/ldp/boms/`) |
| BOM registry | `cats/network/registry/` | Node-local index (`data_cid`→BOM / BOM→Order); `GET /ldp/registry/…` — [`BomRegistry.md`](BomRegistry.md) |
| `init` intake | `cats/node/app.py` | `order_cid` \| `bom_cid` \| unique `data_cid` (ambiguous → 409) |
| `link*` | `cats/network/order.py` | `cat_response` **or** `bom_cid=` / `data_cid=` → `flatten_bom` |
| Fetch + verify | `ldp/client.py` | Fail-closed DI verify |
| Solid publish / ACL / LDN | `solid_client.py`, `wac.py`, `ldn.py` | [Solid](https://solidproject.org/) + [WAC](https://solid.github.io/web-access-control-spec/) + [LDN](https://www.w3.org/TR/ldn/) |
| Wire-up | `Runtime.execute` | Sign → `bom_cid` → LDP → optional Solid → **registry put** → LDN |

---

## See also

- [`BomRegistry.md`](BomRegistry.md) — Node-local query index (not the envelope store)
- [`SOLID.md`](SOLID.md) — Solid dual-write, WebID/WAC, LDN (`bom_solid_uri`)
- [`BOM.md`](BOM.md) — signed envelope, Invoice/Order CID nest, HTTP response
- [`ControlFeedbackLoop.md`](ControlFeedbackLoop.md) — Order-from-BOM intake
- [`LineageOfProvenance.md`](LineageOfProvenance.md) — CID chain + reverse lookup
- [`IPFS.md`](IPFS.md) / [`STORAGE.md`](STORAGE.md) — AddressStore / data plane (unchanged by this path)
