import marimo

__generated_with = "0.23.13"
app = marimo.App()


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # CAT Node Control-Feedback Loop: Data Provenance and Lineage of a Data Product's CATs (CAT0 → CAT1)

    **Provenance** is the **record** (signed BOM / Invoice / Order binding — what ran, with what). **Lineage** is the **path** (how data or Process/Function connect — intra-run hops or CAT→CAT equality). This notebook demonstrates **data and process** of both:

    | | Provenance (record) | Lineage (path) |
    |---|---|---|
    | **Data** | CAT0 signed BOM + Invoice `data` / `data_stages` / as-executed; CAT1 mints a **new** BOM (catalogued, not a CAT0 inspect replay) | CAT0 intra-run `stageLineage`; CAT1 input Invoice data ≡ CAT0 output data |
    | **Process** | CAT0 Order Function pairing (`process_0` as hotF); Invoice seed is the Process replay dict; CAT1 seed is a new replay dict | CAT1 `linkProcess`: Function mutated (`process_1`), Structure carried |

    Not demonstrated here: `linkStructure` (Structure mutation); mesh-federated registry; CAT1 `stageLineage` / as-executed / content-equiv; dataframe transform checks (`tests/test_provenance.py`).

    **Together**, CAT0 then CAT1 is one **Data Mesh Control-Feedback Loop** closed across _two Data Product Process executions._ A CAT Node is a mesh-peer **Data Product**: the Architectural Quantum (code + data + infrastructure) is the deployable unit. The platform’s intended **self-serve intake** is the next Order recovered from a prior **BOM** (provenance record) via the Node-local registry. This Order is not a held envelope, not a second out-of-band `create_order_request`, and not a BOM→BOM pointer in the bytes. CAT0 **publishes** the first product onto the mesh (signed locators + index). CAT1 is **inter-product composition**: mutate Function, carry Structure, chain CAT0’s output data as input. Same loop each time (Order → manufactured execution → Invoice → BOM + registry → inspect). That is federated computational governance on the **Action Plane** (catalog/verify BOMs) supervising the **Data Plane** (process and transport CATs). Mesh-global federation of the index is still Node-local here.
    * **CAT0** (*mint and prove one Data Product run*, registry-first — **data provenance**, **process provenance**, **intra-run data lineage**). Domain team authors the first Order locally (`process_0`) — out-of-band because there is no prior BOM. Execute Function on Structure, Invoice staged output, emit a signed BOM as the **supply chain of evidence**. A collaborator verifies **one** product from HTTP/registry pointers alone (`flatten_uri_dict`, not `flatten_bom`) — retrieval and re-execution without holding Invoice bytes in the envelope. Writes `cat0_record` / `cat0_data_id` into the self-serve catalog. Does not compose the next product (no process lineage / cross-CAT data lineage).
    * **CAT1** (*compose the next Data Product from the catalog, then prove lineage* — **process lineage**, **cross-CAT data lineage**, plus a **new data-provenance** BOM and **new process provenance** (seed)). Stewardship/composition uses `linkProcess(content_id=cat0_data_id)` (or `bom_ldp_uri=` if `by-data` is ambiguous), hotF `process_1`. Same execute/index loop on a new BOM — a new product version on the mesh, not a replay of CAT0. Inspect is `flatten_bom` + lineage helpers: Function mutated, Structure carried, CAT1 **input** data ≡ CAT0 **output** data (data-as-product equality), and a **new** execution (output data and seeds differ). That is lineage of provenance on the mesh without embedding a pointer to CAT0’s BOM in CAT1’s bytes. Does not replay CAT0’s locator walk / `stageLineage` / as-executed.
    """)
    return


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Instantiate mesh client and registry

    CAS-only `ContentMesh` plus Node-local `BomRegistry` / `LocatorIndex` (**data-provenance catalog**). Bound
    once above both CAT0 and CAT1 (`CONTENT_MESH`). Off the mint path.
    """)
    return


