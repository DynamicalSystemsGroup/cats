### Manage CATs' Virtual Environment (via [uv](https://docs.astral.sh/uv/)):

CATs uses [uv](https://docs.astral.sh/uv/) to manage its Python interpreter, virtual environment, and locked
dependencies (`uv.lock`). uv creates/updates `./.venv` automatically — there's no separate `python -m venv` step.

##### 0. Install the pinned Python interpreter (from `.python-version`):
```bash
# CATs working directory
cd cats
pip install uv
uv python install
```
##### 1. Create/refresh `.venv` and install locked dependencies:
```bash
uv sync                       # base install
uv sync --extra ops           # + Ray, pandas, Marimo (mesh demo)
uv sync --group dev           # + pytest, build (contributor tooling)
```
The [MAC experiment](../experiments/mac/MAC.md) isn't a package extra — it's installed separately with
`uv pip install -r experiments/mac/requirements-mac.txt` into the same `.venv`, since it's experiment-only
and not part of the `cats` package's published dependencies.

##### 1b. Operator / secrets (repo-root `.env`):

`cats` loads `.env` from the **repo root** on import (not from cwd). Shell-exported
variables win over the file. Create the file from the template **only if it does
not already exist** (never `cp` over an existing `.env` — that clobbers MAC keys
and other secrets):

```bash
test -f .env || cp .env.example .env
```

To add new operator keys, copy lines from `.env.example` into the existing `.env`.

| Variable | Default if unset | Role |
| --- | --- | --- |
| `CAT_NODE_HOST` / `CAT_NODE_PORT` | `127.0.0.1` / `5000` | Flask bind + client URL + `node_uri` |
| `CAT_NODE_DID` | `{CATS_HOME}/.cats/node_did.json` | Override Node `did:key` |
| `IPFS_API_HOST` / `IPFS_API_PORT` | `127.0.0.1` / `5001` | Optional Kubo HTTP API |
| `CATS_IO_PARTITIONS` | `1` | Process IoPort partition count |
| `CATS_IO_VIA_JOB` | unset (false) | IoPort via Ray job when `1`/`true`/`yes`/`on` |
| `SOLID_*` | unset (Solid off) | Control-plane pod; see [`SOLID.md`](./SOLID.md) |

`.env` is gitignored. Do **not** put `CATS_HOME`, `TF_DATA_DIR`,
`INTEGRATION_INPUT_DATA_CACHE`, `RAY_ENABLE_UV_RUN_RUNTIME_ENV`, or
`WERKZEUG_RUN_MAIN` here — those are derived or written by `cats`.
Do not set empty `VAR=` lines (that overrides the code default with `""`).

#### 2. Run commands in the environment (no manual activate/deactivate needed)
```bash
make node-up                    # optional: content-store-ensure then node-start (see NodeLifeCycle.md)
make node-start                 # soft-probes ContentStore; Kubo not required for CAS-only
make node-stop                  # Flask only — never host Kubo
uv run pytest tests/test_provenance.py
```
**Optional — activate `.venv` directly** (traditional venv activate/deactivate, if you prefer it to `uv run`):
```bash
source ./.venv/bin/activate
# (.venv) $
deactivate
# $
```