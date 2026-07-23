# CAT Node Archtectural Components:

* the Factory:
    * Software Diambiguation: https://en.wikipedia.org/wiki/Software_factory 
    * Manafacturing Diambiguation: https://en.wikipedia.org/wiki/Factory 
    * Manufacturing cell for the Node as Data Product: `accept(Order)` stages materials → `assemble()` Function+Structure → `produce()` ephemeral Executor. `Service.initFactory` is the platform façade that delegates to Factory; Service does not own manufacturing logic.
* the Architectural Quantum: [Minimal Federated Operating Model](https://www.starburst.io/blog/data-mesh-book-bulletin-principle-of-federated-computational-governance/)
* the (ephemeral) Executor of the Architectural Quantum:
    * defenitions of the nested Architectural Quantum's Components (https://github.com/DynamicalSystemsGroup/cats#quantum-architecture-description-as-a-minimal-federated-operating-model)
    * Node Product Flow using an Executor to execute the Architectural Quantum: docs/NodeProductFlow.md
