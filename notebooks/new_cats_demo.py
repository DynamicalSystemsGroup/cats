import marimo

__generated_with = "0.23.13"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Execute Initial CAT0 (registry-first)

    Same Control-Feedback I/O as [`cats_demo.py`](cats_demo.py), but **CAT0 does not
    call `flatten_bom`**. After `catSubmit`, inspect via registry lookups + HTTP GETs
    (named cells below). **`flatten_bom` is used only for CAT1.**

    CAS-only Node client (`ContentMesh(ipfsClient=None)`). Prerequisites:
    Node up (`make node-start` / `make node-up`). See [`DEMO.md`](../docs/DEMO.md).

    ##### Instantiate CAT Mesh Client + registry helpers
    """)
    return


@app.cell
def _():
    from pprint import pprint

    import requests

    from cats import CATS_HOME, CONTENT_MESH as contentMesh
    from cats import INPUT_STRUCTURE_HOME, INPUT_DATA_HOME
    from cats.network.cas import LocatorIndex, flatten_uri_dict
    from cats.network.cas import (
        assert_directory_manifest_equiv,
        assert_stage_lineage_payload_equiv,
    )
    from cats.network.node_http import _node_base_url
    from cats.network.registry import (
        BomRegistry,
        assert_bom_content_equiv,
        assert_control_plane_handoff_coherence,
        assert_handoff_projection_complete,
        assert_input_invoice_slots,
        assert_invoice_content_equiv,
        assert_order_content_equiv,
        assert_order_function_slots,
        assert_order_structure_slots,
        assert_registry_claims_reachable,
        assert_registry_index_parity,
    )

    registry = BomRegistry(CATS_HOME)
    locator_index = LocatorIndex(CATS_HOME)
    node_base = _node_base_url()

    def http_get_json(path):
        """GET Node path relative to `_node_base_url()` → JSON."""
        url = path if path.startswith("http") else f"{node_base}{path}"
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def http_get(path):
        """GET Node path → raw bytes (opaque data_uri / stage payloads)."""
        url = path if path.startswith("http") else f"{node_base}{path}"
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content

    return (
        CATS_HOME,
        INPUT_DATA_HOME,
        INPUT_STRUCTURE_HOME,
        assert_bom_content_equiv,
        assert_control_plane_handoff_coherence,
        assert_directory_manifest_equiv,
        assert_handoff_projection_complete,
        assert_input_invoice_slots,
        assert_invoice_content_equiv,
        assert_order_content_equiv,
        assert_order_function_slots,
        assert_order_structure_slots,
        assert_registry_claims_reachable,
        assert_registry_index_parity,
        assert_stage_lineage_payload_equiv,
        contentMesh,
        flatten_uri_dict,
        http_get,
        http_get_json,
        locator_index,
        pprint,
        registry,
        requests,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Compose Initial CAT Order request for CAT Node

    `create_order_request` returns `{content_id, order_uri, invoice_uri}` (endpoint
    defaults via `CAT_NODE_HOST` / `CAT_NODE_PORT`).
    """)
    return


@app.cell
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

    cat_order_request_0 = contentMesh.create_order_request(
        ingress_subproc=ingress,
        integrated_subproc=process_0,
        egress_subproc=egress,
        integration_cache_subproc=integration_cache,
        infrafunction_subproc=infrafunction_subproc,
        data_dirpath=INPUT_DATA_HOME,
        structure_filepath=INPUT_STRUCTURE_HOME,
    )
    pprint(cat_order_request_0)
    return cat_order_request_0, process_1


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Submit Initial CAT Order request to CAT Node

    Expect HTTP envelope keys `content_id`, `bom_ldp_uri`, optional `hl` /
    `bom_solid_uri`; signed `bom` with `invoice_uri` / `log_uri` / `node_did` +
    Data Integrity proof. **No `flatten_bom`** — inspect via registry / HTTP next.
    """)
    return


@app.cell
def cat0_submit_order(cat_order_request_0, contentMesh, pprint):
    cat_invoiced_response_0 = contentMesh.catSubmit(cat_order_request_0)
    pprint(cat_invoiced_response_0)
    bom_id_0 = cat_invoiced_response_0.get("content_id")
    bom_ldp_uri_0 = cat_invoiced_response_0.get("bom_ldp_uri")
    hl_0 = cat_invoiced_response_0.get("hl")
    return bom_id_0, bom_ldp_uri_0, cat_invoiced_response_0, hl_0


@app.cell
def _(cat_invoiced_response_0):
    cat_invoiced_response_0
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Registry post-execute checks (CAT0 → CAT1)

    After `catSubmit`, the same library helpers as unit tests:

    1. **Index parity** — `BomRegistry` / `LocatorIndex` ≡ `GET /ldp/registry/…`
       (`assert_registry_index_parity`)
    2. **Projection complete** — required record fields, by-data / by-order,
       stage LocatorIndex URIs (`assert_handoff_projection_complete`)
    3. **Claims reachable** — record locators / `*_uri` resolve over HTTP
       (`assert_registry_claims_reachable`)

    Not “all HTTP content ∈ registry.” Envelope / lineage asserts continue in
    named inspect cells below. `allow_ambiguous=True` so re-runs with many BOMs
    per data digest still pass as long as *this* BOM is listed.
    """)
    return