@app.cell
def mesh_client():
    from pprint import pprint

    from cats import CATS_HOME, CONTENT_MESH as contentMesh
    from cats import INPUT_STRUCTURE_HOME, INPUT_DATA_HOME
    from cats.network.cas import LocatorIndex
    from cats.network.registry import BomRegistry

    registry = BomRegistry(CATS_HOME)
    locator_index = LocatorIndex(CATS_HOME)
    return (
        CATS_HOME,
        INPUT_DATA_HOME,
        INPUT_STRUCTURE_HOME,
        contentMesh,
        locator_index,
        pprint,
        registry,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Instantiate inspect helpers

    Library asserts (same helpers as `tests/test_*.py`). Stay off the mint path
    so editing asserts does not remint.

    - **Both CATs (data provenance catalog):** `assert_registry_index_parity` → `assert_handoff_projection_complete` → `assert_registry_claims_reachable`. Inspect dump: `to_consume` / `index_shape` / `locator_http`.
    - **CAT0 — data + process provenance, intra-run data lineage:** handoff / `assert_*_content_equiv` / `assert_execution_bind` / `stageLineage` / as-executed; `flatten_uri_dict`
    - **CAT1 — process lineage + cross-CAT data lineage + new data provenance + new process provenance:** `assert_order_pairing_lineage`, `assert_invoice_data_chain`, `assert_distinct_executions`
    """)
    return


@app.cell(hide_code=True)
def inspect_helpers():
    import requests

    from cats.network.cas import flatten_uri_dict, ref_id
    from cats.network.cas import (
        assert_directory_manifest_equiv,
        assert_stage_lineage_payload_equiv,
    )
    from cats.network.node_http import _node_base_url
    from cats.network.registry import (
        assert_bom_content_equiv,
        assert_control_plane_handoff_coherence,
        assert_distinct_executions,
        assert_execution_bind,
        assert_handoff_projection_complete,
        assert_infrastructure_as_executed_slots,
        assert_input_invoice_slots,
        assert_invoice_content_equiv,
        assert_invoice_data_chain,
        assert_order_content_equiv,
        assert_order_function_content_equiv,
        assert_order_function_slots,
        assert_order_invoice_content_equiv,
        assert_order_pairing_lineage,
        assert_order_structure_content_equiv,
        assert_order_structure_slots,
        assert_plant_as_executed_snapshot,
        assert_registry_claims_reachable,
        assert_registry_index_parity,
        assert_structure_as_executed_bind,
        assert_structure_as_executed_slots,
    )

    _node_base = _node_base_url()


    def http_get_json(path):
        """GET Node path relative to `_node_base_url()` → JSON."""
        url = path if path.startswith("http") else f"{_node_base}{path}"
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return resp.json()


    def http_get(path):
        """GET Node path → raw bytes (opaque data_uri / stage payloads)."""
        url = path if path.startswith("http") else f"{_node_base}{path}"
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content


    return (
        assert_bom_content_equiv,
        assert_control_plane_handoff_coherence,
        assert_directory_manifest_equiv,
        assert_distinct_executions,
        assert_execution_bind,
        assert_handoff_projection_complete,
        assert_infrastructure_as_executed_slots,
        assert_input_invoice_slots,
        assert_invoice_content_equiv,
        assert_invoice_data_chain,
        assert_order_content_equiv,
        assert_order_function_content_equiv,
        assert_order_function_slots,
        assert_order_invoice_content_equiv,
        assert_order_pairing_lineage,
        assert_order_structure_content_equiv,
        assert_order_structure_slots,
        assert_plant_as_executed_snapshot,
        assert_registry_claims_reachable,
        assert_registry_index_parity,
        assert_stage_lineage_payload_equiv,
        assert_structure_as_executed_bind,
        assert_structure_as_executed_slots,
        flatten_uri_dict,
        http_get,
        http_get_json,
        ref_id,
        requests,
    )


@app.cell(hide_code=True)
def cat0_inspection(mo):
    mo.md(r"""
    ### Control-Feedback Loop Execution of CAT0 (registry-first) 🐈

    **Value:** a collaborator can take this Node’s first CAT as a **signed, locator-addressed Data Product** and verify **one** Control-Feedback run from HTTP / registry pointers alone, without holding the Invoice body in the HTTP envelope, and without a BOM→BOM pointer in the bytes. CAT0 **writes** `cat0_record` / `cat0_data_id` so CAT1 can compose from the index; recovering that next CAT is CAT1’s job.

    **Demonstration:**
    * **data provenance** (signed BOM as supply chain of evidence; Invoice `data` / `data_stages` / as-executed)
    * **process provenance** (Order Function / Process pairing as-Code, `process_0`; Invoice seed)
    * **intra-run data lineage** (`stageLineage`). Not **process lineage** or **cross-CAT data lineage** (CAT1).

    **Control-Feedback Loop** (this section’s purpose: *mint and prove one run*):

    1. **Order** — compose a content-addressed Order from local Function, Structure, and input Invoice (`cat0_create_order`). First mint is out-of-band; the loop’s intended intake is “Order from a prior BOM,” which this run **enables** by indexing the result.
    2. **Factory → Executor** — `catSubmit` reconstitutes the Architectural Quantum (Function on Structure), executes, and **Invoices** staged output (`cat0_submit_order`). The HTTP envelope is a signed BOM of locators (`invoice_uri` / `log_uri` / `node_did` + Data Integrity), not the Invoice body (**no** top-level `invoice_uri` / `order_uri`).
    3. **Runtime → BOM + registry** — the Node emits the signed ExecutionBom and indexes it so later CATs can find this run by data digest (`registry_index_parity`). Inspect dump is grouped `to_consume` / `index_shape` / `locator_http`. Index **write** is in scope; index **lineage compose** is not.
    4. **Feedback inspect (locator-first)** — walk BOM → Invoice → Order (as-Code Function / Structure / input Invoice) and prove mesh.cat ≡ HTTP of cited slots (`cat0_bom`, `cat0_invoice`, `cat0_order`). `prov:used` is Order then generated Invoice (`cat0_execution_bind`). Data-plane hops are intra-run `stageLineage` (ingress ← input copy; later hops pointer-coherent). As-executed is **observation**, not a data hop (`cat0_stage3_*`).

    Mesh client and registry (`mesh_client`) and inspect helpers (`inspect_helpers`) are bound **above**. Inspect helpers stay off the mint path so editing asserts does not remint. CAS-only Node client (`ContentMesh(ipfsClient=None)`). Node up (`make node-start` / `make node-up`). See [`DEMO.md`](../docs/DEMO.md). Same I/O as [`old_cats_demo.py`](old_cats_demo.py); CAT0 does **not** call `flatten_bom`.

    **Acceptance criteria** (proven by the cells below):

    | Criterion | Proven by |
    |---|---|
    | Order is minted from local Process / InfraFunction / Structure / input data (**process provenance** bind) | `cat0_create_order` |
    | Node completes one loop and returns a signed BOM envelope (`content_id`, `bom_ldp_uri`, optional `hl` / `bom_solid_uri`) (**data provenance** record) | `cat0_submit_order` |
    | Registry disk ≡ HTTP index; projection complete; cited locators reachable. Dump: `to_consume` / `index_shape` / `locator_http`. This BOM is listed (`allow_ambiguous=True`) | `registry_index_parity` → `cat0_record`, `cat0_data_id` |
    | Response → registry → LDP BOM → Invoice → Order cohere; BOM mesh.cat ≡ HTTP (**data provenance**) | `cat0_bom` (`assert_control_plane_handoff_coherence`, `assert_bom_content_equiv`) |
    | Output Invoice `data` / `data_stages` / as-executed (**data provenance**); `seed` is Process replay dict (**process provenance**) | `cat0_invoice` |
    | Order Function / Structure slots (**process provenance**); nested input Invoice (**input data provenance**) | `cat0_order` |
    | `prov:used` is Order then output Invoice; GET `@id` ≡ handoff bodies (**process provenance** then **data provenance**) | `cat0_execution_bind` (`cat0_used_order`, `cat0_generated_invoice` inspect) |
    | `stageLineage` payload hops: URI-equal **or** directory-manifest `entries` equal (**intra-run data lineage**) | `cat0_stage_lineage_payload_equiv`; hops `cat0_stage0_ingress` … `cat0_stage2_egress` |
    | As-executed observation binds to Invoice SAE; Plant / InfraStructure slots hold (**data provenance** observation, not a data hop) | `cat0_stage3_structure_as_executed`, `cat0_stage3_plant_as_executed`, `cat0_stage3_infrastructure_as_executed` |

    Not in this section: `flatten_bom`; Function mutation / Structure carry / data chain (CAT1 **process / cross-CAT data lineage**); `linkStructure`; mesh-federated registry; dataframe transform checks (`tests/test_provenance.py`); “all HTTP content ∈ registry.”
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Compose Initial CAT Order request for CAT Node

    `create_order_request` returns `{content_id, order_uri, invoice_uri}` (endpoint
    defaults via `CAT_NODE_HOST` / `CAT_NODE_PORT`). HotF is `process_0` (**process
    provenance** of this run); the cell also binds `process_1` for CAT1 **process
    lineage** (`linkProcess`).
    """)
    return


@app.cell(hide_code=True)
def cat0_create_order(
    CATS_HOME,
    INPUT_DATA_HOME,
    INPUT_STRUCTURE_HOME,
    contentMesh,
    pprint,
):
    # Order Function sources live under repo-root data/, not the installed cats
    # package. Marimo cwd is notebooks/ — put CATS_HOME on sys.path so
    # `import data` resolves (do not put this path hack in cats/).
    import sys

    if CATS_HOME not in sys.path:
        sys.path.insert(0, CATS_HOME)

    from data.input.function.process import (
        egress,
        ingress,
        integration_cache,
        process_0,
        process_1,
    )
    from data.input.function.infrafunction import infrafunction_subproc

    cat0_order_request = contentMesh.create_order_request(
        ingress_subproc=ingress,
        integrated_subproc=process_0,
        egress_subproc=egress,
        integration_cache_subproc=integration_cache,
        infrafunction_subproc=infrafunction_subproc,
        data_dirpath=INPUT_DATA_HOME,
        structure_filepath=INPUT_STRUCTURE_HOME,
    )
    pprint(cat0_order_request)
    return cat0_order_request, process_1


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Submit Initial CAT Order request to CAT Node

    Mints the **data provenance** record for this run. Expect HTTP envelope keys
    `content_id`, `bom_ldp_uri`, optional `hl` / `bom_solid_uri`; signed `bom` with
    `invoice_uri` / `log_uri` / `node_did` + Data Integrity proof. **No** top-level
    envelope `invoice_uri` / `order_uri`. Inspected via
    registry / HTTP next instead of `flatten_bom`
    """)
    return


