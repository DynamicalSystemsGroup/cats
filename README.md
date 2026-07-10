# CATs: Content-Addressable Transformers

## Description:

**Content-Addressable Transformers** (**CATs**) is a unified Data Service Collaboration framework for organizations 
implemented as an edge-computing service that establish a Data Mesh as a scalable self-serviced Data Platform of 
Data Products with Data Provenance. CATs connect collaborators between organizations on a Data Mesh via the 
[Content-Addressed Storage (CAS)](https://en.wikipedia.org/wiki/Content-addressable_storage) of interoperable and scalable data processing to enable Data Provenance. CAT data processing workloads (CATs) are deployable as parallelized and distributed processes at horizontal & vertical scale to 
support scalable (big) data processing microservices with Scientific Computing capabilities. CATs are also integration 
points which enable scaled data processing portability between client-server cloud platforms and mesh (p2p) networks 
with minimal rework or modification.
![CATs Chaordic Kernel](images/CATs_chaordic_kernel.jpeg)
- **Techncal Use-Case Specification:** CATs' utilizes [Ray](https://www.ray.io/) as an execution middleware framework deployed on **[Kubernetes](https://kubernetes.io/)** for interoperable & parallelized distributed computing applications / Big Data processing with Scientific Computing enabled [ecosystem integrations](https://docs.ray.io/en/latest/ray-overview/ray-libraries.html) such as [Apache Spark](https://spark.apache.org/), and [PyTorch](https://pytorch.org/).

### How are CATs workloads processed as Data Provenance Records?

CAT's (Data) Mesh is specified / reified by CATs executing **[Bills-Of-Materials (BOMs)](https://en.wikipedia.org/wiki/Bill_of_materials)** as specifications used to chain CAT Nodes' content-addressed records into a verifiable lineage of Data Provenance. (* **[Details](docs/LineageOfProvenance.md)**)

CATs are submitted as content-addressed **Orders** of data processes (transformers) which are **Invoiced** for verification and logged as **BOMs** that serve as **Data Provenance records** that are unique identifiers of CAT workloads and their content. **BOMs** are CATs' Content-Addressed **Data Provenance records** for **verifiable data processing** with URIs for transport over a Mesh network of CATs. BOMs are also used as CAT’ input & output that contain CATs’ means of data processing between CAT Nodes.

**BOMs** employ **Content Identifiers (CIDs)** for CAS to provide a means of location-agnostic data transportation / retrieval of based on its content / CAT processes for [Data Verification](https://en.wikipedia.org/wiki/Data_verification). Therefore, the implementation of CATs' as content-addressed data processes establishes and self-services a scalable Data Platform as a Data Mesh network of interoperable distributed computing workloads deployable on [Kubernetes](https://kubernetes.io/) as CATs execution paradigm.
![CATs BOM Activity](images/CATs_bom_activity.jpeg)
- BOM CIDs can be used to verify the means of processing data (input, transformation / process, output, infrastructure-as-code (IaC)) they can also make CATs resilient by enabling re-execution via retrieval. CATs certifies the accuracy of data processing on data products and pipelines by enabling maintenance and reporting of [data and process lineage & provenance](https://bi-insider.com/posts/data-lineage-and-data-provenance/) as chains of 
evidence using CIDs.

### How do CATs enable colaborative Data Processing for Data Initiatives?

CATs enables the **[continuous reification of Data Initiatives](https://github.com/DynamicalSystemsGroup/cats?tab=readme-ov-file#continuous-data-initiative-reification)** by cataloging discoverable, accessible, and re-executable workloads as **[Data Service Collaboration](https://github.com/DynamicalSystemsGroup/cats?tab=readme-ov-file#continuous-data-initiative-reification)** composable records between organizations. These records provide a reliable and efficient way to manage, share, and reference data processes via **[Content-Addressing](https://en.wikipedia.org/wiki/Content-addressable_storage)** Data Provenance records. **Data Initiatives** will be naturally reified as a result of **Data Service Collaboration** on CATs. CATs will be compiled and executed as interconnecting services on a Data Mesh that grows naturally when organizations communicate CATs provenance records within feedback loops of Data Initiatives.
![CATs Initiative Aligmment](images/CATs_bom_ag.jpeg)

### What is Content Addressing & How does CATs use it?

**Content-Addressing** is a method of uniquely identifying and retrieving data based on its content rather than its 
location or address. CATs provides verifiable data processing and transport on a Mesh network of CATs interconnected by 
Content-Addressing Data Provenance records with [IPFS](https://ipfs.io/) **[CIDs](https://docs.ipfs.io/concepts/content-addressing/)** (Content-Identifiers) as content addresses issued by IPFS **[client](https://docs.ipfs.io/install/command-line/#official-distributions)** to identify and retrieve inputs, transformations, outputs, and infrastructure (as code [IaC]) for verifying transformation accuracy given CIDs.
![CID Example](images/cid_example.jpeg)
- IPFS serves as CATs' Data Mesh's network layer to provide parallelized data ingress and egress for IPFS data. This network portability closes the gap between data analysis and operations by connecting the network planes of the cloud service model (SaaS, PaaS, IaaS) with IPFS. CATs connect these network planes by enabling the instantiation of FaaS with cloud services in AWS, GCP, Azure, etc. on a **Data Mesh** network of CATs. IPFS enables this connection as p2p distributed-computing job submission in addition to the client-server job submission provided by Ray.

## Get Started!:

1. **Install [Dependencies](./docs/DEPS.md)** (including [uv](https://docs.astral.sh/uv/), which manages
  CATs' Python interpreter, virtual environment, and locked dependencies)
  - Run `make deps` to install everything automatically on macOS or Linux (see the [`Makefile`](./Makefile) and
    `make help`), or follow [`DEPS.md`](./docs/DEPS.md) to install each dependency manually.
2. **Install CATs:**
  ```bash
    git clone git@github.com:DynamicalSystemsGroup/cats.git
    cd cats
    uv python install   # installs the Python version pinned in .python-version
    uv sync             # creates .venv and installs locked dependencies from uv.lock
  ```
  - See `[ENV.md](./docs/ENV.md)` for the full environment workflow, including the `ops` and `mac` extras.
3. **Demo: [Establish a CAT Mesh](./docs/DEMO.md)**
4. **Test: [CAT Mesh Verification](./docs/TEST.md)**
5. **[Experiments](./experiments/EXP.md)**

### [Dashboards:](docs/DASHBOARDS.md)

Once a Structure is deployed, three web dashboards are reachable at fixed `localhost` addresses: the
[Ray Dashboard](http://127.0.0.1:8265) for the Plant's KubeRay cluster (job status, actors, logs), the
[MinIO Console](http://127.0.0.1:9001) for the shared object store Ray Data's distributed writes land in,
and the [IPFS WebUI](http://127.0.0.1:5001/webui) for browsing everything CID'ed into a BOM/Invoice/Order.
See [`DASHBOARDS.md`](docs/DASHBOARDS.md) for URLs, credentials, and what each one is for.

### [Contribute!](docs/CONTRIBUTING.md)

### CATs' Architectural Quantum:

Organizations and collaborators participating will employ CATs for rapid ratification of service agreements within collaborative feedback loops of **[Data Initiatives](https://github.com/DynamicalSystemsGroup/cats?tab=readme-ov-file#continuous-data-initiative)**. CATs' apply an **Architectural Quantum** Domain-Driven Design principle described in **[Data Mesh of Data Products](https://martinfowler.com/articles/data-mesh-principles.html)** to reify Data Initiatives.(* **[Design Description](docs/DESIGN.md)**)

The Action Plane is the Analytical Data Processing interface. The Action Plane orchestrates and supervises how virtual resources owned by the Data Product should be managed, routed, and processed and is stored “offmesh” (“offline”). It supervises the exchange of data between sub-Process components within the Data sub-Plane (Process) in adherence to Data Contracting Standards of organizations participating in a Data Mesh.
![CAT Kernel](images/CATkernel.jpeg)

#### Quantum Architecture Description as a [Minimal Federated Operating Model](https://www.starburst.io/blog/data-mesh-book-bulletin-principle-of-federated-computational-governance/)

- **Function** is a FaaS for scalable Data Processing and analytics executed as CAT **Processes**. Functions (FaaS) are deployed 
on Structure (PaaS) to execute Processes orchestrated by InfraFunctions (FaaS) 
  - **Process (FaaS)** is composed of the **Functional Data Processors** that InfraFunction (FaaS) executes on Structure (PaaS), and 
  contextualizes with pre and post processed data. Process (FaaS) is executed with and made 
  orchestratable by InfraFunction (FaaS) to support the following use-cases
    - The CAT Order is updated with the inclusion of resulting mutated Functions (FaaS) for execution processed by CATs 
    Factory Client.
  - **InfraFunction (FaaS) is a Data Processing orchestrator** that composes Process and dispatches its 
  configurable execution onto the Plant (SaaS)
    - The CAT Order is updated in alignment CATs Architectural Quantum’s Functionality. This Order will include the 
    resulting updated of Structure (PaaS) with respect to the updated Plant (SaaS) and an updated Function (FaaS) with 
    updated Ingress and Egress subProcesses (FaaS)
- **Structure** (**PaaS** as **IaC**) provisions and maintains the Plant (SaaS) as Function’s (FaaS) scalable execution environment. 
  - **Plant (SaaS)** is composed from **InfraStructure (IaaS)** as Structure's dynamically scaled execution environment of 
  **Function (FaaS)**
    - The web application codebase is Content Addressed within CAT Orders as Data Contract metadata for Order registration.
  - **InfraStructure (IaaS)** provisions and maintains the dynamically scaled infrastructure that composes a Plant (SaaS).
    - The CAT Order is updated in alignment with event-driven functionality and operations with the resulting mutation 
    of Structure (PaaS).

Each of these components is content-addressed and reconstituted at runtime with the same composition it was CID-ed with: the 
Factory consumes a single **Order CID** - resolving to Input Invoice, Function, and Structure CIDs - to produce a fresh, 
ephemeral **Executor** per CAT execution, which composes Structure's Plant from its InfraStructure and Function's Process 
from its InfraFunction, and itself (not a layer above it) produces the resulting **Invoice CID**. 
(* **[Quantum-as-CIDs details](docs/DESIGN.md#how-the-architectural-quantum-is-realized-as-content-addressed-cids)**)

### CAT Mesh: CATs Data Mesh platform with Data Provenance

**CAT Mesh** is a self-serviced Data Mesh platform with Data Provenance. **CAT Nodes** are CAT Mesh peers that enable workloads to be portable between client-server cloud platforms and p2p mesh network with minimal rework or modification.

Multi-disciplinary and cross-functional teams can use CAT Nodes to verify and scale distributed computing workloads. Workloads (CATs) executed by CAT Nodes interface cloud service model (SaaS, PaaS, IaaS) offered by providers such as AWS, GCP, Azure, etc. on a Mesh Network interconnected by IPFS. 

CAT Nodes are **Data Products** - peer-nodes on a mesh network that encapsulate components (*) to function as a service providing access to a domain's analytical data as a product; * code, data & metadata, and infrastructure.

**In the following image:** 

- Large ovals in the image above represent **Data Products** servicing each other with Data
- "O" ovals are Operational Data web service endpoints
- "D" ovals are Analytical Data web service endpoints
- Source: [Data Mesh Principles and Logical Architecture](https://martinfowler.com/articles/data-mesh-principles.html) - Zhamak 
Dehghani, et al.
![Data Product Domain](images/data_product_domain.jpeg)

## Key Concepts:

- **[Data Verification](https://en.wikipedia.org/wiki/Data_verification)** - a process for which data is checked for 
accuracy and inconsistencies before processed
- **[Data Provenance](https://bi-insider.com/posts/data-lineage-and-data-provenance/)** - a means of proving data 
lineage using historical records that provide the means 
of pipeline re-execution and **[data validation](https://en.wikipedia.org/wiki/Data_validation)**
- **[Data Lineage](https://bi-insider.com/posts/data-lineage-and-data-provenance/)** - reporting of data lifecyle from 
source to destination
- **[Distributed Computing](https://en.wikipedia.org/wiki/Distributed_computing)** - typically the concurrent and/or 
parallel execution of job tasks distributed to networked computers processing data
- **[Bill of Materials (BOM)](https://en.wikipedia.org/wiki/Bill_of_materials)** - an extensive list of raw materials,
components, and instructions required to construct, manufacture, or repair a product or service

### Image Citations:

- **["Illustrated CAT"](https://github.com/DynamicalSystemsGroup/cats#illustrated-cat)**
  - [Python logo](https://tse4.mm.bing.net/th?id=OIP.ubux1yLT726_fVc3A7WSXgHaHa&pid=Api)
  - [SQL logo](https://cdn3.iconfinder.com/data/icons/dompicon-glyph-file-format-2/256/file-sql-format-type-128.png)
  - [Terraform logo](https://tse2.mm.bing.net/th?id=OIP.1gAEVon2RF5oko4iWCfftgHaHO&pid=Api)
  - [IPFS logo](https://tse1.mm.bing.net/th?id=OIP.BRyW5Tdm5_6VQxCsGr_sQAHaHa&pid=Api)
  - [cat image](https://tse1.mm.bing.net/th?id=OIP.xS_itpeyTImMcrcQ_YNsfQHaIu&pid=Api)
  - [ray.io logo](https://open-datastudio.io/_images/ray-logo.png)

## Acknowledgments

CATs was developed by the [Dynamical Systems Group (DSG)](https://github.com/DynamicalSystemsGroup) team.

**Key contributions:**

- **Network Architecture & Verified Information Exchange:** 
  - [Michael Zargham (mzargham)](https://github.com/mzargham) 
  - [David Sisson](https://github.com/davidfsol5)
- **Lead Solutions Architect & Developer / Distributed Systems Engineer** 
  - [Joshua E. Jodesty](https://github.com/JEJodesty)
- **Testing:** Danilo