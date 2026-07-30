# What kind of "Plant" is a CAT Node?

CATs' architecture is built around the "Plant" family of engineering analogies referenced throughout `[README.md](../README.md)`, `[COMPONENTS.md](COMPONENTS.md)`, and `[NodeProductFlow.md](NodeProductFlow.md)`. This article answers a more literal version of that question: mapped against Wikipedia's own **[Plant (disambiguation) - Heavy industry and engineering](https://en.wikipedia.org/wiki/Plant_(disambiguation)#Heavy_industry_and_engineering)** listed a s follows:

- **Represented Plants:**
  - [Plant (control theory)](https://en.wikipedia.org/wiki/Plant_(control_theory)) - the combination of process and actuator & analogous to CAT Node's Function [FaaS]
  - [Manufacturing plant](https://en.wikipedia.org/wiki/Manufacturing_plant) - analogous to CAT Node's (Product) Factory which is also analogous to a [Software Factory](https://en.wikipedia.org/wiki/Software_factory) 
  - [Power plant](https://en.wikipedia.org/wiki/Power_station) analogous to CAT Node's "Structure" [PaaS]
  - [Physical plant](https://en.wikipedia.org/wiki/Physical_plant) - a facility's infrastructure analogous to CAT Node's Structure's "InfraStructure" [IaaS]
- **Non-Represented Plants:**
  - [Chemical plant](https://en.wikipedia.org/wiki/Chemical_plant)
  - [Heavy equipment](https://en.wikipedia.org/wiki/Heavy_equipment)

**Questions:**

- what type of "plant" is the **CAT Node** as a whole, and
- what type of "plant" is each of its constituent **Architectural Components** (`[COMPONENTS.md](COMPONENTS.md)`: the Factory, the Architectural Quantum, the ephemeral Executor) and their nested sub-components (`[NodeProductFlow.md](NodeProductFlow.md)`: Function/Process/InfraFunction, Structure/Plant/InfraStructure), taken separately.

## Caveat: which "Power plant" article actually applies

"Power plant" effectively surfaces twice on the disambiguation page, and they mean different things:

- **[Power station](https://en.wikipedia.org/wiki/Power_station)** - the top-level bullet's target: a facility
that *generates* power and feeds it into a Transmission & Distribution (T&D) grid. This is the
"generation + Transmission & Distribution (T&D)" model.
- **[Physical plant § Power plants](https://en.wikipedia.org/wiki/Physical_plant#Power_plants)** - a subsection
nested *inside* the separate "Physical plant" bullet's target article. It isn't the generation+grid model; it's
a taxonomy of a power facility's *internal equipment* (primary systems like the reactor core/cooling loops vs.
generic balance-of-plant systems like turbines/generators/feedwater) - an equipment classification, not a
generation / Transmission & Distribution (T&D) architecture.

For CATs, the meaningful match is the **Power Station** sense: `Plant [SaaS]` generates compute
(Ray/KubeRay), `InfraStructure [IaaS]` is the Transmission & Distribution (T&D) substrate (IPFS/MinIO/Docker Compose)
the generated results move through. Job **landing** (entrypoint + `ComputePort` adapter) is Plant-owned
under `plant_cid`; scratch correlators (`ObjectStore` / `JobHandle`) stay IaaS — see [`INTEROP.md`](./INTEROP.md) §2g.
The Physical-Plant-internal "Power plants" taxonomy doesn't map onto that
generation / Transmission & Distribution (T&D) split; at most, its primary-systems/balance-of-plant-systems distinction loosely echoes
`Plant [SaaS]` (generation-specific core) vs. `InfraStructure [IaaS]` (generic supporting substrate reusable
across generation mechanisms) - worth noting, but not the primary analogy used below.

## The CAT Node as a whole

The CAT Node doesn't reduce to one single type from the "Heavy industry and engineering" list - it's a
**composite** that spans three of the six categories, each operating at a different structural layer:


| Layer                                                          | Type match                            |
| -------------------------------------------------------------- | ------------------------------------- |
| Factory (assembles the Executor from Order components)         | **Manufacturing Plant**               |
| Function [FaaS] (Process [Composed Function] + InfraFunction [Actuator]) | **Plant (control theory)**     |
| Structure [PaaS] (Plant [SaaS] + InfraStructure [IaaS])        | **Power Plant** (Power Station sense) |


No single Node-level component is a **Chemical plant** or **Heavy equipment** - those two categories have no
analog anywhere in CATs' architecture.

## Per-component breakdown

Using `[COMPONENTS.md](COMPONENTS.md)`'s three named Architectural Components, plus the nested components
`[NodeProductFlow.md](NodeProductFlow.md)` defines the actual "plant"-like behavior for:

### 1. the Factory

`[COMPONENTS.md](COMPONENTS.md)` itself cites [Factory](https://en.wikipedia.org/wiki/Factory) directly. Among
the six: **Manufacturing plant**. It takes an Order (raw materials: Input Invoice + Function CID + Structure
CID) and assembles/composes them into a finished product (the ephemeral Executor) - the
assembly-from-specification pattern is exactly Manufacturing plant's definition.
Order intake/staging is `Factory.accept` (reached via `Runtime.initFactory`); Runtime remains the
Node process-lifetime ambient, not the manufacturing logic.

### 2. the Architectural Quantum

Per `[NodeProductFlow.md](NodeProductFlow.md)` step 0B, the Architectural Quantum is `Function [FaaS]` +
`Structure [PaaS]`. It isn't a single type; it's the *union* of the next two rows, since it's defined as
Function's dependency on Structure, not a standalone facility:

- **Function [FaaS]** (`Process [Composed Function]` + `InfraFunction [Actuator]`) -> **Plant (control theory)** as a whole -
"the combination of process and actuator" is verbatim Function's own composition (Process [Composed Function] = the
composed callable graph / FaaS-composer analogue: transport/`ComputePort` callables plus a Plant-agnostic tHOF = the "process"; InfraFunction [Actuator] = the actuator dispatching that tHOF onto compute via `PlantPort`). Orders are authored via the REPLaC Workflow UI of Function [FaaS] (Marimo in this demo).
  - `Process [Composed Function]` alone -> the **process** half of Plant (control theory)
  - `InfraFunction [Actuator]` alone -> the **actuator** half of Plant (control theory)
- **Structure [PaaS]** (`Plant [SaaS]` + `InfraStructure [IaaS]`) -> **Power plant**, specifically the Power
Station generation + Transmission & Distribution (T&D) model (per the caveat above).
  - `Plant [SaaS]` alone (this demo: Ray/KubeRay via `RayPlantPort`) -> the **generation** side of that Power Station model - not a
  separately-named type on the list, since "generation" isn't its own bullet, but it's the half of Power
  plant that produces the resource. Function stays Plant-agnostic; Ray adapters live under Structure.
  - `InfraStructure [IaaS]` alone (IPFS/MinIO/Docker Compose) -> doubles as **Physical plant** in its own right
  ("a facility's infrastructure" - its literal Wikipedia definition matches directly) *and* plays the
  Transmission & Distribution (T&D) role within Structure's Power-Station reading. It's the one component that
  legitimately sits in two of the six categories simultaneously.

### 3. the (ephemeral) Executor

Doesn't fit any of the six categories itself. It doesn't generate, transmit, manufacture, or process anything on
its own; it's the *runtime that operates* the other plants - dispatching Function [FaaS] onto Structure [PaaS]
via InfraFunction [Actuator] dispatching onto Plant [SaaS] (`[NodeProductFlow.md](NodeProductFlow.md)` step 2a). Structurally
it's closer to a plant *operator/control-room process* than to a plant itself - it's the thing standing between
the Manufacturing-plant output (a composed Function+Structure pair) and those components' own actual execution.

## Summary table


| Component             | Plant (control theory) | Manufacturing plant | Physical plant | Power plant         | Chemical plant | Heavy equipment |
| --------------------- | ---------------------- | ------------------- | -------------- | ------------------- | -------------- | --------------- |
| CAT Node (whole)      | ✓ (via Function)       | ✓ (via Factory)     | -              | ✓ (via Structure)   | -              | -               |
| Factory               | -                      | **✓**               | -              | -                   | -              | -               |
| Architectural Quantum | ✓ (Function half)      | -                   | -              | ✓ (Structure half)  | -              | -               |
| Process [Composed Function] | ✓ ("process" half) | -                   | -              | -                   | -              | -               |
| InfraFunction [Actuator] | ✓ ("actuator" half) | -                   | -              | -                   | -              | -               |
| Structure [PaaS]      | -                      | -                   | -              | **✓**               | -              | -               |
| Plant [SaaS]          | -                      | -                   | -              | ✓ (generation half) | -              | -               |
| InfraStructure [IaaS] | -                      | -                   | **✓**          | ✓ (Transmission & Distribution (T&D) half) | -              | -               |
| Executor              | -                      | -                   | -              | -                   | -              | -               |


See also: `[COMPONENTS.md](COMPONENTS.md)` for the Node's top-level Architectural Components,
`[NodeProductFlow.md](NodeProductFlow.md)` for how they're exercised per execution,
`[DESIGN.md](DESIGN.md)` for how the Architectural Quantum is realized as content-addressed CIDs, and
`[INTEROP.md](INTEROP.md)` for proving Plant/T&D interoperability across AQ components.