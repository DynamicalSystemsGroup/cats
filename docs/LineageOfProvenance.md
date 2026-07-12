# CAT Composition Lineage as Data Provenance Records

![CAT Lineage](../images/CATs_bom_connect.jpeg)

## How are CATs composed as a Lineage of Data Provenance on a Data Mesh?

Because every BOM is Content-Addressed using **[Content Identifiers (CIDs)](https://docs.ipfs.io/concepts/content-addressing/)**, each CAT's output `data_cid` is the exact same content the next CAT's input Invoice references (\*). As CATs execute across a **CAT Mesh**, this chains individual CATs' data together into a verifiable, traceable record of how data moved and was transformed from one CAT to the next—composing the Mesh's **[data and process lineage & provenance](https://bi-insider.com/posts/data-lineage-and-data-provenance/)**.

This composition gives the Mesh three properties:

- **Verifiability** — CIDs can be used to verify the means of processing data (input, transformation/process, output, and infrastructure-as-code (IaC)) at every link in the chain, enabling [Data Verification](https://en.wikipedia.org/wiki/Data_verification).
- **Resilience** — because each link is retrievable by its CID, any CAT in the lineage can be re-executed from its recorded BOM, making the Mesh resilient to node loss or replay needs.
- **Auditability** — the resulting chain of evidence lets CAT Mesh participants prove [Data Lineage](https://bi-insider.com/posts/data-lineage-and-data-provenance/) end-to-end, from a Data Product's source inputs to its final outputs, across organizational boundaries.

Notes (\*):
* This chains by carrying forward each CAT's output `data_cid` content - not a stored `bom_cid`/`order_cid` backward-pointer from the new BOM to the one before it. A BOM's own `bom_cid` is never written into any IPFS-addressed content it produces (it's only ever returned transiently in the Node's HTTP response), so recovering *which* BOM produced a given `data_cid` - the "upstream" link - currently depends on whoever calls `linkProcess()` already holding that prior response themselves, standing in for the not-yet-built registry (see [`NodeProductFlow.md`](NodeProductFlow.md)'s note on the same gap). A "downstream" pointer is deferred further still: no BOM can know at creation time who will later consume its output, so that link is only ever discoverable from the consuming CAT's side, going forward.

## Where this fits in CATs:

- CATs are compiled and executed as interconnecting services on a **Data Mesh** that grows as organizations communicate CAT provenance records within feedback loops of **[Data Initiatives](https://github.com/DynamicalSystemsGroup/cats?tab=readme-ov-file#continuous-data-initiative-reification)**.
- **CAT Nodes**—the peers that make up the CAT Mesh—are **Data Products** that encapsulate code, data & metadata, and infrastructure, and are portable between client-server cloud platforms and p2p mesh networks with minimal rework.
- The lineage chain composed by BOMs is what allows a **CAT Order** to be updated and re-verified as its constituent Functions (FaaS), Structure (PaaS), and Infrastructure (IaaS) mutate over the CAT's lifecycle (see the [Architectural Quantum](../README.md#cats-architectural-quantum) description in the README).

See also: [README: How are CATs workloads processed as Data Provenance Records?](../README.md#how-are-cats-workloads-processed-as-data-provenance-records) and [CAT Mesh: CATs Data Mesh platform with Data Provenance](../README.md#cat-mesh-cats-data-mesh-platform-with-data-provenance).

## What's inside a BOM's CIDs

See **[`BOM.md`](BOM.md)** for exactly what each of an Order's and BOM's CIDs resolves to: how `order.function_cid`/`order.structure_cid` nest their Process/InfraFunction and Plant/InfraStructure pairs (with concrete example payloads pulled live from IPFS), and how the output-side `bom.plant_snapshot_cid`/`bom.infrastructure_snapshot_cid` differ from those input-side, specified-as-code CIDs.
