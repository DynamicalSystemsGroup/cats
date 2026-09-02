### What is Content-Addressing & How do CATs use it?

**Content-Addressing** refers to [Content-Addressed Storage (CAS)](https://en.wikipedia.org/wiki/Content-addressable_storage): uniquely identifying information by its **content**, then retrieving it. CATs use that on a Mesh of Nodes that exchange Data Provenance records (BOMs).

Live Orders split identity and location:

- **Equality** is **`ni:`** (RFC 6920 digest / envelope `contentId` / registry hash keys) — not URL-string equality.
- **Retrieval** is **CAS-over-HTTP**: HTTP **`*_uri`** locators (`GET /ldp/cas/<hex>`, Invoice/Order/BOM LDP URIs). Mesh `cat` / AddressStore resolve `ni:` / `hl:` / `http(s)` and sha256-verify. See [`STORAGE.md`](STORAGE.md) / [`IPFS.md`](IPFS.md) / [`BOM.md`](BOM.md).

Host Kubo is **optional** operator tooling. Legacy IPFS **[CIDs](https://docs.ipfs.io/concepts/content-addressing/)** (`Qm…` / `bafy…`) **fail closed** on the hot path — remint to `ni:` / HTTP.

![Content-address example](images/cid_example.jpeg)

- CAT Nodes connect XaaS planes (Function [FaaS] on Structure [PaaS]) as a **Data Mesh**. Transport of Quantum blobs is Node CAS-over-HTTP; Plant job submission in this demo is Ray (client-server). Optional Kubo does not replace CAS as the address of record.
