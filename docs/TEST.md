## [Test(s)](../tests/):

**Coverage (two tiers)**

- **Integration** — [`tests/test_provenance.py`](../tests/test_provenance.py): live Node + ContentStore.
  Submits CAT0 and CAT1 **once** (module-scoped fixture), then asserts full provenance
  records (Order Function/Structure pairing, Invoice stage CIDs, BOM log + Plant /
  InfraStructure snapshots) and CAT0/CAT1 `data_cid` lineage equality. Needs Session 1 below.
  See [`BOM.md`](./BOM.md) and [`LineageOfProvenance.md`](./LineageOfProvenance.md).
- **Unit** — the other `tests/test_*.py` modules: mocked / in-process / source guards
  (lineage helpers, named binds, ports, IaaS utils, MeshClient RPC, Node CLI, etc.).
  No live Node required. [`tests/test_ipfs_client.py`](../tests/test_ipfs_client.py) is thin Kubo smoke (`@requires_kubo`; skips if `:5001` is down).

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

  a. *List integration tests* without running them:
  ```bash
  uv run pytest --collect-only tests/test_provenance.py
  ```

  b. **Run integration tests** (provenance + data lineage):
  ```bash
  # Live Node: CAT0/CAT1 once; full provenance records + data_cid lineage equality
  uv run pytest -s tests/test_provenance.py
  ```
    - `pytest` also invokes cleanup via `tests/conftest.py` at session start (session autouse fixture).
    
  c. **Run unit tests** (everything except the live provenance module).
     All at once:
  ```bash
  uv run pytest -s tests/ --ignore=tests/test_provenance.py
  ```
     Or per file:
  ```bash
  # ComputePort / PlantPort / JobHandle + Process/InfraFunction surface guards
  uv run pytest -s tests/test_compute_plant_ports.py

  # Order-submitted vs MeshClient bootstrap ContentStore binding
  uv run pytest -s tests/test_content_store_ensure_binding.py

  # Function source directory CIDs + pickle/named-bind hybrid on function_cid
  uv run pytest -s tests/test_function_source_cid.py

  # InfraStructure content_store_utils / ContentStore
  uv run pytest -s tests/test_infrastructure_content_store_utils.py

  # InfraStructure obj_store_utils / ObjectStore / JobHandle
  uv run pytest -s tests/test_infrastructure_obj_store_utils.py

  # InfraStructure transport_utils / TransportContext
  uv run pytest -s tests/test_infrastructure_transport_utils.py

  # CatsIPFSClient Kubo RPC (smoke skips if :5001 down)
  uv run pytest -s tests/test_ipfs_client.py

  # MeshClient.linkOrder — combined Function/Structure lineage helper
  uv run pytest -s tests/test_link_order.py

  # MeshClient.linkStructure — Structure lineage twin of linkProcess
  uv run pytest -s tests/test_link_structure.py

  # MeshClient Kubo RPC + CAT_NODE_* endpoints (no ipfs CLI)
  uv run pytest -s tests/test_meshclient_rpc_surface.py

  # Named-bind JSON leaves vs pickle for Function Order slots
  uv run pytest -s tests/test_named_binds.py

  # AQ-safe Node CLI (start/stop/status/ensure)
  uv run pytest -s tests/test_node_lifecycle_cli.py

  # Plant plant_utils / PlantContext
  uv run pytest -s tests/test_plant_utils.py

  # Process / InfraFunction public-surface discipline
  uv run pytest -s tests/test_process_public_surface.py

  # Terraform module-cache readiness (InfraStructure.initialize)
  uv run pytest -s tests/test_structure_modules_installed.py

  # Structure root_cid staging + getEnhancedBom materialize
  uv run pytest -s tests/test_structure_root_cid.py

  # TransportPort Protocol + as_transport_port facade
  uv run pytest -s tests/test_transport_port.py
  ```
