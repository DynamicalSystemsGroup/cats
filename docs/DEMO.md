## [Establish a CAT Mesh:](../notebooks/cats_demo.py)

#### Steps:

##### 0. Start Docker daemon:

Needed for **Structure** facets (MinIO scratch + Plant / KubeRay), **not** Docker Kubo T&D peers (retired §6s).

##### 1. Content store + Node lifecycle: see [`NodeLifeCycle.md`](./NodeLifeCycle.md) (optional Kubo: [`IPFS.md`](./IPFS.md))

Live Orders use Node **CAS-over-HTTP**. Host Kubo is optional operator tooling. Node start
**soft-probes** ContentStore and does not hard-require Kubo (§6r/§6s). See [`NodeLifeCycle.md`](./NodeLifeCycle.md).

##### 2. [Create the environment](./ENV.md) and install dependencies *in Terminal C*:

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
make node-start              # soft-probes ContentStore; Kubo not required for CAS-only
# optional: make node-up     # content-store-ensure && node-start (brings Kubo tooling up too)
make node-stop               # Flask only — host Kubo left running if you started it
```

##### 4. Establish Data (CAT) Mesh *in Terminal B*: [Demo](../notebooks/cats_demo.py)

Execute CATs on a single-node Mesh via Marimo — the **REPLaC (REPL as Code) Workflow UI** of Function [FaaS], used to compose Process [Composed Function] (transport callables plus a Higher-Order Transfer Function / hotF, `integrated_subproc`) for InfraFunction [Actuator] to dispatch onto Plant [SaaS]. Function sources are packaged as `data/input/function/process/` and `data/input/function/infrafunction/` (import the package public surfaces). Compose Orders with **named imports** of the Process public surface only (`ingress`, `egress`, `integration_cache`, `process_*`, … — see `process.__all__`); never `from data.input.function.process import *`. Stock surfaces are Order-bound as named-bind JSON leaves (`contentId` + optional `source_uri` / `module` / `qualname`); non-stock REPL callables still pickle. Across runs, `linkProcess` mutates Function lineage, `linkStructure` mutates Structure lineage, and `linkOrder` mutates Function and/or Structure in one lineage step (all chain prior Invoice **data** equality via `data_uri` / `ni:`). Each `link*` accepts a prior HTTP `cat_response` **or** `content_id=` / `data_uri=` / `bom_uri=` / `hl=` resolved through the Node-local BOM registry (`GET /ldp/registry/…`; see [`BomRegistry.md`](BomRegistry.md)). Legacy `bom_cid=` / `data_cid=` are rejected. Recreate Orders after Function module-path or bind-shape changes.

**What you should see after CAT0 `catSubmit`:** HTTP envelope with `content_id`, `bom_ldp_uri`, optional `hl` / `bom_solid_uri`; signed `bom` carrying `invoice_uri` / `log_uri` / `node_did` + Data Integrity proof; `flatten_bom` expands those URIs into Invoice / Order / stage refs (`data_uri`, `function_uri`, `structure_uri`, …). CAT1 in the notebook uses `linkProcess` (Function lineage) — not a second independent `create_order_request`.

Marimo’s working directory is `notebooks/`. `from cats import …` does not import
Order Function sources (`cats/` must not `import data`). The registry-first demo’s
`cat0_create_order` cell inserts `CATS_HOME` on `sys.path` before named Process
imports. For [`cats_demo.py`](../notebooks/cats_demo.py) (or any cell that imports
`data` without that insert), run with the repo on `PYTHONPATH`:

```bash
PYTHONPATH=. uv run marimo edit notebooks/cats_demo.py
# registry-first lineage (linkProcess via content_id= / bom_ldp_uri=):
uv run marimo edit notebooks/new_cats_demo.py
```

After CAT0 `catSubmit`, [`new_cats_demo.py`](../notebooks/new_cats_demo.py) runs the same
library helpers as the unit suites: registry **index parity**, **handoff projection**
completeness, **claims reachability**, then **control-plane handoff coherence**,
then **content equivalence** (`assert_*_content_equiv` before flatten), then
**stageLineage directory-manifest** hops (`assert_directory_manifest_equiv` /
`assert_stage_lineage_payload_equiv`) — not “all HTTP content ∈ registry.”

Cells re-run reactively as dependencies change; work through the notebook top to bottom. See [`BomRegistry.md`](BomRegistry.md) for the Python registry guide.