@app.cell(hide_code=True)
def cat0_submit_order(cat0_order_request, contentMesh):
    cat0_bom_response = contentMesh.catSubmit(cat0_order_request)
    cat0_bom_id = cat0_bom_response.get("content_id")
    cat0_bom_ldp_uri = cat0_bom_response.get("bom_ldp_uri")
    cat0_hl = cat0_bom_response.get("hl")
    return cat0_bom_id, cat0_bom_ldp_uri, cat0_bom_response, cat0_hl


@app.cell
def cat0_bom_response(cat0_bom_response):
    cat0_bom_response
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Registry post-execute checks (CAT0 → CAT1)

    After `catSubmit`, the same library helpers as unit tests. This **indexes the
    data-provenance record** so CAT1 can compose **lineage** from the catalog:

    1. **Index parity** — `BomRegistry` / `LocatorIndex` ≡ `GET /ldp/registry/…`
       (`assert_registry_index_parity`)
    2. **Projection complete** — required record fields, by-data / by-order,
       stage LocatorIndex URIs (`assert_handoff_projection_complete`)
    3. **Claims reachable** — record locators / `*_uri` resolve over HTTP
       (`assert_registry_claims_reachable`)

    Inspect dump is grouped `to_consume` / `index_shape` / `locator_http` (`_0`
    locators) — same shape as CAT1. Not “all HTTP content ∈ registry.” Envelope /
    lineage asserts continue in named inspect cells below. `allow_ambiguous=True`
    so re-runs with many BOMs per data digest still pass as long as *this* BOM is
    listed.
    """)
    return


@app.cell(hide_code=True)
def registry_index_parity(
    assert_handoff_projection_complete,
    assert_registry_claims_reachable,
    assert_registry_index_parity,
    cat0_bom_id,
    cat0_bom_ldp_uri,
    cat0_hl,
    http_get,
    http_get_json,
    locator_index,
    pprint,
    registry,
):
    # 1) Index parity: disk BomRegistry/LocatorIndex ≡ GET /ldp/registry/…
    _parity = assert_registry_index_parity(
        registry=registry,
        locator_index=locator_index,
        bom_id=cat0_bom_id,
        http_get_json=http_get_json,
        allow_ambiguous=True,
    )
    cat0_record = _parity["record"]
    cat0_data_id = _parity["data_id"]

    # 2) Projection complete: required fields + reverse indexes + stage locators.
    assert_handoff_projection_complete(
        registry,
        locator_index,
        bom_id=cat0_bom_id,
        require_stage_locators=True,
    )

    # 3) Claims reachable: record locators / *_uri resolve on the live Node.
    assert_registry_claims_reachable(
        cat0_record, http_get_json=http_get_json, http_get=http_get
    )

    # Hand off cat0_data_id (+ cat0_record) to CAT1 / named inspect cells.
    pprint(
        {
            "to_consume": {
                "cat0_data_id": cat0_data_id,
                "cat0_data_uri": cat0_record.get("data_uri"),
                "cat0_bom_id": cat0_bom_id,
                "cat0_bom_ldp_uri": cat0_bom_ldp_uri,
                "cat0_hl": cat0_hl,
            },
            "index_shape": {
                "lookup_bom": _parity["bom_ids_by_data"],
                "resolve_unique_bom": _parity["unique_bom"],
                "cat0_order_id": _parity["order_id"],
                "lookup_by_order": _parity["boms_for_order"],
            },
            "locator_http": {
                "locator_index_uris": _parity["data_locators"],
                "http_by_data": _parity["http_by_data"],
            },
            "asserts_ok": True,
        }
    )
    return cat0_data_id, cat0_record


@app.cell
def _(cat0_record):
    cat0_record
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Inspect CAT0 BOM & nested Envelopes

    **Data provenance** of this run: the signed ExecutionBom as the supply chain of
    evidence. CAT0 uses HTTP / registry locators only — **not** `flatten_bom`. Invoice URI
    is on the signed `bom`; Order URI is on that Invoice.

    **`assert_control_plane_handoff_coherence`** (control-plane handoff
    invariants): response → registry → LDP BOM → Invoice → Order —
    distinct from registry index parity above. Then **content equivalence**
    (`assert_*_content_equiv`: mesh.cat ≡ HTTP GET per allowlisted
    subcomponent — same helpers as `tests/test_content_equiv_*.py`, plus
    registry digest agreement when the record cites that stem).
    """)
    return


