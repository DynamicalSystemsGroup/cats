import marimo

__generated_with = "0.23.13"
app = marimo.App()


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # BOM projections (P2 / P3 / P4 / P5 / P6 / P7)

    Catalog-first: read a prior execute envelope from the Node-local registry,
    project SPDX 3 / CycloneDX 1.6 / DCAT 3 / SysML v2 / data-contract /
    allocate-view into CAS. P2, P5, P6, and P7 **do not remint** Order or
    Invoice. P3/P4 cells below read Invoice `runtime_sbom_uri` and Order eBOM
    `*_sbom_uri` stems when a `CATS_SBOM=1` mint has already attached them.
    **Living §6u demo** — P8 adds cells here; do not fold into
    [`cats_lineage_demo.py`](cats_lineage_demo.py) (CFL walk, flag-off).

    Resolve Invoice from signed `bom.invoice_uri` (never a top-level execute
    `invoice_uri`). Live P2 proof: re-run byte-stable except Syft timestamps;
    `GET /ldp/cas/<hex>` on the Node; print `syft_elapsed`.
    """)
    return


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def mesh_client():
    from pathlib import Path

    import requests

    from cats import CATS_HOME, CONTENT_MESH as contentMesh
    from cats.network.bom import (
        project_allocate_view,
        project_bom,
        project_data_lot,
        project_sysml_quantum,
        validate_sysml_quantum,
    )
    from cats.network.bom.read import stem_id
    from cats.network.bom.rtm import (
        break_backward_copy,
        drop_order_conforms_copy,
        load_rtm,
        validate_backward,
        validate_forward,
    )
    from cats.network.cas import LocatorIndex, cas_ldp_uri, from_ni
    from cats.network.registry import BomRegistry

    registry = BomRegistry(CATS_HOME)
    locator_index = LocatorIndex(CATS_HOME)
    uv_lock_path = Path(CATS_HOME) / "uv.lock"
    uv_lock = uv_lock_path.read_bytes() if uv_lock_path.is_file() else None
    return (
        break_backward_copy,
        cas_ldp_uri,
        contentMesh,
        drop_order_conforms_copy,
        from_ni,
        load_rtm,
        locator_index,
        project_allocate_view,
        project_bom,
        project_sysml_quantum,
        registry,
        requests,
        stem_id,
        uv_lock,
        validate_backward,
        validate_forward,
        validate_sysml_quantum,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Catalog intake

    Newest registry BOM (or set `content_id=`). Reconstruct `{content_id, bom,
    bom_ldp_uri}` from the record — no held CAT0/CAT1 envelope required.
    Run the lineage demo first if the index is empty.
    """)
    return


@app.cell
def catalog_envelope(registry, requests):
    bom_ids = registry.list_boms()
    if not bom_ids:
        raise RuntimeError(
            "BomRegistry is empty — run notebooks/cats_lineage_demo.py "
            "(CAT0 catSubmit) first"
        )
    content_id = bom_ids[0]
    record = registry.get(content_id)
    if not record:
        raise RuntimeError(f"registry miss for {content_id}")
    locs = record.get("locators") or {}
    bom_ldp_uri = locs.get("bom_ldp_uri")
    if not bom_ldp_uri:
        raise RuntimeError("record missing locators.bom_ldp_uri")
    bom_resp = requests.get(bom_ldp_uri, timeout=60)
    bom_resp.raise_for_status()
    cat_response = {
        "content_id": content_id,
        "bom": bom_resp.json(),
        "bom_ldp_uri": bom_ldp_uri,
    }
    print(f"catalog BOM {content_id}")
    print("invoice_uri (signed)", cat_response["bom"].get("invoice_uri"))
    return cat_response, record


@app.cell
def inspect_flat(cat_response, contentMesh):
    flat = contentMesh.flatten_bom(cat_response)
    invoice = flat.get("invoice") or {}
    bag = invoice.get("flat") or {}
    order = bag.get("order") or {}
    print("flatten_bom stems:", sorted(bag))
    print(
        "order eBOM uris:",
        {
            k: bool(order.get(k))
            for k in (
                "function_sbom_uri",
                "structure_sbom_uri",
                "input_data_sbom_uri",
            )
        },
    )
    flat
    return invoice, order


