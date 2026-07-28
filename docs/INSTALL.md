1. **Clone CATs:**
  ```bash
    git clone git@github.com:DynamicalSystemsGroup/cats.git
    cd cats
    uv python install   # installs the Python version pinned in .python-version
    uv sync             # creates .venv and installs locked dependencies from uv.lock
  ```
  - See `[ENV.md](./docs/ENV.md)` for the full environment workflow, including the `ops` and `mac` extras.
2. **Install [Dependencies](./docs/DEPS.md)** (including [uv](https://docs.astral.sh/uv/), which manages
  CATs' Python interpreter, virtual environment, and locked dependencies)
  ```bash
  make deps-all
  # core: make deps
  # optional extras alone: make deps-helm / make deps-graphviz
  ```
  - Runs on macOS or Linux (see the `[Makefile](./Makefile)` and `make help`), or follow
  `[DEPS.md](./docs/DEPS.md)` to install each dependency manually.