@app.cell(hide_code=True)
def cat0_bom(
    assert_bom_content_equiv,
    assert_control_plane_handoff_coherence,
    cat0_bom_response,
    cat0_record,
    contentMesh,
    http_get,
    http_get_json,
):
    # Control-plane handoff coherence (assert only — no flatten until fetch_ref exists).
    # Public name: marimo does not export leading-underscore locals to other cells.
    cat0_handoff = assert_control_plane_handoff_coherence(
        cat_response=cat0_bom_response,
        record=cat0_record,
        http_get_json=http_get_json,
        content_mesh=contentMesh,
    )
    fetch_ref = cat0_handoff["fetch_ref"]

    cat0_bom = cat0_handoff["bom"]
    assert_bom_content_equiv(
        cat0_bom,
        content_mesh=contentMesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record=cat0_record,
    )
    cat0_bom
    return cat0_bom, cat0_handoff, fetch_ref


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Inspect CAT0 Invoice Envelope

    **Data provenance** of the product bytes: Invoice `data` / `data_stages` /
    as-executed refs. **Process provenance** on the Invoice: `seed` is the Process
    replay dict. **`assert_invoice_content_equiv`**: mesh.cat ≡ HTTP GET per allowlisted
    Invoice subcomponent (same helpers as
    `tests/test_content_equiv_invoice.py`), plus registry digest agreement
    when the record cites that stem. Then **`flatten_uri_dict`** builds `cat0_flat_invoice` (assert and flatten stay separate). Stage refs live on Invoice `data_stages` (not on the execute log).
    """)
    return


@app.cell(hide_code=True)
def cat0_invoice(
    assert_invoice_content_equiv,
    cat0_handoff,
    cat0_record,
    contentMesh,
    fetch_ref,
    flatten_uri_dict,
    http_get,
    http_get_json,
    pprint,
):
    cat0_raw_invoice = cat0_handoff["invoice"]
    assert_invoice_content_equiv(
        cat0_raw_invoice,
        content_mesh=contentMesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record=cat0_record,
    )
    _invoice_stems = {
        "order",
        "data",
        "seed",
        "data_stages",
        "structure_as_executed",
        "egressed_data",
        "integrated_data",
        "ingressed_data",
    }
    cat0_flat_invoice = flatten_uri_dict(
        cat0_raw_invoice, fetch_ref, max_depth=2, stems=_invoice_stems
    )
    print("Invoice:")
    pprint(cat0_raw_invoice)
    cat0_flat_invoice
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Inspect CAT0 Order Envelope

    **Process provenance** of this run: Order Function / Structure pairing as-Code
    (what Process was bound, not a chain of Process versions). Nested input Invoice
    flatten is **input data provenance** (prior product bytes), not process lineage.
    Top-level Order: **`assert_order_content_equiv`** then **`flatten_uri_dict`** builds `cat0_flat_order` (assert and flatten stay separate).

    Nested Function / Structure / input Invoice:
    slot presence, then **content equivalence**
    (`assert_order_*_content_equiv`: mesh.cat ≡ HTTP GET of nested
    `*_uri`), then flatten. Input Invoice flatten does **not** use handoff
    `fetch_ref` (`data` would remap to registry egress).
    """)
    return