@app.cell
def project(cat_response, contentMesh, project_bom, record, uv_lock):
    projections = project_bom(
        cat_response,
        contentMesh,
        record=record,
        uv_lock=uv_lock,
    )
    projections
    return (projections,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### P2 live proof

    Observational — print / compare, not pytest. Unit tests already cover
    the fixture ABI (`invoice_uri`, fail-open Syft, no BOM `content_id`).
    This walk uses the catalog BOM: (1) second `project_bom` — `ni:` match
    except `runtime_syft`; (2) Node `GET /ldp/cas/<hex>` equals local CAS
    bytes; (3) `syft_elapsed` / whether Syft wrote a CAS original.
    """)
    return


@app.cell
def rerun_stable(
    cat_response,
    contentMesh,
    project_bom,
    projections,
    record,
    uv_lock,
):
    _STABLE = (
        "function_spdx",
        "structure_spdx",
        "runtime_cdx",
        "data_contract",
        "data_dcat",
        "data_spdx",
    )
    projections_again = project_bom(
        cat_response,
        contentMesh,
        record=record,
        uv_lock=uv_lock,
    )
    rerun = {
        "stable": {
            key: {
                "first": projections.get(key),
                "second": projections_again.get(key),
                "match": projections.get(key) == projections_again.get(key),
            }
            for key in _STABLE
        },
        "runtime_syft": {
            "first": projections.get("runtime_syft"),
            "second": projections_again.get("runtime_syft"),
            "note": "Syft JSON timestamps may differ; not part of the byte-stable exit",
        },
    }
    print("stable matches:", {k: v["match"] for k, v in rerun["stable"].items()})
    print(
        "runtime_syft first/second:",
        rerun["runtime_syft"]["first"],
        rerun["runtime_syft"]["second"],
    )
    rerun
    return


@app.cell
def fetch_cas(
    cas_ldp_uri,
    contentMesh,
    from_ni,
    locator_index,
    projections,
    requests,
):
    import json as _json

    fetched = {}
    for name, ni in projections.items():
        if name == "syft_elapsed" or not isinstance(ni, str):
            continue
        local = contentMesh.catObj(ni)
        hex_digest = from_ni(ni)
        cas_uri = cas_ldp_uri(hex_digest)
        locators = locator_index.lookup_uris(ni)
        resp = requests.get(cas_uri, timeout=60)
        fetched[name] = {
            "content_id": ni,
            "cas_hex": hex_digest,
            "cas_uri": cas_uri,
            "locators": locators,
            "http_status": resp.status_code,
            "matches_local": resp.content == local,
            "document": _json.loads(local.decode("utf-8")),
        }
    print(
        "Node GET matches local:",
        {k: v["matches_local"] and v["http_status"] == 200 for k, v in fetched.items()},
    )
    fetched
    return


@app.cell
def syft_timing(projections):
    syft_timing = {
        "syft_elapsed": projections.get("syft_elapsed"),
        "runtime_syft": projections.get("runtime_syft"),
        "syft_ran": projections.get("runtime_syft") is not None,
        "note": (
            "P3 gate: record wall time before promoting Syft onto "
            "Executor.execute. None elapsed means Syft was skipped (fail-open)."
        ),
    }
    print("syft_elapsed", syft_timing["syft_elapsed"])
    print("runtime_syft", syft_timing["runtime_syft"])
    print("syft_ran", syft_timing["syft_ran"])
    syft_timing
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### P3 aBOM stem (`CATS_SBOM=1`)

    Flag-on remint is **this** notebook's evidence path.
    [`cats_lineage_demo.py`](cats_lineage_demo.py) stays flag-off.

    If the catalog Invoice already has `runtime_sbom_uri`, GET the nest then
    CycloneDX / optional Syft. Otherwise remint **once** with `CATS_SBOM=1`
    (do not leave the flag on for CFL notebooks), then re-run catalog intake.
    """)
    return


@app.cell
def p3_invoice_stem(invoice):
    runtime_sbom_uri = invoice.get("runtime_sbom_uri")
    if runtime_sbom_uri:
        print("runtime_sbom_uri", runtime_sbom_uri)
    else:
        print(
            "No runtime_sbom_uri on this catalog Invoice (CATS_SBOM was off). "
            "Remint once with CATS_SBOM=1 (leave cats_lineage_demo.py flag-off), "
            "then re-run catalog intake."
        )
    return (runtime_sbom_uri,)


