# CAT Node Archtectural Components:

* the Runtime:
    * Process-lifetime Node ambient (`cats/runtime`, singleton `RUNTIME`): host layout, ContentMesh, Order entry (`initFactory` / `initBOMcar`) and BOM envelope wrap (`execute`). Not the peer edge (`cats.node`), not the Assembler, not the per-Order Executor. After execute, a Node-local **BOM registry** (`BomRegistry`) indexes the verified envelope so the next Order is discovered via `content_id` / `data_uri` / `bom_ldp_uri` — [`BomRegistry.md`](../provenance/BomRegistry.md).
* the CAT Assembler (`cats.assembler`):
    * Manufacturing cell for the Node as Data Product: `accept(Order)` stages materials → `assemble()` Function+Structure → `produce()` ephemeral Executor. This cell is not a [software factory](https://en.wikipedia.org/wiki/Software_factory).
* the CAT Factory (`cats.factory`):
    * The agent line that operates the Assembler. `Composition` and `Release` are named stations and do no work on the accept path. `Factory.accept` calls `Assembler.accept`. `Factory.produce` returns that Assembler's Executor. `Runtime.initFactory` returns this Factory; Runtime does not own manufacturing logic.
* the Architectural Quantum: [Minimal Federated Operating Model](https://www.starburst.io/blog/data-mesh-book-bulletin-principle-of-federated-computational-governance/)
* the (ephemeral) Executor of the Architectural Quantum:
    * defenitions of the nested Architectural Quantum's Components (https://github.com/DynamicalSystemsGroup/cats#quantum-architecture-description-as-a-minimal-federated-operating-model)
    * Control-Feedback Loop using an Executor to execute the Architectural Quantum: [ControlFeedbackLoop.md](ControlFeedbackLoop.md)
    * Wires Function↔Structure ports (`plant_port()`, `obj_store_context()`, `as_transport_port` in `cats.executor.function`). Must not import Order `data/` sources; Function owns the `TransportPort` Protocol only.