@app.cell(hide_code=True)
def cat0_order(
    assert_input_invoice_slots,
    assert_order_content_equiv,
    assert_order_function_content_equiv,
    assert_order_function_slots,
    assert_order_invoice_content_equiv,
    assert_order_structure_content_equiv,
    assert_order_structure_slots,
    cat0_handoff,
    cat0_record,
    contentMesh,
    http_get,
    http_get_json,
    requests,
):
    cat0_raw_order = cat0_handoff["order"]
    assert_order_content_equiv(
        cat0_raw_order,
        content_mesh=contentMesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record=cat0_record,
    )
    cat0_order_function_uri = cat0_raw_order["function_uri"]
    cat0_order_structure_uri = cat0_raw_order["structure_uri"]
    cat0_order_invoice_uri = cat0_raw_order["invoice_uri"]

    cat0_raw_function = requests.get(cat0_order_function_uri, timeout=60).json()
    assert_order_function_slots(cat0_raw_function)
    assert_order_function_content_equiv(
        cat0_raw_function,
        content_mesh=contentMesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record=cat0_record,
    )

    cat0_raw_structure = requests.get(cat0_order_structure_uri, timeout=60).json()
    assert_order_structure_slots(cat0_raw_structure)
    assert_order_structure_content_equiv(
        cat0_raw_structure,
        content_mesh=contentMesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record=cat0_record,
    )

    cat0_raw_ordered_invoice = requests.get(cat0_order_invoice_uri, timeout=60).json()
    assert_input_invoice_slots(cat0_raw_ordered_invoice)
    assert_order_invoice_content_equiv(
        cat0_raw_ordered_invoice,
        content_mesh=contentMesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record=cat0_record,
    )
    return (
        cat0_raw_function,
        cat0_raw_order,
        cat0_raw_ordered_invoice,
        cat0_raw_structure,
    )


@app.cell(hide_code=True)
def cat0_order_display(cat0_raw_order, fetch_ref, flatten_uri_dict, pprint):
    cat0_flat_order = flatten_uri_dict(
        cat0_raw_order,
        fetch_ref,
        max_depth=1,
        stems={"function", "structure", "invoice"},
    )
    print("Order:")
    pprint(cat0_raw_order)
    cat0_flat_order
    return


@app.cell(hide_code=True)
def cat0_function_display(
    cat0_raw_function,
    fetch_ref,
    flatten_uri_dict,
    pprint,
):
    cat0_flat_function = flatten_uri_dict(
        cat0_raw_function,
        fetch_ref,
        max_depth=1,
        stems={
            "infrafunction_source",
            "infrafunction",
            "process_source",
            "process",
        },
    )
    print("Function:")
    pprint(cat0_raw_function)
    cat0_flat_function
    return


@app.cell(hide_code=True)
def cat0_structure_display(
    cat0_raw_structure,
    fetch_ref,
    flatten_uri_dict,
    pprint,
):
    cat0_flat_structure = flatten_uri_dict(
        cat0_raw_structure,
        fetch_ref,
        max_depth=1,
        stems={"infrastructure", "plant", "root"},
    )
    print("Structure:")
    pprint(cat0_raw_structure)
    cat0_flat_structure
    return


@app.cell
def cat0_ordered_invoice_display(
    cat0_raw_ordered_invoice,
    flatten_uri_dict,
    http_get_json,
):
    # Do not use handoff fetch_ref: its ``data`` stem remaps to registry egress.
    cat0_flat_ordered_invoice = flatten_uri_dict(
        cat0_raw_ordered_invoice,
        lambda stem, uri: http_get_json(uri),
        max_depth=1,
        stems={"data"},
    )
    print("Ordered Invoice:")
    print(cat0_raw_ordered_invoice)
    cat0_flat_ordered_invoice
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Inspect CAT0 Execution Provenance

    **Data lineage (intra-run)** plus **provenance bind**. `stageLineage`: ingress ← input; integration ← ingress; data ← integration;
    then `structure_as_executed` (not on the payload chain). `prov:used` is
    Order then Invoice — **`assert_execution_bind`** (same helper as
    `tests/test_execution_bind.py`): Order is **process provenance**, Invoice is **data provenance**.

    Payload hops use **`assert_directory_manifest_equiv`** /
    **`assert_stage_lineage_payload_equiv`** (same helpers as
    `tests/test_manifest_equiv.py`): URI equal **or** directory-manifest
    `entries` equal — distinct from mesh≡HTTP content_equiv and from
    provenance DataFrame endpoint checks. As-executed observation is
    `cat0_stage3_*` (not a data hop).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Execution bind (`prov:used`)

    `assert_execution_bind`: `prov:used` is Order (**process provenance**) then output Invoice (**data provenance**). Identity
    is `contentId` or URI digest (`ldp/orders` vs `ldp/cas` OK). With
    `http_get_json`, GET each `@id` and require payload ≡ handoff Order / Invoice
    (pointer reachability). Inspect cells below fetch those bodies through the
    PROV pointers — slot presence stays in handoff / content-equiv.
    """)
    return


@app.cell
def cat0_execution_bind(
    assert_execution_bind,
    cat0_bom,
    cat0_handoff,
    http_get_json,
):
    execution_bind = assert_execution_bind(
        cat0_bom,
        order_uri=cat0_handoff["invoice"]["order_uri"],
        invoice_uri=cat0_handoff["invoice_uri"],
        http_get_json=http_get_json,
        expected_order=cat0_handoff["order"],
        expected_invoice=cat0_handoff["invoice"],
    )
    execution_bind
    return (execution_bind,)


@app.cell
def cat0_generated_invoice(execution_bind, requests):
    # prov:used[1] is the output Invoice (payload ≡ handoff already asserted).
    invoice_url = execution_bind[1]["@id"]
    invoice_resp = requests.get(invoice_url, timeout=60)
    invoice_resp.raise_for_status()
    generated_invoice = invoice_resp.json()
    generated_invoice
    return


@app.cell
def cat0_used_order(execution_bind, requests):
    # prov:used[0] is the Order (payload ≡ handoff already asserted).
    order_url = execution_bind[0]["@id"]
    order_resp = requests.get(order_url, timeout=60)
    order_resp.raise_for_status()
    used_order = order_resp.json()
    used_order
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Stage lineage payload hops (pointer coherence)

    **Intra-run data lineage** (not cross-CAT). `assert_stage_lineage_payload_equiv` walks BOM `stageLineage` entities that
    have `prov:wasDerivedFrom`:

    - **Ingress ← input** (first hop): stage `@id` ≡ derived-from `@id` (copy).
    - **Later payload hops**: derived-from `@id` ≡ previous stage `@id` — PROV
      pointer coherence, not transform output ≡ input.
    - Skips entities without `wasDerivedFrom` (e.g. `structure_as_executed`).

    Same helper as `tests/test_manifest_equiv.py`. Match is URI-equal **or**
    directory-manifest `entries` equal — distinct from mesh≡HTTP `content_equiv`
    and from provenance DataFrame checks. Per-stage cells below inspect each hop;
    `cat0_stage3_*` then inspect as-executed observation (**data provenance**, not a lineage hop).
    """)
    return