@app.cell
def p3_fetch_stem(requests, runtime_sbom_uri):
    runtime_sbom = {"nest_uri": runtime_sbom_uri, "documents": {}}
    if not runtime_sbom_uri:
        print("skip P3 GET — no runtime_sbom_uri")
    else:
        _nest_resp = requests.get(runtime_sbom_uri, timeout=60)
        _nest_resp.raise_for_status()
        _nest = _nest_resp.json()
        runtime_sbom["nest"] = _nest
        for _stem in ("cyclonedx", "syft"):
            _uri = _nest.get(f"{_stem}_uri")
            if not _uri:
                continue
            _got = requests.get(_uri, timeout=60)
            runtime_sbom["documents"][_stem] = {
                "uri": _uri,
                "http_status": _got.status_code,
                "document": _got.json() if _got.ok else None,
            }
        print(
            "P3 GET",
            {k: v["http_status"] for k, v in runtime_sbom["documents"].items()},
        )
    runtime_sbom
    return (runtime_sbom,)


@app.cell
def p3_syft(runtime_sbom):
    _nest = runtime_sbom.get("nest") or {}
    p3_syft = {
        "skipped": not runtime_sbom.get("nest_uri"),
        "syft_uri": _nest.get("syft_uri"),
        "syft_on_invoice": bool(_nest.get("syft_uri")),
        "note": (
            "Invoice stem does not store wall time. After a CATS_SBOM=1 remint, "
            "re-run the P2 syft_timing cell (or read Executor logs) for "
            "syft_elapsed — that is the P3 fast-enough evidence."
        ),
    }
    print("skipped", p3_syft["skipped"])
    print("syft_on_invoice", p3_syft["syft_on_invoice"])
    print("syft_uri", p3_syft["syft_uri"])
    p3_syft
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### P4 eBOM stems (`CATS_SBOM=1`)

    Same flag as P3. If the catalog Order already has `function_sbom_uri` /
    `structure_sbom_uri` / `input_data_sbom_uri`, GET each (and the input nest).
    Otherwise remint once with `CATS_SBOM=1` (leave
    [`cats_lineage_demo.py`](cats_lineage_demo.py) flag-off), then re-run catalog
    intake. Do not remint inside this notebook.
    """)
    return


@app.cell
def p4_order_stems(order):
    ebom_uris = {
        "function_sbom_uri": order.get("function_sbom_uri"),
        "structure_sbom_uri": order.get("structure_sbom_uri"),
        "input_data_sbom_uri": order.get("input_data_sbom_uri"),
    }
    if all(ebom_uris.values()):
        print("eBOM stems", ebom_uris)
    else:
        print(
            "No eBOM sbom URIs on this catalog Order (CATS_SBOM was off). "
            "Remint once with CATS_SBOM=1 (leave cats_lineage_demo.py flag-off), "
            "then re-run catalog intake."
        )
    ebom_uris
    return (ebom_uris,)


@app.cell
def p4_fetch_stems(ebom_uris, requests):
    ebom_docs = {"uris": ebom_uris, "documents": {}}
    if not all(ebom_uris.values()):
        print("skip P4 GET — Order lacks function/structure/input_data sbom URIs")
    else:
        for _stem in ("function_sbom", "structure_sbom"):
            _uri = ebom_uris[f"{_stem}_uri"]
            _got = requests.get(_uri, timeout=60)
            ebom_docs["documents"][_stem] = {
                "uri": _uri,
                "http_status": _got.status_code,
                "document": _got.json() if _got.ok else None,
            }
        _nest_uri = ebom_uris["input_data_sbom_uri"]
        _nest_resp = requests.get(_nest_uri, timeout=60)
        _nest_resp.raise_for_status()
        _nest = _nest_resp.json()
        ebom_docs["nest"] = _nest
        ebom_docs["documents"]["input_data_sbom"] = {
            "uri": _nest_uri,
            "http_status": _nest_resp.status_code,
            "document": _nest,
        }
        for _nested in ("dcat", "spdx"):
            _uri = _nest.get(f"{_nested}_uri")
            if not _uri:
                continue
            _got = requests.get(_uri, timeout=60)
            ebom_docs["documents"][_nested] = {
                "uri": _uri,
                "http_status": _got.status_code,
                "document": _got.json() if _got.ok else None,
            }
        print(
            "P4 GET",
            {k: v["http_status"] for k, v in ebom_docs["documents"].items()},
        )
    ebom_docs
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### P5 SysML v2 eBOM view

    Compile the minimal Quantum (six part defs, five INTEROP ports, one
    `ArchitecturalQuantum` usage) **from** this catalog Order into CAS JSON-LD.
    Factory / Executor do not read the file. Stale `contentId` fails the check,
    not `execute`. Do not remint.
    """)
    return


