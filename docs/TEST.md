## [Test(s)](../tests/verification_test.py):

1. **[Install CATs](https://github.com/DynamicalSystemsGroup/cats/tree/cats2?tab=readme-ov-file#get-started)** (`uv sync --extra ops --group dev` for mesh demos and tests; `dev` provides `pytest`)
  - **Root Dependency**: see `[IPFS.md](./IPFS.md)` — run `make content-store-ensure` before
  `make node-start` (start asserts only). MeshClient soft-warns if the API is down. Order-submitted
  TF `host_ipfs_daemon` create is the sole automatic `ContentStore.ensure`; Structure `apply` asserts
  readiness after TF.
2. **Session 1**
  a. *[Create the environment](./ENV.md)*
  ```bash
  cd cats     
  uv sync --extra ops --group dev
  ```
    - `uv run` (below) uses this `.venv` automatically — no manual activation needed.
  b. **Ensure ContentStore, then start CAT Node** — follow [Get Started! step 3](../README.md#get-started).
  ```bash
  make content-store-ensure
  make node-start
  ```
3. **Session 2:**
  a. *List Tests* without running them:
  ```bash
  uv run pytest --collect-only tests/verification_test.py
  ```
  b. **Run All Tests**
  ```bash
  uv run pytest -s tests/verification_test.py
  ```
    - `pytest` also invokes this script via `tests/conftest.py` at session start and through a session autouse fixture.