@app.cell
def cat0_stage_lineage_payload_equiv(
    assert_stage_lineage_payload_equiv,
    cat0_bom,
    http_get_json,
):
    assert_stage_lineage_payload_equiv(cat0_bom, http_get_json=http_get_json)
    return


@app.cell
def cat0_stage0_ingress(
    assert_directory_manifest_equiv,
    cat0_bom,
    http_get_json,
    requests,
):
    # stageLineage[0]: ingress_data ← input Invoice data
    ingress_stage = cat0_bom["stageLineage"][0]
    ingress_uri = ingress_stage["@id"]
    input_data_uri = ingress_stage["prov:wasDerivedFrom"]["@id"]

    ingressed_resp = requests.get(ingress_uri, timeout=60)
    ingressed_resp.raise_for_status()
    ingressed_data = ingressed_resp.json()

    assert_directory_manifest_equiv(
        ingress_uri, input_data_uri, http_get_json=http_get_json
    )
    print("ingress_data wasDerivedFrom input_data: ok")
    ingressed_data
    return (ingress_uri,)


@app.cell
def cat0_stage1_integration(
    assert_directory_manifest_equiv,
    cat0_bom,
    http_get_json,
    ingress_uri,
    requests,
):
    # stageLineage[1]: integration_data ← ingress_data
    integration_stage = cat0_bom["stageLineage"][1]
    integration_uri = integration_stage["@id"]
    _integration_derived_from_uri = integration_stage["prov:wasDerivedFrom"]["@id"]

    integration_resp = requests.get(integration_uri, timeout=60)
    integration_resp.raise_for_status()
    integration_data = integration_resp.json()

    assert_directory_manifest_equiv(
        _integration_derived_from_uri,
        ingress_uri,
        http_get_json=http_get_json,
    )
    print("integration_data wasDerivedFrom ingress_data: ok")
    integration_data
    return (integration_uri,)


@app.cell
def cat0_stage2_egress(
    assert_directory_manifest_equiv,
    cat0_bom,
    http_get_json,
    integration_uri,
    requests,
):
    # stageLineage[2]: Invoice data (egress) ← integration_data
    egressed_stage = cat0_bom["stageLineage"][2]
    _egressed_data_uri = egressed_stage["@id"]
    _egressed_derived_from_uri = egressed_stage["prov:wasDerivedFrom"]["@id"]

    egressed_resp = requests.get(_egressed_data_uri, timeout=60)
    egressed_resp.raise_for_status()
    egressed_data = egressed_resp.json()

    assert_directory_manifest_equiv(
        _egressed_derived_from_uri,
        integration_uri,
        http_get_json=http_get_json,
    )
    print("data wasDerivedFrom integration_data: ok")
    egressed_data
    return


@app.cell
def cat0_stage3_structure_as_executed(
    assert_structure_as_executed_bind,
    assert_structure_as_executed_slots,
    cat0_bom,
    cat0_handoff,
    http_get_json,
    requests,
):
    # Observation entity (no wasDerivedFrom): SAE ≡ Invoice structure_as_executed.
    _sae_uri = cat0_handoff["invoice"]["structure_as_executed_uri"]
    _sae_entity = assert_structure_as_executed_bind(
        cat0_bom,
        structure_as_executed_uri=_sae_uri,
        http_get_json=http_get_json,
        expected_structure_as_executed=http_get_json(_sae_uri),
    )
    structure_as_executed_resp = requests.get(_sae_entity["@id"], timeout=60)
    structure_as_executed_resp.raise_for_status()
    structure_as_executed = structure_as_executed_resp.json()
    assert_structure_as_executed_slots(structure_as_executed)
    structure_as_executed
    return (structure_as_executed,)


@app.cell
def cat0_stage3_plant_as_executed(
    assert_plant_as_executed_snapshot,
    cat0_handoff,
    ref_id,
    requests,
    structure_as_executed,
):
    plant_as_executed_uri = structure_as_executed["plant_as_executed_uri"]
    plant_as_executed_resp = requests.get(plant_as_executed_uri, timeout=60)
    plant_as_executed_resp.raise_for_status()
    plant_as_executed = plant_as_executed_resp.json()
    assert_plant_as_executed_snapshot(
        plant_as_executed,
        structure_id=ref_id(cat0_handoff["order"], "structure"),
    )
    plant_as_executed
    return


@app.cell
def cat0_stage3_infrastructure_as_executed(
    assert_infrastructure_as_executed_slots,
    pprint,
    requests,
    structure_as_executed,
):
    infrastructure_as_executed_uri = structure_as_executed[
        "infrastructure_as_executed_uri"
    ]
    infrastructure_resp = requests.get(
        infrastructure_as_executed_uri, timeout=60
    )
    infrastructure_resp.raise_for_status()
    infrastructure_as_executed = infrastructure_resp.json()
    assert_infrastructure_as_executed_slots(infrastructure_as_executed)

    object_store_as_executed_uri = infrastructure_as_executed[
        "object_store_as_executed_uri"
    ]
    object_store_resp = requests.get(object_store_as_executed_uri, timeout=60)
    object_store_resp.raise_for_status()
    object_store_as_executed = object_store_resp.json()

    pprint(infrastructure_as_executed)
    object_store_as_executed
    return


