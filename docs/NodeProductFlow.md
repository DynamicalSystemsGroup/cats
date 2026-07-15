# CAT Node's Product Control-Feedback Loop:

## Control-Feedback Loop Specification:

![CAT Node's Product Control-Feedback Loop](../images/NodeProductFlow.png)

```mermaid
%% post-render: flip-edge-arrow L_Order_InvoiceOrderCID_0
flowchart LR
    subgraph Order["Order (CID)"]
        InputInvoice[("Invoice (CID) [input]")]
        subgraph FunctionCID["Function (FaaS) CID"]
            ProcessFaaSCID["Process (FaaS)"]:::factory
            InfraFunctionFaaSCID["InfraFunction (FaaS)"]:::factory
        end
        subgraph StructureCID["Structure (PaaS) CID"]
            PlantSaaSCID["Plant (SaaS)"]:::factory
            InfraStructureIaaSCID["InfraStructure (IaaS)"]:::factory
        end
    end

    subgraph Node
        subgraph Factory["Factory"]
        end
        subgraph Executor["Executor"]
            subgraph Function["Function [FaaS]"]
                ProcessFaaS["Process (FaaS)"]:::factory
                InfraFunctionFaaS["InfraFunction (FaaS)"]:::factory
                ProcessFaaS -->|executesVia| InfraFunctionFaaS
            end
            subgraph Structure["Structure [PaaS]"]
                PlantSaaS["Plant (SaaS)"]:::factory
                InfraStructureIaaS["InfraStructure (IaaS)"]:::factory
                InfraStructureIaaS -->|deployedOn| PlantSaaS
            end
            InfraFunctionFaaS -->|orchestratesProcessingOn| PlantSaaS
            Function -->|executedOn| Structure
        end
    end

    subgraph BOM["BOM (CID)"]
        subgraph Invoice["Invoice (CID)"]
            InvoiceOrderCID[("Order (CID)")]
            DataCID[("Data (CID) [output]")]
            SeedCID[("Seed (CID) [dictionary]")]
        end
        ExecutorLog[("Executor Log (CID)")]
    end

    Order -->|"processedBy"| Factory
    Factory -->|"instantiates"| Executor
    InputInvoice -->|"transformedBy"| Executor
    Factory -->|"composes"| Function
    Factory -->|"constructs"| Structure
    Executor -->|"invoiceExecution"| Invoice
    Node -->|"deriveBOM"| BOM
    Order <-.-|"discoveredVia"| InvoiceOrderCID

    %% Invisible layout-only links carried over from
    %% local_artifacts/mermaid/github/NodeProductFlow.md to counteract the
    %% same dagre rank/ordering quirks in this experimental variant.
    InfraStructureIaaS ~~~ ProcessFaaS
    InfraFunctionFaaS ~~~ PlantSaaS
    InputInvoice ~~~ Executor
    SeedCID ~~~ ExecutorLog

    %% After reversing "deploys" to "deployedOn" (PlantSaaS -> InfraStructureIaaS),
    %% InfraStructureIaaS became the new rank "sink" (no outgoing edge) instead of
    %% PlantSaaS, so it's what now shares Invoice's rank/column and overlaps BOM.
    InfraStructureIaaS ~~~ InvoiceOrderCID

    classDef factory fill:#dbe9ff,stroke:#5b7fbd;
    classDef executor fill:#d9f2d9,stroke:#4c9a4c;
    classDef factoryActivity fill:#e8d9f5,stroke:#7a4ca6;
```

0. The "Architectural Quantum" is a Minimal Federated Operating Model that adheres to Domain-Driven Design 
   principles
1. The "Node" consumes an "Order" containing an input "Invoice" of input data to be processed as well as the 
   Architectural Quantum's functional domain components that process Invoiced data; The content of the Order CID to be processed by the Node's "Factory" consists of the following: (*)
   A. the CID-ed input Invoice as is within `data/input/data/*`
   B. the CID-ed Architectural Quantum's functional domain components:
      a. "Function [FaaS]" consists of "Process [FaaS]" and Process' "InfraFunction [FaaS]" processing dependency
         - Function [FaaS] (as Code) is CID-ed for which the contents consist of CIDs for Procces [FaaS] and   
           InfraFunction [FaaS]
      b. "Structure [PaaS]" is Function's infrastructure dependency and consists of "Plant [SaaS]" and Plant's 
         "InfraStructure [IaaS]" infrastructure dependency
         - Structure [PaaS] (as Code) is CID-ed for which the contents consist of Plant [SaaS] and InfraStructure 
           [IaaS] CIDs
2. The Node's "Factory" processes an Order to produce "Executor" of an Architectural Quantum by composing Function 
   [FaaS], constructing Structure [PaaS], then instantiating Executors with Function [FaaS] & Structure [PaaS] as its dependencies / parameters
3. The Executor is a composition of Architectural Quantum execution that executes and Invoices the ephemeral 
   execution of the Architectural Quantum.
      A. the Executor executes the aforemention composition as a Function [FaaS] executing on Structure [PaaS] via 
         InfraFunction [FaaS] orchestrating the execution of Process(es) [FaaS] on the Plant [SaaS] deployed on InfraStructure [IaaS]
      B. the Executor Invoices the ephemeral execution of the Architectural Quantum by prodcuing a CID-ed Invoice 
         containing the original CID-ed Order, an the CID-ed output Data, and a (non-deterministic proccessing) Seed (dictionary for Proccess(es) [FaaS])
4. The Node produces a CID-ed BOM containing an CID-ed Invoice and CID-ed Executor execution "logs" (*)

Notes (*):
    * 1. The Order is intended to be consumed from within a "BOM" hosted on a registry; i.e. - discovered via that BOM's "invoice.order_cid" - rather than supplied out-of-band; **this registry is not yet implemented**, such that the Node's `/cat/node/init` endpoint accepts the target `order_cid` directly as input today, standing in for the not-yet-built "look up a BOM on the registry, then consume its Order" step
    * 3 - CIDs of BOMs are intended to be published to the registry (0c) for future Orders to be consumed from