@app.cell
def registry_index_parity(
    assert_handoff_projection_complete,
    assert_registry_claims_reachable,
    assert_registry_index_parity,
    bom_id_0,
    bom_ldp_uri_0,
    hl_0,
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
        bom_id=bom_id_0,
        http_get_json=http_get_json,
        allow_ambiguous=True,
    )
    record_0 = _parity["record"]
    data_id_0 = _parity["data_id"]

    # 2) Projection complete: required fields + reverse indexes + stage locators.
    assert_handoff_projection_complete(
        registry,
        locator_index,
        bom_id=bom_id_0,
        require_stage_locators=True,
    )

    # 3) Claims reachable: record locators / *_uri resolve on the live Node.
    assert_registry_claims_reachable(
        record_0, http_get_json=http_get_json, http_get=http_get
    )

    # Hand off data_id_0 (+ record_0) to CAT1 / named inspect cells.
    pprint(
        {
            "data_id_0": data_id_0,
            "data_uri_0": record_0.get("data_uri"),
            "bom_id_0": bom_id_0,
            "bom_ldp_uri_0": bom_ldp_uri_0,
            "hl_0": hl_0,
            "lookup_bom": _parity["bom_ids_by_data"],
            "resolve_unique_bom": _parity["unique_bom"],
            "order_id_0": _parity["order_id"],
            "lookup_by_order": _parity["boms_for_order"],
            "locator_index_uris": _parity["data_locators"],
            "http_by_data": _parity["http_by_data"],
            "asserts_ok": True,
        }
    )
    return data_id_0, record_0


@app.cell
def _(record_0):
    record_0
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Inspect CAT0 BOM & nested Envelopes

    CAT0 uses HTTP / registry locators only — **not** `flatten_bom`.

    Asserts use **`assert_control_plane_handoff_coherence`** (control-plane
    handoff invariants): response → registry → LDP BOM → Invoice → Order —
    distinct from registry index parity above. Then **content equivalence**
    (`assert_*_content_equiv`: mesh.cat ≡ HTTP GET per allowlisted
    subcomponent). Then **`flatten_uri_dict`** builds `flat_order0` /
    `flat_invoice0` (assert and flatten stay separate).
    """)
    return


@app.cell
def cat0_cp_handoff(
    assert_control_plane_handoff_coherence,
    cat_invoiced_response_0,
    contentMesh,
    http_get_json,
    record_0,
):
    # Control-plane handoff coherence (assert only — no flatten).
    _handoff = assert_control_plane_handoff_coherence(
        cat_response=cat_invoiced_response_0,
        record=record_0,
        http_get_json=http_get_json,
        content_mesh=contentMesh,
    )
    bom0 = _handoff["bom"]
    locs = _handoff["locators"]
    raw_invoice0 = _handoff["invoice"]
    raw_order0 = _handoff["order"]
    # Slot URIs already asserted present on Order by handoff coherence.
    order0_function_uri = raw_order0["function_uri"]
    order0_structure_uri = raw_order0["structure_uri"]
    order0_invoice_uri = raw_order0["invoice_uri"]
    # Public name: marimo does not export leading-underscore locals to other cells.
    fetch_ref = _handoff["fetch_ref"]
    return (
        bom0,
        fetch_ref,
        order0_function_uri,
        order0_invoice_uri,
        order0_structure_uri,
        raw_invoice0,
        raw_order0,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Content equivalence (mesh ≡ HTTP)

    Same helpers as `tests/test_content_equiv_*.py`: for each allowlisted
    BOM / Invoice / Order subcomponent, `contentMesh.cat` ≡ HTTP GET of
    `*_uri` (plus registry digest agreement when the record cites that
    stem). Distinct from handoff coherence above and from flatten below.
    """)
    return