@app.cell(hide_code=True)
def cat1_inspection(mo):
    mo.md(r"""
    ### Control-Feedback Loop Execution of CAT1 — process lineage via registry (`content_id=`) 🐈

    **Value:** a collaborator can compose the **next** CAT from the Node-local registry CAT0 wrote — not a held `cat_response`, not a second `create_order_request` — mutating **Function** while carrying **Structure** and CAT0’s output **data**. The chain is content equality plus the index (which BOM produced this digest); there is no BOM→BOM pointer in the bytes.

    **Demonstrates:** **process lineage** (`linkProcess`: Function mutated `process_0` → `process_1`, Structure carried); **cross-CAT data lineage** (CAT1 input Invoice data ≡ CAT0 output data); a **new data-provenance** BOM (indexed, not a CAT0 locator-walk replay); **new process provenance** (CAT1 seed ≠ CAT0 seed).

    **Control-Feedback Loop** (this section’s purpose: *compose from the index, then prove lineage*):

    1. **Order** — `linkProcess` is the lineage operator (`cat1_link_process`). Intake is CAT0’s data digest (`content_id=cat0_data_id`); fall back to `bom_ldp_uri=` when `by-data` is ambiguous. Rebuilds Function (`process_1` as hotF), carries Structure, chains Invoice data equality.
    2. **Factory → Executor** — `catSubmit` runs the same manufactured-execution loop on that Order (`cat1_submit_order`). Envelope shape matches CAT0 (locators + signed `bom`; **no** top-level `invoice_uri` / `order_uri`).
    3. **Runtime → BOM + registry** — the Node emits a new signed ExecutionBom and indexes **this** BOM (`cat1_registry_index_parity`). Same suite and dump grouping as CAT0 (`to_consume` / `index_shape` / `locator_http`, `_1` locators). Separate from submit so re-running checks does not mint another CAT1.
    4. **Feedback inspect (`flatten_bom` tree)** — `{invoice, log}` with uri slots + parent `flat` (`cat1_flatten_bom`). **Process lineage:** Function mutated, Structure carried (`assert_order_pairing_lineage`). **Cross-CAT data lineage:** CAT1 **input** Invoice data ≡ CAT0 **output** data (`assert_invoice_data_chain`: `order.flat.invoice`, not the Executor **output** Invoice). **New data provenance / process provenance:** output data and seeds differ (`assert_distinct_executions`).

    `mesh_client` / `inspect_helpers` are bound **above**. `tests/test_lineage.py` covers the three lineage helpers; `tests/test_provenance.py` CAT1 is a second `create_order_request(process_1)` (not `linkProcess` data-chain). Do **not** replay CAT0 envelope / stage / as-executed inspect.

    **Acceptance criteria** (proven by the cells below):

    | Criterion | Proven by |
    |---|---|
    | Next Order is composed from the registry (`content_id=` or `bom_ldp_uri=` fallback), not a held envelope (**process lineage** + **cross-CAT data lineage** intake) | `cat1_link_process` |
    | Node completes one loop and returns a signed BOM envelope (**new data provenance** record) | `cat1_submit_order` |
    | `flatten_bom` tree is the CAT1 inspect surface (does not mutate the envelope) | `cat1_flatten_bom` |
    | Registry disk ≡ HTTP index for the **new** BOM; dump grouped like CAT0 | `cat1_registry_index_parity` |
    | Function mutated; Structure carried (**process lineage**) | `cat1_function_structure` (`assert_order_pairing_lineage`) |
    | CAT1 input Invoice data ≡ CAT0 output data (**cross-CAT data lineage**) | `cat1_data_chain` (`assert_invoice_data_chain`) |
    | New execution: CAT1 output data ≠ CAT0 (**new data provenance**); seeds differ (**new process provenance**) | `cat1_new_execution` (`assert_distinct_executions`) |

    Not in this section: CAT0 locator walk / `stageLineage` / as-executed / content-equiv; a second `create_order_request`; `linkStructure`; mesh-federated registry; dataframe transform checks (`tests/test_provenance.py`).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Compose CAT1 Order from the registry

    **Process lineage** intake: `linkProcess` mutates Function (`process_1`) and
    carries Structure. **Cross-CAT data lineage** intake: CAT0 output data becomes
    CAT1 input (`content_id=` / `bom_ldp_uri=`). Not a second `create_order_request`.
    """)
    return


@app.cell
def cat1_link_process(
    cat0_bom_ldp_uri,
    cat0_data_id,
    contentMesh,
    pprint,
    process_1,
    registry,
):
    # content_id= requires a unique by-data hit; re-runs often need bom_ldp_uri=.
    if len(registry.lookup_bom(cat0_data_id)) == 1:
        cat1_order_request = contentMesh.linkProcess(
            content_id=cat0_data_id,
            integrated_subproc=process_1,
        )
        link_mode = "content_id"
    else:
        cat1_order_request = contentMesh.linkProcess(
            bom_ldp_uri=cat0_bom_ldp_uri,
            integrated_subproc=process_1,
        )
        link_mode = "bom_ldp_uri (ambiguous data)"
    pprint({"link_mode": link_mode, **cat1_order_request})
    return (cat1_order_request,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Submit CAT1 Order request to CAT Node

    Mints a **new data-provenance** BOM (not a CAT0 inspect replay). Expect HTTP
    envelope keys `content_id`, `bom_ldp_uri`, optional `hl` / `bom_solid_uri`;
    signed `bom` with `invoice_uri` / `log_uri` / `node_did` + Data Integrity proof.
    **No** top-level envelope `invoice_uri` / `order_uri`. Inspect via `flatten_bom`
    next (not CAT0-style HTTP walk).
    """)
    return


@app.cell
def cat1_submit_order(cat1_order_request, contentMesh):
    cat1_bom_response = contentMesh.catSubmit(cat1_order_request)
    cat1_bom_id = cat1_bom_response.get("content_id")
    cat1_bom_ldp_uri = cat1_bom_response.get("bom_ldp_uri")
    cat1_hl = cat1_bom_response.get("hl")
    cat1_bom_response
    return cat1_bom_id, cat1_bom_ldp_uri, cat1_bom_response, cat1_hl


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Flatten CAT1 BOM (inspect tree)

    `flatten_bom` returns `{invoice, log}`: uri slots stay on each JSON parent;
    fetched JSON is nested under that parent's `flat`. It does **not** mutate the
    submit envelope. Lineage cells below read this tree — **process lineage**
    (`assert_order_pairing_lineage`), **cross-CAT data lineage**
    (`assert_invoice_data_chain`), and distinct-execution (**new data provenance** of
    output data; **new process provenance** of seeds) (`assert_distinct_executions`) — not CAT0-style HTTP inspect.
    """)
    return


