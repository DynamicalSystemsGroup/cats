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