@app.cell
def p5_sysml(
    contentMesh,
    invoice,
    order,
    project_sysml_quantum,
    stem_id,
    validate_sysml_quantum,
):
    import json as _json

    sysml = {"skipped": True}
    _order_id = stem_id(invoice, "order")
    _fn = (order.get("flat") or {}).get("function") or {}
    _st = (order.get("flat") or {}).get("structure") or {}
    if not _order_id or not order.get("function_uri") or not order.get("structure_uri"):
        print("need a catalog Order")
    else:
        sysml_id = project_sysml_quantum(
            order,
            contentMesh,
            order_id=_order_id,
            function=_fn or None,
            structure=_st or None,
        )
        sysml_doc = _json.loads(contentMesh.cat(sysml_id))
        validate_sysml_quantum(
            sysml_doc,
            order,
            order_id=_order_id,
            function=_fn or None,
            structure=_st or None,
        )
        _parts = [
            item["name"]
            for item in sysml_doc.get("ownedElement") or []
            if item.get("@type") == "sysml:PartDefinition"
        ]
        _ports = [
            item["name"]
            for item in sysml_doc.get("ownedElement") or []
            if item.get("@type") == "sysml:PortDefinition"
        ]
        sysml = {
            "skipped": False,
            "content_id": sysml_id,
            "part_defs": _parts,
            "port_defs": _ports,
            "valid": True,
            "document": sysml_doc,
        }
        print("sysml", sysml_id)
        print("parts", _parts)
        print("ports", _ports)
        print("validate", True)
    sysml
    return (sysml,)