@app.cell
def cat1_flatten_bom(cat1_bom_response, contentMesh):
    cat1_flat_bom = contentMesh.flatten_bom(cat1_bom_response)
    cat1_flat_bom
    return (cat1_flat_bom,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Registry post-execute checks (CAT1)

    Same library helpers as CAT0 / unit tests, **separate from submit**, on **this**
    BOM — index the **new data-provenance** record (not a replay of CAT0 hops):

    1. **Index parity** — `assert_registry_index_parity`
    2. **Projection complete** — `assert_handoff_projection_complete`
    3. **Claims reachable** — `assert_registry_claims_reachable`

    Inspect dump is the same grouping as CAT0: `to_consume` / `index_shape` /
    `locator_http` (`_1` locators). `allow_ambiguous=True` for re-runs.
    """)
    return


@app.cell
def cat1_registry_index_parity(
    assert_handoff_projection_complete,
    assert_registry_claims_reachable,
    assert_registry_index_parity,
    cat1_bom_id,
    cat1_bom_ldp_uri,
    cat1_hl,
    http_get,
    http_get_json,
    locator_index,
    pprint,
    registry,
):
    # Same registry post-execute checks as CAT0 (parity → projection → reachability).
    _parity_1 = assert_registry_index_parity(
        registry=registry,
        locator_index=locator_index,
        bom_id=cat1_bom_id,
        http_get_json=http_get_json,
        allow_ambiguous=True,
    )
    cat1_record = _parity_1["record"]
    cat1_data_id = _parity_1["data_id"]
    assert_handoff_projection_complete(
        registry,
        locator_index,
        bom_id=cat1_bom_id,
        require_stage_locators=True,
    )
    assert_registry_claims_reachable(
        cat1_record, http_get_json=http_get_json, http_get=http_get
    )
    # Same grouped inspect dump as CAT0 registry_index_parity (_1 locators).
    pprint(
        {
            "to_consume": {
                "cat1_data_id": cat1_data_id,
                "cat1_data_uri": cat1_record.get("data_uri"),
                "cat1_bom_id": cat1_bom_id,
                "cat1_bom_ldp_uri": cat1_bom_ldp_uri,
                "cat1_hl": cat1_hl,
            },
            "index_shape": {
                "lookup_bom": _parity_1["bom_ids_by_data"],
                "resolve_unique_bom": _parity_1["unique_bom"],
                "order_id_1": _parity_1["order_id"],
                "lookup_by_order": _parity_1["boms_for_order"],
            },
            "locator_http": {
                "locator_index_uris": _parity_1["data_locators"],
                "http_by_data": _parity_1["http_by_data"],
            },
            "asserts_ok": True,
        }
    )
    cat1_record
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### CAT1 lineage vs CAT0

    **Process lineage:** Function mutated (`process_0` → `process_1`), Structure carried (`cat1_function_structure`, `assert_order_pairing_lineage`).
    **Cross-CAT data lineage:** CAT1 input Invoice data ≡ CAT0 output Invoice data (`cat1_data_chain`, `assert_invoice_data_chain`).
    **New data provenance:** CAT1 output data ≠ CAT0 (`cat1_new_execution`, `assert_distinct_executions`).
    **New process provenance:** CAT1 seed (Process replay dict) ≠ CAT0 seed (`cat1_new_execution`, `assert_distinct_executions`). Same helpers as
    `tests/test_lineage.py` (and `test_link_*` / `test_provenance.py` where they apply).
    """)
    return


@app.cell
def cat1_function_structure(
    assert_order_pairing_lineage,
    cat0_handoff,
    cat1_flat_bom,
):
    pairing_lineage = assert_order_pairing_lineage(
        cat0_handoff["order"],
        cat1_flat_bom["invoice"]["flat"]["order"],
        function="mutated",
        structure="carried",
    )
    pairing_lineage
    return


@app.cell
def cat1_data_chain(assert_invoice_data_chain, cat0_handoff, cat1_flat_bom):
    # CAT1 Order input Invoice (not Executor output Invoice).
    data_chain = assert_invoice_data_chain(
        cat0_handoff["invoice"],
        cat1_flat_bom["invoice"]["flat"]["order"]["flat"]["invoice"],
    )
    data_chain
    return


@app.cell
def cat1_new_execution(
    assert_distinct_executions,
    cat0_handoff,
    cat1_flat_bom,
    http_get_json,
):
    _seed0 = http_get_json(cat0_handoff["invoice"]["seed_uri"])
    _seed1 = cat1_flat_bom["invoice"]["flat"]["seed"]
    distinct_executions = assert_distinct_executions(
        cat0_handoff["invoice"],
        cat1_flat_bom["invoice"],
        prior_seed=_seed0,
        next_seed=_seed1,
    )
    distinct_executions
    return


if __name__ == "__main__":
    app.run()