@app.cell
def cat0_content_equiv(
    assert_bom_content_equiv,
    assert_invoice_content_equiv,
    assert_order_content_equiv,
    bom0,
    contentMesh,
    http_get,
    http_get_json,
    raw_invoice0,
    raw_order0,
    record_0,
):
    assert_bom_content_equiv(
        bom0,
        content_mesh=contentMesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record=record_0,
    )
    assert_invoice_content_equiv(
        raw_invoice0,
        content_mesh=contentMesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record=record_0,
    )
    assert_order_content_equiv(
        raw_order0,
        content_mesh=contentMesh,
        http_get_json=http_get_json,
        http_get=http_get,
        record=record_0,
    )
    return


@app.cell
def _(bom0):
    bom0
    return


@app.cell
def cat0_invoice(fetch_ref, flatten_uri_dict, pprint, raw_invoice0):
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
    flat_invoice0 = flatten_uri_dict(
        raw_invoice0, fetch_ref, max_depth=2, stems=_invoice_stems
    )

    print("Invoice:")
    pprint(raw_invoice0)
    flat_invoice0
    return


@app.cell
def cat0_order(fetch_ref, flatten_uri_dict, pprint, raw_order0):
    flat_order0 = flatten_uri_dict(
        raw_order0,
        fetch_ref,
        max_depth=1,
        stems={"function", "structure", "invoice"},
    )

    print("Order:")
    pprint(raw_order0)
    flat_order0
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### Inspect CAT0 Order Envelope
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    #### CAT0 Order's Function Envelope
    """)
    return


@app.cell
def cat0_ordered_function(
    assert_order_function_slots, order0_function_uri, pprint, requests
):
    raw_function0 = requests.get(order0_function_uri, timeout=60).json()
    assert_order_function_slots(raw_function0)

    infrafunction_source_uri = raw_function0["infrafunction_source_uri"]
    infrafunction_uri = raw_function0["infrafunction_uri"]
    process_source_uri = raw_function0["process_source_uri"]
    process_uri = raw_function0["process_uri"]

    flat_function0 = {
        "infrafunction_source": requests.get(infrafunction_source_uri, timeout=60).json(),
        "infrafunction": requests.get(infrafunction_uri, timeout=60).json(),
        "process_source": requests.get(process_source_uri, timeout=60).json(),
        "process": requests.get(process_uri, timeout=60).json(),
    }

    print("Function:")
    pprint(raw_function0)
    print()

    print("Flat Function:")
    pprint(flat_function0)
    print()
    return


@app.cell
def _(mo):
    mo.md(r"""
    #### CAT0 Order's Structure Envelope
    """)
    return


@app.cell
def cat0_ordered_structure(
    assert_order_structure_slots, order0_structure_uri, pprint, requests
):
    raw_structure0 = requests.get(order0_structure_uri, timeout=60).json()
    assert_order_structure_slots(raw_structure0)

    infrastructure_uri = raw_structure0["infrastructure_uri"]
    plant_uri = raw_structure0["plant_uri"]
    root_uri = raw_structure0["root_uri"]

    flat_structure0 = {
        "infrastructure": requests.get(infrastructure_uri, timeout=60).json(),
        "plant": requests.get(plant_uri, timeout=60).json(),
        "root": requests.get(root_uri, timeout=60).json(),
    }

    print("Structure:")
    pprint(raw_structure0)
    print()

    print("Flat Structure:")
    pprint(flat_structure0)
    print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### CAT0 Order's Invoice Envelope
    """)
    return