@app.cell
def p5_fetch(
    cas_ldp_uri,
    contentMesh,
    from_ni,
    locator_index,
    requests,
    sysml,
):
    sysml_fetch = {"skipped": True}
    if sysml.get("skipped") or not sysml.get("content_id"):
        print("skip P5 GET — need a catalog Order")
    else:
        _ni = sysml["content_id"]
        _local = contentMesh.catObj(_ni)
        _hex = from_ni(_ni)
        _cas_uri = cas_ldp_uri(_hex)
        _got = requests.get(_cas_uri, timeout=60)
        sysml_fetch = {
            "skipped": False,
            "content_id": _ni,
            "cas_uri": _cas_uri,
            "locators": locator_index.lookup_uris(_ni),
            "http_status": _got.status_code,
            "matches_local": _got.content == _local,
        }
        print(
            "P5 GET",
            sysml_fetch["http_status"],
            "matches_local",
            sysml_fetch["matches_local"],
        )
    sysml_fetch
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### P6 data contract (cite only)

    Thin ODCS-shaped spec node in CAS. DCAT 3 stays the promise
    (`dct:conformsTo` = contract `@id`). Flag-off catalog Invoice — do not
    remint with `CATS_SBOM=1`. Factory does not read this file.
    """)
    return


@app.cell
def p6_contract(contentMesh, projections):
    import json as _json

    contract = {"skipped": True}
    _contract_ni = projections.get("data_contract")
    _dcat_ni = projections.get("data_dcat")
    if not _contract_ni or not _dcat_ni:
        print("skip P6 — need a catalog Invoice (run project_bom)")
    else:
        _contract_doc = _json.loads(contentMesh.cat(_contract_ni))
        _dcat_doc = _json.loads(contentMesh.cat(_dcat_ni))
        contract = {
            "skipped": False,
            "content_id": _contract_ni,
            "@id": _contract_doc.get("@id"),
            "conformsTo": _dcat_doc.get("dct:conformsTo"),
            "allocatesTo": [
                clause.get("cats:allocatesTo")
                for clause in _contract_doc.get("cats:clauses") or []
            ],
            "document": _contract_doc,
        }
        print("contract", contract["content_id"])
        print("@id", contract["@id"])
        print("dct:conformsTo", contract["conformsTo"])
        print("allocatesTo", contract["allocatesTo"])
    contract
    return (contract,)


@app.cell
def p6_fetch(
    cas_ldp_uri,
    contentMesh,
    contract,
    from_ni,
    locator_index,
    requests,
):
    contract_fetch = {"skipped": True}
    if contract.get("skipped") or not contract.get("content_id"):
        print("skip P6 GET — need a catalog Invoice")
    else:
        _ni = contract["content_id"]
        _local = contentMesh.catObj(_ni)
        _hex = from_ni(_ni)
        _cas_uri = cas_ldp_uri(_hex)
        _got = requests.get(_cas_uri, timeout=60)
        contract_fetch = {
            "skipped": False,
            "content_id": _ni,
            "cas_uri": _cas_uri,
            "locators": locator_index.lookup_uris(_ni),
            "http_status": _got.status_code,
            "matches_local": _got.content == _local,
        }
        print(
            "P6 GET",
            contract_fetch["http_status"],
            "matches_local",
            contract_fetch["matches_local"],
        )
    contract_fetch
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### P7 bidirectional RTM

    Allocate view (CAS) joins each P6 clause to a P5 Process usage /
    concern. Order and Invoice DCAT share one contract `@id`
    (`dct:conformsTo`). Then walk **forward** (clause → port / mBOM
    promise) and **backward** (egressed `ni:` → clause). Local Dataset
    SHACL is optional (`cats[rtm]`); skip those cells if the extra is
    missing. Flag-off catalog — do not remint here. Order cite needs the
    P4 `CATS_SBOM=1` nest when present.
    """)
    return


@app.cell
def p7_allocate(contentMesh, contract, project_allocate_view, sysml):
    import json as _json

    allocate = {"skipped": True}
    if sysml.get("skipped") or contract.get("skipped"):
        print("skip P7 allocate — need P5 SysML and P6 contract")
    else:
        _sysml_doc = sysml["document"]
        _contract_doc = contract["document"]
        allocate_id = project_allocate_view(_sysml_doc, _contract_doc, contentMesh)
        allocate_doc = _json.loads(contentMesh.cat(allocate_id))
        allocate = {
            "skipped": False,
            "content_id": allocate_id,
            "@id": allocate_doc.get("@id"),
            "edges": [
                {
                    "clause": edge.get("@id"),
                    "allocatesTo": edge.get("cats:allocatesTo"),
                }
                for edge in allocate_doc.get("cats:edges") or []
            ],
            "allocatedFrom": [
                {
                    "target": item.get("@id"),
                    "clause": item.get("cats:allocatedFrom"),
                }
                for item in allocate_doc.get("cats:targets") or []
            ],
            "document": allocate_doc,
        }
        print("allocate", allocate["content_id"])
        print("@id", allocate["@id"])
        print("allocatesTo", [edge["allocatesTo"] for edge in allocate["edges"]])
        print(
            "allocatedFrom",
            [item["clause"] for item in allocate["allocatedFrom"]],
        )
    allocate
    return (allocate,)


@app.cell
def p7_allocate_fetch(
    allocate,
    cas_ldp_uri,
    contentMesh,
    from_ni,
    locator_index,
    requests,
):
    allocate_fetch = {"skipped": True}
    if allocate.get("skipped") or not allocate.get("content_id"):
        print("skip P7 GET — need allocate view")
    else:
        _ni = allocate["content_id"]
        _local = contentMesh.catObj(_ni)
        _hex = from_ni(_ni)
        _cas_uri = cas_ldp_uri(_hex)
        _got = requests.get(_cas_uri, timeout=60)
        allocate_fetch = {
            "skipped": False,
            "content_id": _ni,
            "cas_uri": _cas_uri,
            "locators": locator_index.lookup_uris(_ni),
            "http_status": _got.status_code,
            "matches_local": _got.content == _local,
        }
        print(
            "P7 GET",
            allocate_fetch["http_status"],
            "matches_local",
            allocate_fetch["matches_local"],
        )
    allocate_fetch
    return


