## [Establish a CAT Mesh:](../cats_demo.py)
#### Steps:
##### 0. Start Docker daemon:
##### 1. IPFS daemon: see [`IPFS.md`](./IPFS.md)
Both `cats/node.py` (step 3) and the Structure's `terraform apply` start the host IPFS
daemon automatically, idempotently, if one isn't already running — so this step isn't
required. Run it yourself only if you want its logs in their own terminal.
##### 2. [Create the environment](./docs/ENV.md) and install dependencies *in Terminal C*:
```bash
# CATs working directory
cd cats
uv sync --extra ops
```
`uv sync` creates/updates `.venv` from the locked dependencies (`uv.lock`); `--extra ops` adds Marimo, Ray, and
pandas for the mesh workflow. `uv run` (below) uses this environment automatically — no manual activation needed.
##### 3. Deploy CAT Node *in Terminal A*:
```bash
uv run python cats/node.py
```
##### 4. Establish Data (CAT) Mesh *in Terminal B*: [Demo](../cats_demo.py)
Execute CATs on a single-node Mesh via Marimo notebook — this is Process [REPL(aC)]: a Read-Eval-Print Loop as Code that composes and submits transport callables plus a Transfer Higher-Order Function (tHOF, `integrated_subproc`) for InfraFunction [FaaS] to dispatch onto Plant [SaaS].
```bash
uv run marimo edit cats_demo.py
```
Cells re-run reactively as dependencies change; work through the notebook top to bottom.