@app.cell(hide_code=True)
def cat0_ordered_invoice(
    assert_input_invoice_slots, order0_invoice_uri, pprint, requests
):
    raw_ordered_invoice0 = requests.get(order0_invoice_uri, timeout=60).json()
    assert_input_invoice_slots(raw_ordered_invoice0)
    _ordered_invoice_data_uri = raw_ordered_invoice0["data_uri"]
    flat_ordered_invoice0 = {
        "data": requests.get(_ordered_invoice_data_uri, timeout=60).json()
    }
    print("Ordered Invoice:")
    pprint(raw_ordered_invoice0)
    print()
    print("Flat Ordered Invoice:")
    pprint(flat_ordered_invoice0)
    print()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Inspect CAT0 Execution Provenance

    `stageLineage`: ingress ← input; integration ← ingress; data ← integration;
    then `structure_as_executed` (not on the payload chain). `prov:used` is
    Order then Invoice.

    Payload hops use **`assert_directory_manifest_equiv`** /
    **`assert_stage_lineage_payload_equiv`** (same helpers as
    `tests/test_manifest_equiv.py`): URI equal **or** directory-manifest
    `entries` equal — distinct from mesh≡HTTP content_equiv and from
    provenance DataFrame endpoint checks.
    """)
    return


@app.cell
def cat0_used_executor(bom0):
    used = bom0["prov:wasGeneratedBy"]["prov:used"]
    executor = used if isinstance(used, list) else [used]
    assert len(executor) >= 2
    assert executor[0].get("@id") and executor[1].get("@id")
    executor
    return (executor,)


@app.cell
def cat0_used_invoice(executor, requests):
    # prov:used[1] is the output Invoice.
    invoice_url = executor[1]["@id"]
    invoice_resp = requests.get(invoice_url, timeout=60)
    invoice_resp.raise_for_status()
    used_invoice = invoice_resp.json()
    assert used_invoice.get("data_uri") and used_invoice.get("order_uri")
    used_invoice
    return


@app.cell
def cat0_used_order(executor, requests):
    # prov:used[0] is the Order.
    order_url = executor[0]["@id"]
    order_resp = requests.get(order_url, timeout=60)
    order_resp.raise_for_status()
    used_order = order_resp.json()
    assert used_order.get("function_uri") and used_order.get("structure_uri")
    used_order
    return


@app.cell
def cat0_stage_lineage_payload_equiv(assert_stage_lineage_payload_equiv, bom0, http_get_json):
    # Shared helper (same as tests/test_manifest_equiv.py): ingress ≡ input;
    # later hops — wasDerivedFrom ≡ prior stage (pointer coherence).
    assert_stage_lineage_payload_equiv(bom0, http_get_json=http_get_json)
    return


@app.cell
def cat0_stage0_ingress(assert_directory_manifest_equiv, bom0, http_get_json, requests):
    # stageLineage[0]: ingress_data ← input Invoice data
    ingress_stage = bom0["stageLineage"][0]
    ingress_uri = ingress_stage["@id"]
    input_data_uri = ingress_stage["prov:wasDerivedFrom"]["@id"]
    assert ingress_uri and input_data_uri

    ingress_data = requests.get(ingress_uri, timeout=60).json()
    input_data = requests.get(input_data_uri, timeout=60).json()
    assert ingress_data is not None and input_data is not None

    assert_directory_manifest_equiv(
        ingress_uri, input_data_uri, http_get_json=http_get_json
    )
    print("ingress_data wasDerivedFrom input_data: ok")
    input_data
    return (ingress_uri,)


@app.cell
def cat0_stage1_integration(
    assert_directory_manifest_equiv,
    bom0,
    http_get_json,
    ingress_uri,
    requests,
):
    # stageLineage[1]: integration_data ← ingress_data
    integration_stage = bom0["stageLineage"][1]
    integration_uri = integration_stage["@id"]
    _integration_derived_from_uri = integration_stage["prov:wasDerivedFrom"]["@id"]
    assert integration_uri and _integration_derived_from_uri

    integration_data = requests.get(integration_uri, timeout=60).json()
    _integration_derived_from_data = requests.get(
        _integration_derived_from_uri, timeout=60
    ).json()
    assert integration_data is not None and _integration_derived_from_data is not None

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
    bom0,
    http_get_json,
    integration_uri,
    requests,
):
    # stageLineage[2]: Invoice data (egress) ← integration_data
    egressed_stage = bom0["stageLineage"][2]
    _egressed_data_uri = egressed_stage["@id"]
    _egressed_derived_from_uri = egressed_stage["prov:wasDerivedFrom"]["@id"]
    assert _egressed_data_uri and _egressed_derived_from_uri

    egressed_data = requests.get(_egressed_data_uri, timeout=60).json()
    _egressed_derived_from_data = requests.get(
        _egressed_derived_from_uri, timeout=60
    ).json()
    assert egressed_data is not None and _egressed_derived_from_data is not None

    assert_directory_manifest_equiv(
        _egressed_derived_from_uri,
        integration_uri,
        http_get_json=http_get_json,
    )
    print("data wasDerivedFrom integration_data: ok")
    egressed_data
    return


@app.cell
def cat0_stage3_structure_as_executed(bom0, requests):
    # stageLineage[3]: structure_as_executed (not on the payload derivation chain)
    structure_as_executed_stage = bom0["stageLineage"][3]
    structure_as_executed_uri = structure_as_executed_stage["@id"]
    assert structure_as_executed_uri
    structure_as_executed = requests.get(structure_as_executed_uri, timeout=60).json()
    assert structure_as_executed.get("plant_as_executed_uri")
    assert structure_as_executed.get("infrastructure_as_executed_uri")
    structure_as_executed
    return (structure_as_executed,)


@app.cell
def cat0_stage3_plant_as_executed(requests, structure_as_executed):
    plant_as_executed_uri = structure_as_executed["plant_as_executed_uri"]
    plant_as_executed_resp = requests.get(plant_as_executed_uri, timeout=60)
    plant_as_executed_resp.raise_for_status()
    plant_as_executed = plant_as_executed_resp.json()
    plant_as_executed
    return


@app.cell
def cat0_stage3_infrastructure_as_executed(
    pprint,
    requests,
    structure_as_executed,
):
    infrastructure_as_executed_uri = structure_as_executed[
        "infrastructure_as_executed_uri"
    ]
    infrastructure_as_executed = requests.get(
        infrastructure_as_executed_uri, timeout=60
    ).json()

    object_store_as_executed_uri = infrastructure_as_executed[
        "object_store_as_executed_uri"
    ]
    assert object_store_as_executed_uri
    object_store_as_executed = requests.get(
        object_store_as_executed_uri, timeout=60
    ).json()

    pprint(object_store_as_executed)
    infrastructure_as_executed
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Execute CAT1 — Function lineage via registry (`content_id=`)

    CAT1 is **not** a fresh Order on the input tree. `linkProcess(content_id=data_id_0)`
    rebuilds Function (`process_1` as hotF), carries Structure, and chains CAT0
    Invoice **data** equality — **no** held `cat_response`.

    Falls back to `bom_ldp_uri=` when `by-data` is ambiguous (re-runs).
    After submit, **`flatten_bom` is used for CAT1 only**.
    """)
    return