@app.cell
def p7_shared_cite(allocate, contract, order, requests):
    import json as _json

    shared = {"skipped": True}
    if contract.get("skipped") or allocate.get("skipped"):
        print("skip P7 cite — need P6 contract")
    else:
        _invoice_urn = contract.get("conformsTo")
        _order_urn = None
        _order_dcat = None
        _nest_uri = order.get("input_data_sbom_uri")
        if _nest_uri:
            _nest = requests.get(_nest_uri, timeout=60)
            _nest.raise_for_status()
            _dcat_uri = _nest.json().get("dcat_uri")
            if _dcat_uri:
                _order_dcat = requests.get(_dcat_uri, timeout=60)
                _order_dcat.raise_for_status()
                _order_urn = _order_dcat.json().get("dct:conformsTo")
        else:
            print(
                "No input_data_sbom_uri on this catalog Order (CATS_SBOM was off). "
                "Remint once with CATS_SBOM=1 (leave cats_lineage_demo.py flag-off), "
                "then re-run catalog intake."
            )
        shared = {
            "skipped": False,
            "invoice_conformsTo": _invoice_urn,
            "order_conformsTo": _order_urn,
            "order_dcat": _order_dcat.json() if _order_urn else None,
            "match": bool(_order_urn) and _order_urn == _invoice_urn,
            "contract_id": contract.get("@id"),
        }
        print("invoice dct:conformsTo", shared["invoice_conformsTo"])
        print("order dct:conformsTo", shared["order_conformsTo"])
        print("shared", shared["match"])
    shared
    return (shared,)


@app.cell
def p7_forward(allocate, shared):
    from cats.network.bom.rtm import walk_forward

    forward = {"skipped": True}
    if allocate.get("skipped"):
        print("skip P7 forward — need allocate view")
    else:
        _order_dcat = None
        if shared.get("order_conformsTo"):
            _order_dcat = {"dct:conformsTo": shared["order_conformsTo"]}
        elif not shared.get("skipped"):
            print("Order DCAT cite skipped — flag-off catalog (P4 remint)")
        forward = walk_forward(allocate["document"], order_dcat=_order_dcat)
        forward["skipped"] = False
        print("clause", forward["clause"])
        print("target", forward["target"])
        print("order_promised", forward["order_promised"])
    forward
    return


@app.cell
def p7_backward(allocate, contract, invoice, stem_id):
    from cats.network.bom.rtm import walk_backward

    backward = {"skipped": True}
    if allocate.get("skipped") or contract.get("skipped"):
        print("skip P7 backward — need allocate view and Invoice DCAT")
    else:
        _lot = stem_id(invoice, "data")
        _invoice_dcat = {
            "dct:conformsTo": contract.get("conformsTo"),
            "dcat:dataset": [
                {"dct:title": "egressed_data", "dct:identifier": _lot}
            ],
        }
        backward = walk_backward(
            allocate["document"], _invoice_dcat, lot=_lot
        )
        backward["skipped"] = False
        print("lot", backward["lot"])
        print("contract", backward["contract"])
        print("clause", backward["clause"])
    backward
    return


