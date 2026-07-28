# CATs: Content-Addressable Transformers

## Description:

**CATs** is an edge-computing framework that establishs a *self-serviced* **[Data Mesh](https://www.datamesh-architecture.com/#what-is-data-mesh)** for inter and intra-orginizational Data Service Collaboration with *verifiable* **Data Provenance**. **CAT Nodes** are intended to be system *integration points* that enable **[Data Product](https://www.datamesh-architecture.com/#data-product)** collaborators to verify, retrieve, and re-execute **interoperable** data processing workload components intra and inter-orginizationally with Data Provenance via **BOMs**. *CAT Nodes* hetoerogeneously scale processing workload portability between client-server cloud platforms and mesh (p2p) networks with minimal rework or modification.

*CAT Node's* execute horizontal, vertical, and heterogenious scallable **Content-Addressable Transformers (CATs)**. **CATs** are ***content-addressed data processing (/ transformation)* workloads** inputed & outputted as *Data Provenance records* used to establishe a Data Mesh as a Platform. CATs reify a Data Mesh as Data Provenance records because the edge protocol mechanism used for the [Content-Addressed Storage (CAS)](https://en.wikipedia.org/wiki/Content-addressable_storage) of CATs as **[Bills-Of-Materials (BOMs)](https://en.wikipedia.org/wiki/Bill_of_materials)** is also the means of Data Transport that networks CAT Nodes as verifiable lineages of Data Provenance (* **[Details](docs/LineageOfProvenance.md)**).

### CAT's Domain-Driven Architecture as a *Control-Feedback Loop*:
![CATs Chaordic Kernel](images/CATs_chaordic_kernel.jpeg)
*CAT Node's* **Architectural Quantum (AQ)** is a [*Minimal* **Federated Operating Model (FOM)**](https://www.starburst.io/blog/data-mesh-book-bulletin-principle-of-federated-computational-governance/) as the re-executable and exchangable *atomic unit* representating the architectural domain of a Data Product. The AQ is content-addressed as a BOM containing the AQ's components such that organizations can collaborate on a Data Mesh with verifiable provenance of *interoperable AQ compoents*. CAT Node's runtime realization of the *minimal FOM / Quantum Architecture* is the **Ordering** of **Execution** is **Invoiced** into a **Bill-Of-Materials** as a **Control-Feedback Loop**.
* **Detailed** *Loop* [here](./docs/ControlFeedbackLoop.md)
* **Summarized** *Loop* below:
  * **A: Production** - CATs (*CAT workloads*) are **Ordered** and **Invoiced** for verification and registered as **[BOMs](docs/BOM.md)** to serve as **Data Provenance records** that uniquely identify CATs and their content for **verifiable data processing** using content-addresses. CATs are deployable as parallelized and distributed processes to support scalable data processing microservices.
    * **1.** the *Node's* **Factory** 
      * **a.** *consumes* & *processes* a content-addressed **Order**
      * **b.** *composes* and *produces* an *ephemeral* **Executor** of data processing using *AQ components* within **Order**
    * **2.** the *Node's* **Executor** 
      * **a.** *executes* the *AQ components* as **Function [FaaS]** on **Structure [PaaS]**
      * **b.** **Invoices** the *execution of data prcessing* as staged output **Content-Addresses**
  * **B: BOMs** - CAT Node's input & output surface that contain the means of data processing between Nodes. CAT Node produces **content-addressed** BOMS that certify the accuracy of data processing for services offered by *Data Products* by enabling maintenance and reporting of [data and process lineage & provenance](https://bi-insider.com/posts/data-lineage-and-data-provenance/) as *supply chains of evidence*. [**Content-Addressing**](docs/CAS.md) reffers **Content-Addressed Storage (CAS)**, which is a method of uniquely identifying and retrieving information based on its content rather than its location or address.
    * **3.** the **Node's Runtime** *emits* a **BOM** as the *Mesh-transportable Data Provenance record* to be *shared* & *re-executed* between Nodes 

## Demonstration: *CAT Workload Specification*
CAT Node is shipped with *Techncal Use-Case Processing Templates (/ "Recipies")* specified as *CAT **Orders*** for which proccess will be executed and **Invoiced**. This repository will feature a Scalable Scientific Computing application **Ordered** as a CATs. This **Order** is specified to utilize [Ray](https://www.ray.io/) as an execution middleware framework **Plant (SaaS)** deployed on **[Kubernetes](https://kubernetes.io/)** for interoperable & parallelized distributed computing applications / Big Data processing with Scientific Computing enabled [ecosystem integrations](https://docs.ray.io/en/latest/ray-overview/ray-libraries.html) such as [Apache Spark](https://spark.apache.org/), and [PyTorch](https://pytorch.org/).

## Get Started!:

1. **Clone CATs:**
  ```bash
    git clone git@github.com:DynamicalSystemsGroup/cats.git
    cd cats
    uv python install   # installs the Python version pinned in .python-version
    uv sync             # creates .venv and installs locked dependencies from uv.lock
  ```
  - See `[ENV.md](./docs/ENV.md)` for the full environment workflow, including the `ops` and `mac` extras.
2. **Install [Dependencies](./docs/DEPS.md)** (including [uv](https://docs.astral.sh/uv/), which manages
  CATs' Python interpreter, virtual environment, and locked dependencies)
  ```bash
  make deps-all
  # core: make deps
  # optional extras alone: make deps-helm / make deps-graphviz
  ```
  - Runs on macOS or Linux (see the `[Makefile](./Makefile)` and `make help`), or follow
  `[DEPS.md](./docs/DEPS.md)` to install each dependency manually.
3. **Start a CAT Node** (convenience: ensure host ContentStore, then bind Flask):
  ```bash
  make node-up
  # chains: make content-store-ensure && make node-start
  ```
  See `[STORAGE.md](./docs/STORAGE.md#node-up-vs-content-store-ensure-and-node-start)`
  for why ensure and start are separate Make targets.
4. **Check Node status** (Flask listen + ContentStore ready):
  ```bash
  make node-status
  # or: uv run python -m cats.node status
  ```
5. **Demo: [Establish a CAT Mesh](./docs/DEMO.md)**
6. **Test: [CAT Mesh Verification](./docs/TEST.md)**
7. **Stop the CAT Node** (Flask only — host Kubo stays up):
  ```bash
  make node-stop
  # or: uv run python -m cats.node stop

  # host IPFS (Kubo) daemon is left running on purpose
  # stop IPFS (Kubo) daemon via the following command:
  # ipfs shutdown
  ```
8. **Dashboards:**
  Once a Structure is deployed, three web dashboards are reachable at fixed `localhost` addresses: See [DASHBOARDS.md](docs/DASHBOARDS.md) for URLs, credentials, and each one's purpose.
  * [Ray Dashboard](http://127.0.0.1:8265) for the Plant's KubeRay cluster (job status, actors, logs)
  * [MinIO Console](http://127.0.0.1:9001) for the [S3-compatible](https://min.io/product/s3-compatibility) shared object store Ray Data's distributed writes land in (see `[STORAGE.md](docs/STORAGE.md)` / `[MinIO.md](docs/MinIO.md)`)
  * [IPFS WebUI](http://127.0.0.1:5001/webui) for browsing everything CID'ed into a BOM/Invoice/Order 
    * CID Nested BOM layout: [`docs/BOM.md`](docs/BOM.md#cat-node-http-bom-response)). 
9. **Auto-Diagramming Software Archtecture:**
  * Command(s): requires `Graphviz` for PNG output — `make deps-graphviz` (or `make deps-all`)
  ```bash
  make diagrams
  ```
  * Optional Commands / Utilities: 
    * `code2flow` used to generate *Functional Component Activity Diagram*: 
      * `uv run python utils/code2flow/diagram_c2f.py`
    * `pyreverse` used to generates *Class & Dependency Diagrams*: 
      * `uv run pyreverse -o png -p CATs -d images/pyreverse cats`
  

### [Contribute!](docs/CONTRIBUTING.md)

## Concepts:

### How are Content-Addressed BOMs used to establish and sustain Data Initiatives?
![CATs BOM Activity](images/CATs_bom_activity_ag.jpeg)
- **Collaboration:** The registration and cataloging of **BOMs** as *Data Provenance records* establishes and sustains **Data Initiatives** because CATs are *discoverable, accessible, composable, re-executable, and iteroperable* such that they support *Inter & Intra-Orginizational Collaboration* on **Data Products**. BOMs provide a reliable and efficient way to manage, share, and reference data processes because they are **[Content-Addressed](https://en.wikipedia.org/wiki/Content-addressable_storage)**. **Data Initiatives** will be naturally established as a result of collaboration on a CAT Node's *Data Product*. CATs will be compiled and executed as interconnecting *Data Products* on a Data Mesh that grow naturally / heterogeneously scales when organizations communicate CATs provenance records within feedback loops of their Data Initiatives.
- **Data Provenance:** The content-address of *BOMs* and their components can be used to verify the means of processing data (input, transformation / process, output, infrastructure-as-code (IaC)) they can also make CATs resilient by enabling re-execution via retrieval. They certify the accuracy of data processing on data products and pipelines by enabling maintenance and reporting of [data and process lineage & provenance](https://bi-insider.com/posts/data-lineage-and-data-provenance/) as *supply chains of evidence*.
- **Data Transport:** *BOMs* employ **Content Identifiers (CIDs)** for Content-Addesable Storage to provide a means of location-agnostic data transportation / retrieval based on its content / CAT processes for [Data Verification](https://en.wikipedia.org/wiki/Data_verification). Therefore, the implementation of CATs' as content-addressed data processes establishes and self-services a scalable Data Platform as a Data Mesh network of interoperable and scalable computing workloads deployable on [Kubernetes](https://kubernetes.io/) as CATs execution paradigm.

### CATs' Architectural Quantum:

Organizations and collaborators participating will employ CATs for rapid ratification of service agreements within collaborative feedback loops of **[Data Initiatives](https://github.com/DynamicalSystemsGroup/cats?tab=readme-ov-file#continuous-data-initiative)**. CATs' apply an **Architectural Quantum** Domain-Driven Design principle described in **[Data Mesh of Data Products](https://martinfowler.com/articles/data-mesh-principles.html)** to reify Data Initiatives.(* **[Design Description](docs/DESIGN.md)**)

The Action Plane is the Analytical Data Processing interface. The Action Plane orchestrates and supervises how virtual resources owned by the Data Product should be managed, routed, and processed and is stored “offmesh” (“offline”). It supervises the exchange of data between sub-Process components within the Data sub-Plane (Process) in adherence to Data Contracting Standards of organizations participating in a Data Mesh.
![CAT Kernel](images/CATkernel.jpeg)

#### Quantum Architecture Description as a [Minimal Federated Operating Model](https://www.starburst.io/blog/data-mesh-book-bulletin-principle-of-federated-computational-governance/)

- **Function [FaaS]** is a Function-as-a-Service for scalable Data Processing and analytics: **Process [Composed Function]** + **InfraFunction [Actuator]**, authored via the **REPLaC (REPL as Code) Workflow UI** of Function [FaaS] (this demo: Marimo, e.g. [`cats_demo.py`](cats_demo.py)). *Functions* are deployed on **Structure [PaaS]**; mutating either *Process* or *InfraFunction* updates the CAT **Order** in alignment with CATs *Architectural Quantum’s* Functionality
  - **Process [Composed Function]** is the composed callable graph (FaaS-composer analogue): **ingress / integration_cache / egress** (transport) plus `**integrated_subproc`** — the tHOF, i.e. the input→output data transform ([transfer function](https://en.wikipedia.org/wiki/Transfer_function)), often higher-order because it applies a batch function (e.g. via Ray `map_batches`). Process is the composition, not the notebook UI and not itself a tHOF. Mutating a ***Function's* Process [Composed Function]** produces a new **Order** whose `function_cid` reflects that update, for the Node's Factory to process on the next execution (*)
  - **InfraFunction [Actuator]** receives the tHOF **Process [Composed Function]** submits and dispatches it onto the Plant (SaaS); transport callables run locally around that dispatch, not as Plant jobs
    - Mutating InfraFunction [Actuator]'s dispatch configuration produces a new Order whose updated `function_cid` carries the updated actuator, alongside any Process-composed callable CIDs and any resulting `structure_cid` update reflecting the **Plant [SaaS]** it now targets (*)
- **Structure [PaaS(as IaC)]** provisions and maintains the **Plant [SaaS]** as **Function’s [FaaS]** scalable execution environment. 
  - **Plant [SaaS]** is composed from **InfraStructure [IaaS]** as **Structure's** dynamically scaled execution environment of 
  **Function [FaaS]** — the runtime onto which **InfraFunction [Actuator]** dispatches the tHOF (`integrated_subproc`) submitted by **Process [Composed Function]**
  - **InfraStructure (IaaS)** provisions and maintains the dynamically scaled infrastructure that composes a Plant (SaaS).
    - The CAT Order is updated in alignment with event-driven functionality and operations: mutating InfraStructure 
    (IaaS)'s provisioning produces a new Order with an updated `structure_cid` (*)

(* Each of these Order mutations produces the next Order a subsequent CAT execution processes - see 
**[NodeProductFlow.md](docs/NodeProductFlow.md)**, whose step 0 note documents how that next Order is (once the 
not-yet-built registry exists) meant to be discovered rather than supplied out-of-band.)

Each of these components is content-addressed and reconstituted at runtime with the same composition it was CID-ed with: the Factory consumes a single **Order CID** - resolving to Input Invoice, Function, and Structure CIDs - composes `Function` and constructs `Structure` from those CIDs, then instantiates a fresh, ephemeral **Executor** per CAT execution with them as its dependencies - `Structure` in turn composing its `Plant` from its `InfraStructure`, and `Function` its `Process` from its `InfraFunction` - and the Executor itself (not a layer above it) produces the resulting **Invoice CID**. 
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

### [Experiments](./experiments/EXP.md)

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
- **Lead Solutions Architect / Distributed Systems & Software Engineer** 
  - [Joshua E. Jodesty](https://github.com/JEJodesty)
- **Testing:** Danilo