## [Establish a CAT Mesh:](../notebooks/cats_demo.py)

#### Steps:

##### 0. Start Docker daemon:

Needed for **Structure** facets (MinIO scratch + Plant / KubeRay), **not** Docker Kubo T&D peers (retired).

##### 1. Content store + Node lifecycle: see [`NodeLifeCycle.md`](./NodeLifeCycle.md) (optional Kubo: [`IPFS.md`](./IPFS.md))

Live Orders use Node **CAS-over-HTTP**. Host Kubo is optional operator tooling. Node start
**soft-probes** ContentStore and does not hard-require Kubo. See [`NodeLifeCycle.md`](./NodeLifeCycle.md).

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

Registry-first CAT0→CAT1 Control-Feedback walk in Marimo (details in the notebook). Node must be up (`make node-start`). Named Process imports only — never `from data.input.function.process import *`.

```bash
uv run marimo edit notebooks/cats_demo.py
```

**After CAT0 `catSubmit`:** envelope has `content_id` / `bom_ldp_uri` (optional `hl` / `bom_solid_uri`); Invoice URI is on signed `bom`, not the HTTP top-level. CAT1 uses `linkProcess` via registry (`content_id=` / `bom_ldp_uri=`), then `flatten_bom` (returns `{invoice, log}` under `flat`; does not mutate the envelope).

Shared suite helpers: parity → handoff/reachability → content-equiv → stageLineage manifest equiv — not “all HTTP ∈ registry.”

**Not in this notebook** (see [`INTEROP.md`](./INTEROP.md)): `linkStructure`, mesh-federated registry, CAT1 as-executed/content-equiv replay, `tests/test_provenance.py` dataframe checks.

##### 5. (Optional) Envelope-held walk: [`old_cats_demo.py`](../notebooks/old_cats_demo.py)

Earlier demo that holds `cat_response` in-notebook (not registry-first). Needs the repo on `PYTHONPATH`:

```bash
PYTHONPATH=. uv run marimo edit notebooks/old_cats_demo.py
```