@app.cell
def p7_shacl(
    allocate,
    cat_response,
    contentMesh,
    contract,
    load_rtm,
    projections,
    runtime_sbom,
    shared,
    sysml,
    validate_backward,
    validate_forward,
):
    import json as _json

    from cats.network.bom.rtm import has_attestation as _has_attestation
    from cats.network.bom.rtm import has_earl_automatic as _has_earl_automatic

    shacl = {"skipped": True, "extra": False}
    if allocate.get("skipped") or contract.get("skipped") or sysml.get("skipped"):
        print("skip P7 SHACL — need joins")
    else:
        try:
            _invoice_dcat = _json.loads(contentMesh.cat(projections["data_dcat"]))
            _order_dcat = shared.get("order_dcat")
            if not isinstance(_order_dcat, dict):
                _order_dcat = {
                    "@id": "urn:cats:demo:order-dcat",
                    "@type": "dcat:Catalog",
                    "dct:conformsTo": contract.get("@id"),
                }
            _dataset = load_rtm(
                sysml_doc=sysml["document"],
                allocate_doc=allocate["document"],
                contract_doc=contract["document"],
                order_dcat=_order_dcat,
                invoice_dcat=_invoice_dcat,
                bom=cat_response.get("bom") or {},
                runtime_sbom=runtime_sbom if isinstance(runtime_sbom, dict) else None,
            )
            _fwd = validate_forward(_dataset)
            _bwd = validate_backward(_dataset)
            shacl = {
                "skipped": False,
                "extra": True,
                "forward": {
                    "conforms": _fwd["conforms"],
                    "shape": _fwd["shape"],
                    "focus": _fwd["focus"],
                },
                "backward": {
                    "conforms": _bwd["conforms"],
                    "shape": _bwd["shape"],
                    "focus": _bwd["focus"],
                },
                "earl_automatic": _has_earl_automatic(_dataset),
                "attestation": _has_attestation(_dataset),
                "dataset": _dataset,
            }
            print("forward", shacl["forward"])
            print("backward", shacl["backward"])
            print("earl:automatic", shacl["earl_automatic"])
            print("rtm:Attestation", shacl["attestation"])
        except ImportError:
            print("skip P7 Dataset — install cats[rtm] (rdflib, pyshacl)")
    shacl
    return (shacl,)


@app.cell
def p7_forward_fail(
    drop_order_conforms_copy,
    shacl,
    validate_backward,
    validate_forward,
):
    forward_fail = {"skipped": True}
    if shacl.get("skipped") or not shacl.get("extra"):
        print("skip P7 Forward fail — need Dataset")
    else:
        _broken = drop_order_conforms_copy(shacl["dataset"])
        _fwd = validate_forward(_broken)
        _bwd = validate_backward(_broken)
        forward_fail = {
            "skipped": False,
            "forward_conforms": _fwd["conforms"],
            "backward_conforms": _bwd["conforms"],
            "shape": _fwd["shape"],
            "focus": _fwd["focus"],
            "note": "mBOM did not promise the contract",
        }
        print("Forward-only fail", not _fwd["conforms"] and _bwd["conforms"])
        print("shape", forward_fail["shape"], "focus", forward_fail["focus"])
    forward_fail
    return


@app.cell
def p7_backward_fail(
    break_backward_copy,
    shacl,
    validate_backward,
    validate_forward,
):
    backward_fail = {"skipped": True}
    if shacl.get("skipped") or not shacl.get("extra"):
        print("skip P7 Backward fail — need Dataset")
    else:
        _broken = break_backward_copy(shacl["dataset"])
        _fwd = validate_forward(_broken)
        _bwd = validate_backward(_broken)
        backward_fail = {
            "skipped": False,
            "forward_conforms": _fwd["conforms"],
            "backward_conforms": _bwd["conforms"],
            "shape": _bwd["shape"],
            "focus": _bwd["focus"],
            "note": "lot has no Invoice DCAT conformsTo or allocate inverse",
        }
        print("Backward-only fail", _fwd["conforms"] and not _bwd["conforms"])
        print("shape", backward_fail["shape"], "focus", backward_fail["focus"])
    backward_fail
    return


@app.cell
def p7_rerun(cat_response, runtime_sbom, shacl):
    from cats.network.bom.rtm import interrogate

    rerun_steps = {"skipped": True}
    _bom = cat_response.get("bom") or {}
    _steps = interrogate.rerun(_bom, shacl.get("dataset") if not shacl.get("skipped") else None)
    rerun_steps = {
        "skipped": False,
        "steps": _steps,
        "syft_on_invoice": bool((runtime_sbom.get("nest") or {}).get("syft_uri"))
        if isinstance(runtime_sbom, dict)
        else False,
        "note": "walks prov:wasGeneratedBy → p-plan steps; does not re-sign",
    }
    print("rerun", rerun_steps["steps"])
    print("syft_on_invoice", rerun_steps["syft_on_invoice"])
    rerun_steps
    return


if __name__ == "__main__":
    app.run()
