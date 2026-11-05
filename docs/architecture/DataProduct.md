# Data Product

A **Data Product** is a **CAT Node** on a [Data Mesh](https://www.datamesh-architecture.com/#what-is-data-mesh): the mesh peer that serves one domain’s analytical data. The domain is a [bounded context](https://martinfowler.com/articles/data-monolith-to-mesh.html#DataAndDistributedDomainDrivenArchitectureConvergence). The cross-functional team that owns the context owns one or more [Architectural Quanta](https://martinfowler.com/articles/data-mesh-principles.html#LogicalArchitecturedataProductTheArchitecturalQuantum) of that Node.

The product other nodes consume is that analytical data, together with the evidence of how it was produced. The quantum is how the Node carries the code, the infrastructure, and the data as one deployable unit.

## Data mesh

CAT uses the data-product architecture in [Data Mesh Principles and Logical Architecture](https://martinfowler.com/articles/data-mesh-principles.html) (Zhamak Dehghani et al.).

A data product gives the rest of the mesh access to a domain’s analytical data. Dehghani’s architectural quantum is the smallest unit of that product that can be deployed on its own, with high functional cohesion, including every structural element its function needs: code, data and metadata, and infrastructure. Processing stays inside the quantum. The ownership boundary is the data the product serves.

On a CAT mesh those products are peers. They service each other and end users. Federated governance is the shared bargain; each product team owns its quantum. The organizational reading of that bargain is [ORG.md](ORG.md).

## The Node

A CAT Node is the mesh-peer implementation of one Data Product. It is the integration point where other organizations verify, retrieve, and re-execute interoperable workloads. The Node stays up across many jobs. Each job is one pass of the [Control-Feedback Loop](ControlFeedbackLoop.md): an Order is executed, invoiced, and published as a Bill of Materials.

Two planes carry that work, as the [README](../../README.md) describes them:

- The **Action Plane** is the management interface. It supervises how the product’s resources are routed and processed, under the service-level agreements between organizations. Bills of Materials are catalogued here. It is stored off the mesh.
- The **Data Plane** orders, executes, invoices, and transports the workloads between Nodes, under the operational-level agreements. It is stored on the mesh.

## The Architectural Quantum

The quantum is the Data Product’s deployable unit. [DESIGN.md](DESIGN.md) is the component tree. The two content-addressed halves are:

- **Function** — the code. Process (the composed transform and its transport ports) and InfraFunction (the actuator that dispatches that transform).
- **Structure** — the infrastructure. Plant (the execution environment) and InfraStructure (the infrastructure that provisions the Plant).

The data travels with them. An **Order** binds one input Invoice, one Function, and one Structure (`invoice_uri`, `function_uri`, `structure_uri`). Equality is `ni:`. Fetch is HTTP `*_uri`. The same ids reconstitute the same composition.

The quantum’s output is the **Invoice**. Its `data_uri` is the analytical data this run serves. Stage locators (`data_stages_uri` and the ingress, integrated, and egress ids under it) and the Seed are the metadata of that run. A collaborator’s next Order may take this `data_uri` as its input. That equality — the next product’s input bytes are this product’s output bytes — is data served as a product across the mesh.

## What is published

The Node’s **Runtime** signs an **ExecutionBom** around the Invoice. The BOM is the supply chain of evidence: input, the Function and Structure that ran, the output `data_uri`, and the infrastructure as executed. Another Node verifies, retrieves, and re-executes from those locators. The Node-local registry indexes the envelope so the next Order is discovered by `content_id`, `data_uri`, or `bom_ldp_uri`.

Contracts for those records: [BOM.md](../provenance/BOM.md), [BomRegistry.md](../provenance/BomRegistry.md), [LineageOfProvenance.md](../provenance/LineageOfProvenance.md).

## One execution

The Node’s manufacturing cell takes one closed Order and produces one **ephemeral Executor**: Function composed on Structure for that Order. The Executor runs that composition, writes the Invoice, and is gone when the run is done. The Data Product does not end with it. The Node remains, and the signed BOM is what the mesh keeps.

Component boundaries for that cell and the Executor are in [COMPONENTS.md](COMPONENTS.md). The loop from Order to signed BOM is in [ControlFeedbackLoop.md](ControlFeedbackLoop.md).
