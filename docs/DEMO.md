## [Establish a CAT Mesh:](../cats_demo.py)

#### Steps:

##### 0. Start Docker daemon:

##### 1. IPFS content store + Node lifecycle: see [`NodeLifeCycle.md`](./NodeLifeCycle.md) (host Kubo detail: [`IPFS.md`](./IPFS.md))

Host Kubo is InfraStructure’s long-lived **content-store facet**. **Before** `make node-start`, ensure
the ContentStore API is up (Node start **asserts** only — it does not heal). See [`NodeLifeCycle.md`](./NodeLifeCycle.md).

##### 2. [Create the environment](./docs/ENV.md) and install dependencies *in Terminal C*:

```bash
# CATs working directory
cd cats
uv sync --extra ops
```

`uv sync` creates/updates `.venv` from the locked dependencies (`uv.lock`); `--extra ops` adds Marimo, Ray, and
pandas for the mesh workflow. `uv run` (below) uses this environment automatically — no manual activation needed.

##### 3. Deploy CAT Node *in Terminal A*:

Follow [`NodeLifeCycle.md`](./NodeLifeCycle.md) (or [Get Started!](../README.md#get-started)).
```bash
make node-up                 # or: make content-store-ensure && make node-start
make node-stop               # Flask only — host Kubo left running
```

##### 4. Establish Data (CAT) Mesh *in Terminal B*: [Demo](../cats_demo.py)

Execute CATs on a single-node Mesh via Marimo — the **REPLaC (REPL as Code) Workflow UI** of Function [FaaS], used to compose Process [Composed Function] (transport callables plus a Higher-Order Transfer Function / hotF, `integrated_subproc`) for InfraFunction [Actuator] to dispatch onto Plant [SaaS]. Function sources are packaged as `data/input/function/process/` and `data/input/function/infrafunction/` (import the package public surfaces). Compose Orders with **named imports** of the Process public surface only (`ingress`, `egress`, `integration_cache`, `process_*`, … — see `process.__all__`); never `from data.input.function.process import *`. Stock surfaces are Order-bound as named-bind JSON leaves (`source_cid` / `module` / `qualname`); non-stock REPL callables still pickle. Across runs, `linkProcess` mutates Function lineage, `linkStructure` mutates Structure lineage, and `linkOrder` mutates Function and/or Structure in one lineage step (all chain prior Invoice `data_cid`; a-la-carte helpers remain). Each `link*` accepts a prior HTTP `cat_response` **or** `bom_cid=` / `data_cid=` resolved through the Node-local BOM registry (`GET /ldp/registry/…`; see [`BomRegistry.md`](BomRegistry.md)). Recreate Orders after Function module-path or bind-shape changes.

```bash
uv run marimo edit cats_demo.py
```

Cells re-run reactively as dependencies change; work through the notebook top to bottom.