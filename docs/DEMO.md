## [Establish a CAT Mesh:](../cats_demo.py)

#### Steps:

##### 0. Start Docker daemon:

##### 1. IPFS content store (InfraStructure): see `[IPFS.md](./IPFS.md)`

Host Kubo is InfraStructure’s long-lived **content-store facet**. **Before** `make node-start`, ensure
the ContentStore API is up (Node start **asserts** only — it does not heal). ContentMesh soft-warns if
the API is down and does **not** auto-ensure. Order-submitted TF `host_ipfs_daemon` create is the sole
**automatic** ensure during Structure apply; `apply` then asserts readiness.

```bash
# from repo root — heal/start host Kubo (required before node-start if :5001 is down)
make content-store-ensure
# or: uv run python data/input/structure/infrastructure/content_store_utils.py ensure
# or: uv run python cats/node.py ensure
```

Or run `ipfs daemon` yourself only if you want its logs in their own terminal. `make node-stop` / Node exit
and Structure destroy do **not** stop host Kubo.

##### 2. [Create the environment](./docs/ENV.md) and install dependencies *in Terminal C*:

```bash
# CATs working directory
cd cats
uv sync --extra ops
```

`uv sync` creates/updates `.venv` from the locked dependencies (`uv.lock`); `--extra ops` adds Marimo, Ray, and
pandas for the mesh workflow. `uv run` (below) uses this environment automatically — no manual activation needed.

##### 3. Deploy CAT Node *in Terminal A*:

Follow [Get Started! step 3](../README.md#get-started) in the README.
```bash
make node-start
```
To stop Flask only afterward, see [Get Started! step 7](../README.md#get-started).
```bash
make node-stop
```

##### 4. Establish Data (CAT) Mesh *in Terminal B*: [Demo](../cats_demo.py)

Execute CATs on a single-node Mesh via Marimo — the **REPLaC (REPL as Code) Workflow UI** of Function [FaaS], used to compose Process [Composed Function] (transport callables plus a Transfer Higher-Order Function / tHOF, `integrated_subproc`) for InfraFunction [Actuator] to dispatch onto Plant [SaaS]. Function sources are packaged as `data/input/function/process/` and `data/input/function/infrafunction/` (import the package public surfaces). Compose Orders with **named imports** of the Process public surface only (`ingress`, `egress`, `integration_cache`, `process_*`, … — see `process.__all__`); never `from data.input.function.process import *`. Stock surfaces are Order-bound as named-bind JSON leaves (`source_cid` / `module` / `qualname`); non-stock REPL callables still pickle. Across runs, `linkProcess` mutates Function lineage, `linkStructure` mutates Structure lineage, and `linkOrder` mutates Function and/or Structure in one lineage step (all chain prior Invoice `data_cid`; a-la-carte helpers remain). Recreate Orders after Function module-path or bind-shape changes.

```bash
uv run marimo edit cats_demo.py
```

Cells re-run reactively as dependencies change; work through the notebook top to bottom.