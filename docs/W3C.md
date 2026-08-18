# Comparative analysis (provenance-focused): `w3c` vs `dev`

Scope: **how provenance is modeled, attributed, signed, published, and discovered** — not Plant/MinIO/transport rewrites.

## One-line verdict (provenance)
* `dev:` provenance is mostly **implicit** [CID](https://docs.ipfs.tech/concepts/content-addressing/) **threading**.
* `w3c:` lineage is an **explicit,** [DID](https://www.w3.org/TR/did-core/)**-attributed**, [Data Integrity](https://www.w3.org/TR/vc-data-integrity/)**-signed** [JSON-LD](https://www.w3.org/TR/json-ld11/)/[PROV-O](https://www.w3.org/TR/prov-o/) **envelope**, published at [LDP](https://www.w3.org/TR/ldp/)/[Solid](https://solidproject.org/) **HTTP locators** peers can fetch and verify — while **CID remains the address of *provenance* record** for referenced stage products. Node-local **BOM registry** reverse lookup (`data_cid` → BOM) is landed; remaining gaps are mesh federation / locator indexes (CAS-over-HTTP) and Phase 2b URI-as-address, not signing.
## Envelope vs stage payloads (unchanged discipline)
Provenance package stays cheap:
* **In envelope:** Invoice/log CIDs, `node_did`, [PROV-O](https://www.w3.org/TR/prov-o/) edges, [Data Integrity](https://www.w3.org/TR/vc-data-integrity/) proof
* **Out of band:** Ray/MinIO bytes, directory DAGs — Invoice stage CIDs + `optional object_store_result_uri` / durable ER correlators
That split is the design doc’s core packaging rule: Control-Feedback **graph + proofs**, not inlined datasets.

---

## What “provenance” means in CATs

The Control-Feedback Loop’s provenance surface is:

1. **Order** (plan / as-Code Quantum) → [CID](https://docs.ipfs.tech/concepts/content-addressing/) graph  
2. **Executor run** (activity) → Invoice + stage CIDs  
3. **BOM** (HTTP / control-plane package) → points at Invoice + logs + agent  

Stage products (`ingress_data_cid`, `integration_data_cid`, `data_cid`, `structure_as_executed_cid`, `seed_cid`) stay **out of the envelope as bytes** — only addresses; `seed_cid` now resolves to a populated Process replay dictionary ([#187](https://github.com/DynamicalSystemsGroup/cats/issues/187)). See also [`LineageOfProvenance.md`](docs/LineageOfProvenance.md) and [`BOM.md`](docs/BOM.md).

---

## Provenance properties: `dev` / `w3c`

| Property | On `dev` | On `w3c` |
| --- | --- | --- |
| **Model** | Mostly **implicit** — CID equality between linked objects | **Explicit graph** — [JSON-LD](https://www.w3.org/TR/json-ld11/) + [PROV-O](https://www.w3.org/TR/prov-o/) on the ExecutionBom (`prov:wasAttributedTo`, `prov:wasGeneratedBy`) |
| **Who produced it** | Weak / Node HTTP lifecycle | **`node_did` ([did:key](https://w3c-ccg.github.io/did-method-key/))** as PROV agent; Flask bind is **not** attribution |
| **Tamper-evidence** | CID of unsigned (or ad-hoc) BOM JSON | CID of **signed** object + [Data Integrity](https://www.w3.org/TR/vc-data-integrity/) `proof` ([`eddsa-jcs-2022`](https://www.w3.org/TR/vc-di-eddsa/) / [RFC 8785 JCS](https://www.rfc-editor.org/rfc/rfc8785)) |
| **Envelope contents** | BOM fields in execute response | Address refs only: `invoice_cid`, `log_cid`, `node_did` + `@context` / `@type` + proof |
| **Publish / locator** | Response / Kubo only | + **`bom_ldp_uri`** ([LDP](https://www.w3.org/TR/ldp/) Node cache); optional **`bom_solid_uri`** ([Solid](https://solidproject.org/) dual-write) |
| **Peer verify path** | Trust fetch + CID | `fetch_bom_envelope` → **`verify_execution_bom`** (Node or Solid URL) |
| **Announce to mesh** | — | Best-effort [LDN](https://www.w3.org/TR/ldn/) Announce (`bom_cid`, `bom_solid_uri`) when Solid configured |
| **ACL on write** | N/A (no Solid) | Solid [WAC](https://solid.github.io/web-access-control-spec/) (Node Write; readers / public Read); Node LDP PUT stays **405** |
| **Backward “which BOM made this `data_cid`?”** | Gap ([`LineageOfProvenance.md`](docs/LineageOfProvenance.md)) | **Node-local registry** (`BomRegistry` / `GET /ldp/registry/by-data/…`); mesh federation still deferred (intra-run `wasDerivedFrom` also landed) |
| **Stage feedback** | Invoice stage CIDs | Same CID addresses on Invoice; signed BOM also carries `stageLineage` PROV entities (reachable after envelope verify via [AddressStore](docs/IPFS.md)) |
| **Large payloads** | [MinIO](https://min.io/) + IPFS CIDs | Same discipline — envelope never embeds stage bytes ([`STORAGE.md`](docs/STORAGE.md)) |

---

## W3C / web technologies that changed provenance

| Technology | Spec / reference | Provenance role | `dev` | `w3c` |
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
| **Linked Data Platform (LDP)** | [W3C TR](https://www.w3.org/TR/ldp/) | Stable HTTP locator/cache for the provenance package | No | Yes (`GET /ldp/boms/`) |
| **Solid** | [Solid Project](https://solidproject.org/) / [Solid Protocol](https://solidproject.org/TR/protocol) | Open-world HTTP publish of envelopes | No | Optional (CSS-compatible) |
| **Community Solid Server (CSS)** | [GitHub](https://github.com/CommunitySolidServer/CommunitySolidServer) | Reference Solid implementation CATs talks to (external) | No | Operator-run (not in Structure) |
| **WebID** | [W3C Incubator](https://www.w3.org/2005/Incubator/webid/spec/) | Solid agent identity bridged from `did:key` | No | Yes |
| **Web Access Control (WAC)** | [Solid WAC](https://solid.github.io/web-access-control-spec/) | ACL on BOM container (Write/Append/Read) | No | Yes (`ensure_solid_bom_acl`) |
| **Linked Data Notifications (LDN)** | [W3C TR](https://www.w3.org/TR/ldn/) | Announce new provenance packages to Inboxes | No | Best-effort when Solid set |
| **ActivityPub** | [W3C TR](https://www.w3.org/TR/activitypub/) | Richer HTTP federation (design option) | No | **Not** in PR (LDN only) |
| **RDF Dataset Canonicalization (RDFC-1.0)** | [W3C TR](https://www.w3.org/TR/rdf-canon/) | Design-doc integrity option alongside DI | No | **Not** used yet (JCS path instead) |
| **Hashlink (`hl:`)** | [IETF draft / hashlink](https://datatracker.ietf.org/doc/html/draft-sporny-hashlink) | Design-doc CID analog for URI integrity | No | **Not** in PR (CID retained) |

### Supporting (not provenance standards, but used after verify)

| Technology | Spec / reference | Role on `w3c` |
| --- | --- | --- |
| **IPFS / CID** | [Content addressing](https://docs.ipfs.tech/concepts/content-addressing/), [CIDs](https://docs.ipfs.tech/concepts/content-addressing/#identifier-formats) | Address of record for Invoice/log/stage products |
| **IPFS HTTP Gateway** | [Gateway API](https://docs.ipfs.tech/reference/http/gateway/) | Opt-in AddressStore reads (`IPFS_GATEWAY_URL`): `cat`, file `get`, directory CAR extract, CAR `dag_export` |
| **Kubo** | [Kubo](https://docs.ipfs.tech/install/command-line/) | Writes + RPC fallback; only-hash verify oracle for exotic layouts |
| **Multibase** | [multibase](https://github.com/multiformats/multibase) | `did:key` / proofValue encoding helpers |

Product docs: [`SOLID.md`](docs/SOLID.md), [`IPFS.md`](docs/IPFS.md), [`STORAGE.md`](docs/STORAGE.md).

---

## Semantic mapping (design §4)

| Loop concept | PROV-ish role | Implementation on `w3c` |
| --- | --- | --- |
| Order | Plan / [`prov:Entity`](https://www.w3.org/TR/prov-o/#Entity) | Still CID on Invoice (`order_cid`); also `prov:used` by `#executorRun` |
| Executor run | [`prov:Activity`](https://www.w3.org/TR/prov-o/#Activity) | `#executorRun` on signed BOM (`prov:wasGeneratedBy`) |
| Invoice + stage CIDs | Generated entities / feedback | Minted on Invoice; mirrored as `stageLineage` `prov:Entity` + `wasDerivedFrom` |
| CAT Node | [`prov:Agent`](https://www.w3.org/TR/prov-o/#Agent) | `node_did` + proof `verificationMethod` |
| BOM | Signed provenance **package** | `build_execution_bom` + `sign_execution_bom`; published at LDP/Solid |

---

## Implementation seams (provenance-only)

| Concern | Path | Change vs `dev` |
| --- | --- | --- |
| Build envelope | `cats/network/feedback/envelope.py` | Structured LD/[PROV-O](https://www.w3.org/TR/prov-o/) BOM |
| Sign / verify | `cats/network/feedback/data_integrity.py` | [Data Integrity](https://www.w3.org/TR/vc-data-integrity/) [`eddsa-jcs-2022`](https://www.w3.org/TR/vc-di-eddsa/) |
| Agent keys | `cats/network/identity/node_did.py` | [did:key](https://w3c-ccg.github.io/did-method-key/) keyfile |
| WebID bridge | `cats/network/identity/webid.py` | [WebID](https://www.w3.org/2005/Incubator/webid/spec/) ↔ same VM |
| Local publish | `ldp/bom_store.py` + routes | [LDP](https://www.w3.org/TR/ldp/) persist + GET cache |
| BOM registry | `cats/network/registry/` | Node-local index (`data_cid`→BOM / BOM→Order); `GET /ldp/registry/…` |
| Fetch + verify | `ldp/client.py` | Fail-closed DI verify |
| Solid publish / ACL / LDN | `solid_client.py`, `wac.py`, `ldn.py` | [Solid](https://solidproject.org/) + [WAC](https://solid.github.io/web-access-control-spec/) + [LDN](https://www.w3.org/TR/ldn/) |
| Wire-up | `Runtime.execute` | Sign → `bom_cid` → LDP → optional Solid → **registry put** → LDN |

---