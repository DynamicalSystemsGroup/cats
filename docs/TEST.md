## [Test(s)](../tests/):

**Coverage (two tiers)**

- **Integration** — [`tests/test_provenance.py`](../tests/test_provenance.py): live Node + ContentStore.
  Submits CAT0 and CAT1 **once** (module-scoped fixture), then asserts full provenance
  records (Order Function/Structure pairing, Invoice stage refs, BOM log + Plant /
  InfraStructure snapshots) and CAT0/CAT1 data lineage equality (`ni:` / content id).
  Needs Session 1 below.
  This is also the only live coverage of the ephemeral **Executor** path (Factory →
  Executor → Invoice/BOM); there is no dedicated `test_executor*.py` module.
  See [`BOM.md`](./BOM.md) and [`LineageOfProvenance.md`](./LineageOfProvenance.md).
- **Unit** — the other `tests/test_*.py` modules: mocked / in-process / source guards
  (lineage helpers, named binds, ports, IaaS utils, ContentMesh RPC, Node CLI, etc.).
  No live Node required. [`tests/test_ipfs_client.py`](../tests/test_ipfs_client.py) is thin Kubo smoke (`@requires_kubo`; skips if `:5001` is down).
  Control-plane Python (§6e) uses `*_id` / `put_dir`; minted JSON stays `*_uri` / `contentId` (§6d).
  §6f `hl:` resolve/emit/intake: [`tests/test_hl_resolve.py`](../tests/test_hl_resolve.py).
  §6i Structure marker `.applied-structure.id` (+ plant `applied_structure_id`):
  [`tests/test_structure_root_cid.py`](../tests/test_structure_root_cid.py) /
  [`tests/test_plant_utils.py`](../tests/test_plant_utils.py).
  §6j Process/Plant/Ray Order ABI (`input_dir_id`, Ray `input_id`/`layout_id`,
  obj_store `structure_id`): [`tests/test_transport_port.py`](../tests/test_transport_port.py) /
  [`tests/test_infrastructure_transport_utils.py`](../tests/test_infrastructure_transport_utils.py) /
  [`tests/test_infrastructure_obj_store_utils.py`](../tests/test_infrastructure_obj_store_utils.py) /
  [`tests/test_ray_io_partitions.py`](../tests/test_ray_io_partitions.py).
  For mesh-reachable LDP hints in `hl:`, set `CAT_NODE_HOST` to an address peers can open
  (loopback only warns).

1. **[Install CATs](https://github.com/DynamicalSystemsGroup/cats/tree/cats2?tab=readme-ov-file#get-started)** (`uv sync --extra ops --group dev` for mesh demos and tests; `dev` provides `pytest`)
  - **Root Dependency**: see [`NodeLifeCycle.md`](./NodeLifeCycle.md) — run `make content-store-ensure` before
  `make node-start` (start asserts only). Host Kubo detail: [`IPFS.md`](./IPFS.md).
2. **Session 1**
  a. *[Create the environment](./ENV.md)*
  ```bash
  cd cats     
  uv sync --extra ops --group dev
  ```
    - `uv run` (below) uses this `.venv` automatically — no manual activation needed.
  b. **Ensure ContentStore, then start CAT Node** — follow [`NodeLifeCycle.md`](./NodeLifeCycle.md).
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
  # Live Node: CAT0/CAT1 once; full provenance records + data lineage equality
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

  # Order-submitted vs ContentMesh bootstrap ContentStore binding
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

  # ContentMesh.linkOrder — combined Function/Structure lineage helper
  uv run pytest -s tests/test_link_order.py

  # ContentMesh.linkStructure — Structure lineage twin of linkProcess
  uv run pytest -s tests/test_link_structure.py

  # BOM registry — Node-local data→BOM / init / link* (§6d content_id / bom_ids)
  # Contract: docs/BomRegistry.md
  uv run pytest -s tests/test_bom_registry.py

  # CAS-over-HTTP — CasHttpStore, ni:/digest, manifests, locators, AddressStore
  uv run pytest -s tests/test_cas_http.py

  # Phase 2b / §6f — URI address + ni:/hl: proof, Order/Invoice LDP, hl: resolve/emit
  uv run pytest -s tests/test_phase2b_uri.py tests/test_hl_resolve.py

  # ContentMesh Kubo RPC + CAT_NODE_* endpoints (no ipfs CLI)
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
