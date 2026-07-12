### CAT Node's Architectural Quantum (Domain-Driven Design principle):

CAT Node uses the Architectural Quantum Domain-Driven Design principle described in 
[**Data Mesh of Data Products**](https://martinfowler.com/articles/data-mesh-principles.html)

This design principle enables effective cross-domain collaboration on Data Products across business and 
knowledge domains between cross-functional & multi-disciplinary teams and organizations.

![alt_text](../images/CATkernel.jpeg)

CAT’s architectural design and implementation are the result of applied Engineering, Computer Science, Network Science, 
and Social Science. CATs is software executing on a network client ontological to an MicroKernel Operating System. CATs’ 
is designed to enable Data Products implemented as compute node peers on a Data Mesh network that encapsulate code, 
data, metadata, and infrastructure to function as a service providing access to the business domain's analytical data as 
a product. Data Products use the Architectural Quantum domain-driven design principle for peer nodes that represent the 
“smallest unit of architecture that can be independently deployed with high functional cohesion, and includes all the 
structural elements required for its function” 
([“Data Mesh Principles and Logical Architecture”](https://martinfowler.com/articles/data-mesh-principles.html#:~:text=smallest%20unit%20of%20architecture%20that%20can%20be%20independently%20deployed%20with%20high%20functional%20cohesion%2C%20and%20includes%20all%20the%20structural%20elements%20required%20for%20its%20function.) - Zhamak Dehghani, et al.).

### How the Architectural Quantum is realized as content-addressed CIDs:

The Quantum's "smallest unit of architecture... with high functional cohesion" is realized concretely as a single content-addressed **Order CID**, consumed by the **Factory** to produce a fresh, ephemeral **Executor** per CAT execution - the Quantum's independently-deployable unit, instantiated anew for every Order rather than kept as standing infrastructure:

- `order_cid` resolves to `{invoice_cid, function_cid, structure_cid}` - the Order's Input Invoice, Function (as Code), and Structure (as Code), each independently content-addressed.
- `structure_cid` resolves to `{plant_cid, infrastructure_cid}` - Structure (**PaaS** as **IaC**) is CID-ed as the pairing of the Plant (SaaS) it provisions and the InfraStructure (IaaS) that provisions it.
- `function_cid` resolves to `{process_cid, infrafunction_cid}` - Function (FaaS) is CID-ed as the pairing of the Process (FaaS) it executes and the InfraFunction (FaaS) that orchestrates it.

The **Factory** reconstitutes this Quantum at runtime with the same composition it was CID-ed with: it composes `Function` and constructs `Structure` from the Order's `function_cid`/`structure_cid`, then instantiates the **Executor** with them as its dependencies. Each in turn composes its own CID-ed sub-component the same way - `Structure` composes its `Plant` from its `InfraStructure`, and `Function` composes its `Processor` from its `InfraFunction` - so Function (FaaS) executes on Structure (PaaS) by InfraFunction (FaaS) orchestrating Plant (SaaS), exactly as the Quantum's applied disciplines describe below. The Executor itself - not a layer above it - is what produces the resulting **Invoice CID**, so the whole Order-in/Invoice-out cycle stays within the one independently-deployable, functionally-cohesive unit the Quantum principle calls for. (* **[CID-level details](BOM.md)**, * **[Lineage-of-Provenance context](LineageOfProvenance.md)**)

### Collaborative value of CATs Architectural Quantum:
The operation and maintenance of CATs’ Data Products on a Data Mesh can occur between independent teams that will 
operate, contribute, and maintain different portions of the entire cloud-service model in adherence to CATs' 
Architectural Quantum in a way suitable for their roles using the CATs’ API to serve individual Data Model entities on a 
Data Mesh for a variety of use-cases. CAT’s Data Product teams can be multidisciplinary due to the fact they can operate 
and maintain the different portions of the entire Web2 cloud service model based on role.

### Data Product Team Example:
* Applied discipline for **Functions (FaaS)**
  * **Data Science** involves exploratory data analysis (EDA), data cleaning and visualization, and 
  predictive modeling / machine learning to inform Control Plane decisions and strategies. 
  * **Machine Learning Engineering** involves the development, training, performance optimizing, and deployment of machine 
  learning models as scalable **Integration** sub-Processes (FaaS) orchestrated by InfraFunction (FaaS). 
  * **Data Analysis** involves the composition of Data Product’s InfraFunctions as data processing language (integration).
  * The CAT Order is updated with the inclusion of resulting mutated Functions (FaaS) for execution processed by CATs 
  Factory Client.
* Applied discipline for **Structure (PaaS** as **IaC)**
  * **Data Platform / Cloud / Infrastructure Engineering** involves the design and IaC development, and automation of the 
  provisioning and management of Structure (PaaS) executing Function. This is accomplished using IaC to provision 
  InfraStructure (IaaS) as the execution paradigm of the Plant (SaaS) as well as contributing to InfraFunctions’ 
  (FaaS) execution configurations of Plant (SaaS) operations.

### [**Orginizational Value**](./ORG.md)