@app.cell
def _(bom_ldp_uri_0, contentMesh, data_id_0, pprint, process_1, registry):
    # content_id= requires a unique by-data hit; re-runs often need bom_ldp_uri=.
    if len(registry.lookup_bom(data_id_0)) == 1:
        cat_order_request_1 = contentMesh.linkProcess(
            content_id=data_id_0,
            integrated_subproc=process_1,
        )
        link_mode = "content_id"
    else:
        cat_order_request_1 = contentMesh.linkProcess(
            bom_ldp_uri=bom_ldp_uri_0,
            integrated_subproc=process_1,
        )
        link_mode = "bom_ldp_uri (ambiguous data)"
    pprint({"link_mode": link_mode, **cat_order_request_1})
    return (cat_order_request_1,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Submit CAT1 Order request to CAT Node
    """)
    return


@app.cell
def _(
    assert_handoff_projection_complete,
    assert_registry_claims_reachable,
    assert_registry_index_parity,
    cat_order_request_1,
    contentMesh,
    http_get,
    http_get_json,
    locator_index,
    pprint,
    registry,
):
    cat_invoiced_response_1 = contentMesh.catSubmit(cat_order_request_1)
    pprint(cat_invoiced_response_1)
    flat_cat_invoiced_response_1 = contentMesh.flatten_bom(cat_invoiced_response_1)
    pprint(flat_cat_invoiced_response_1)

    bom_id_1 = cat_invoiced_response_1.get("content_id")
    # Same registry post-execute checks as CAT0 (parity → projection → reachability).
    _parity_1 = assert_registry_index_parity(
        registry=registry,
        locator_index=locator_index,
        bom_id=bom_id_1,
        http_get_json=http_get_json,
        allow_ambiguous=True,
    )
    record_1 = _parity_1["record"]
    data_id_1 = _parity_1["data_id"]
    assert_handoff_projection_complete(
        registry,
        locator_index,
        bom_id=bom_id_1,
        require_stage_locators=True,
    )
    assert_registry_claims_reachable(
        record_1, http_get_json=http_get_json, http_get=http_get
    )

    pprint(
        {
            "content_id": bom_id_1,
            "bom_ldp_uri": cat_invoiced_response_1.get("bom_ldp_uri"),
            "hl": cat_invoiced_response_1.get("hl"),
            "data_id_1": data_id_1,
            "data_uri_1": record_1.get("data_uri"),
            "lookup_bom(data_1)": _parity_1["bom_ids_by_data"],
            "list_boms_newest": registry.list_boms()[:5],
            "asserts_ok": True,
        }
    )
    return


if __name__ == "__main__":
    app.run()
