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
    ### Execute Initial CAT0
    CAS-only Node client (`ContentMesh(ipfsClient=None)`). New Order graph slots are
    HTTP `*_uri` with `ni:` equality — not Kubo / legacy CIDs.

    ##### Instantiate CAT Mesh Client
    """)
    return


@app.cell
def _():
    import requests
    from pprint import pprint
    from copy import deepcopy

    from cats import CONTENT_MESH as contentMesh
    from cats import INPUT_STRUCTURE_HOME, INPUT_DATA_HOME

    return INPUT_DATA_HOME, INPUT_STRUCTURE_HOME, contentMesh, pprint, requests


@app.cell
def _(requests):
    def content_address_uri_equivalence(manafest_uri, dataset_uri):
        return manafest_uri == dataset_uri

    datasets = lambda xs: sorted(e["entries"] for e in (xs if isinstance(xs, list) else [xs]))
    def content_address_named_entry_equivalence(manafest_uri, dataset_uri):
        manafest = requests.get(manafest_uri).json()
        dataset = requests.get(dataset_uri).json()
        return datasets(manafest) == datasets(dataset)

    def content_address_equivalence(manafest_uri, dataset_uri):
        uri_equivalence = content_address_uri_equivalence(manafest_uri, dataset_uri)
        named_entry_equivalence = content_address_named_entry_equivalence(manafest_uri, dataset_uri)
        return uri_equivalence & named_entry_equivalence

    return (content_address_equivalence,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Compose Initial CAT Order request for CAT Node

    `create_order_request` returns `{content_id, order_uri, invoice_uri}` (endpoint
    defaults via `CAT_NODE_HOST` / `CAT_NODE_PORT`).
    """)
    return


@app.cell
def _(INPUT_DATA_HOME, INPUT_STRUCTURE_HOME, contentMesh):
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
    cat_order_request_0
    return cat_order_request_0, process_1


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Submit Initial CAT Order request to CAT Node

    Expect HTTP envelope keys `content_id`, `bom_ldp_uri`, optional `hl` /
    `bom_solid_uri`; signed `bom` with `invoice_uri` / `log_uri` / `node_did` +
    Data Integrity proof. CAT1 `flatten_bom` returns `{invoice, log}` with
    uri slots kept and fetched JSON under `flat` (does not mutate the envelope).
    """)
    return


@app.cell
def _(cat_order_request_0, contentMesh):
    cat_bom_response_0 = contentMesh.catSubmit(cat_order_request_0)
    # cat_bom_response_0
    # pprint(cat_bom_response_0)
    # flat_cat_response_0 = contentMesh.flatten_bom(cat_bom_response_0)
    # pprint(flat_cat_response_0)
    return (cat_bom_response_0,)


@app.cell
def _(contentMesh):
    from cats.network.registry import BomRegistry

    reg = BomRegistry(contentMesh.CATS_HOME)  # or cats.CATS_HOME
    ni = "ni:///sha-256;ChLj43XqspB8LvAJylJk2KBV-e99Vc9r5t5oCo8Z8TU"


    record = reg.get(ni)                      # projected index record
    record
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Inspect CAT0 BOM & nested Envelopes
    """)
    return


@app.cell
def cat0_bom(cat_bom_response_0, pprint, requests):
    bom0_ldp_uri = cat_bom_response_0.get("bom_ldp_uri") or {}
    bom0 = requests.get(bom0_ldp_uri).json()

    invoice0_uri = bom0.get("invoice_uri")
    raw_invoice0 = requests.get(invoice0_uri).json()

    order0_uri = raw_invoice0.get("order_uri")
    output_data_uri = raw_invoice0.get('data_uri')
    seed_uri = raw_invoice0.get('seed_uri')

    invoice0 = {
        'order0_uri': raw_invoice0.get("order_uri"),
        'output_data_uri': raw_invoice0.get('data_uri'),
        'seed_uri': raw_invoice0.get('seed_uri')
    }

    flat_invoice0 = {
        'order0_uri': order0_uri,        
        'output_data': requests.get(output_data_uri).json(),
        'seed': requests.get(seed_uri).json()
    }

    raw_order0 = requests.get(order0_uri).json()
    order0_function_uri = raw_order0.get("function_uri")
    order0_structure_uri = raw_order0.get("structure_uri")
    order0_invoice_uri = raw_order0.get("invoice_uri")
    raw_order0

    flat_order0 = {
        'function': requests.get(order0_function_uri).json(),
        'structure': requests.get(order0_structure_uri).json(),
        'invoice': requests.get(order0_invoice_uri).json(),
    }

    print("Order:")
    pprint(raw_order0)
    print()
    print("Flat Order:")
    pprint(flat_order0)
    print()

    print("Invoice:")
    pprint(invoice0)
    print()
    print("Flat Invoice:")
    pprint(flat_invoice0)

    bom0
    return bom0, order0_function_uri, order0_invoice_uri, order0_structure_uri


@app.cell
def _(mo):
    mo.md(r"""
    ###Inspect CAT0 Order Envelope
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    #### CAT0 Order's Function Envelope
    """)
    return


@app.cell
def cat0_ordered_function(order0_function_uri, pprint, requests):
    raw_function0 = requests.get(order0_function_uri).json()

    infrafunction_source_uri = raw_function0['infrafunction_source_uri']
    infrafunction_uri = raw_function0['infrafunction_uri']
    process_source_uri = raw_function0['process_source_uri']
    process_uri = raw_function0['process_uri']

    flat_function0 = {
        "infrafunction_source": requests.get(infrafunction_source_uri).json(),
        "infrafunction": requests.get(infrafunction_uri).json(),
        "process_source": requests.get(process_source_uri).json(),
        "process": requests.get(process_uri).json()
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
def _():
    return


@app.cell(hide_code=True)
def cat0_ordered_structure(order0_structure_uri, pprint, requests):
    raw_structure0 = requests.get(order0_structure_uri).json()

    infrastructure_uri = raw_structure0['infrastructure_uri']
    plant_uri = raw_structure0['plant_uri']
    root_uri = raw_structure0['root_uri']

    flat_structure0  = {
        "infrastructure": requests.get(infrastructure_uri).json(),
        "plant": requests.get(plant_uri).json(),
        "root": requests.get(root_uri).json(),
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
def cat0_ordered_invoice(order0_invoice_uri, pprint, requests):
    raw_ordered_invoice0 = requests.get(order0_invoice_uri).json()
    data_uri = raw_ordered_invoice0['data_uri']
    flat_ordered_invoice0 = {'data': requests.get(data_uri).json()}
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
    """)
    return


@app.cell
def cat0_used_executor(bom0):
    used = bom0['prov:wasGeneratedBy']['prov:used']
    executor = used if isinstance(used, list) else [used]
    executor
    return (executor,)


@app.cell
def cat0_used_function(executor, requests):
    function_url = executor[1]['@id']
    function = requests.get(function_url).json()
    function
    return


@app.cell
def cat0_used_structure(executor, requests):
    structure_url = executor[0]['@id']
    structure = requests.get(structure_url).json()
    structure
    return


@app.cell
def cat0_sourced_data(bom0, content_address_equivalence, requests):
    stage_0 = bom0['stageLineage'][0]
    manafest_uri_0 = stage_0['@id']
    origin_dataset_uri_0 = stage_0['prov:wasDerivedFrom']['@id']

    stage_0_manafest = requests.get(manafest_uri_0).json()
    origin_dataset_0 = requests.get(origin_dataset_uri_0).json()

    content_address_equivalence_0 = content_address_equivalence(
        manafest_uri_0,
        origin_dataset_uri_0
    )
    print("Source Dataset wasDerivedFrom Origin Dataset:", content_address_equivalence_0)
    origin_dataset_0
    return (origin_dataset_uri_0,)


@app.cell
def cat0_ingressed_data(
    bom0,
    content_address_equivalence,
    origin_dataset_uri_0,
    requests,
):
    stage_1 = bom0['stageLineage'][1]
    ingresed_dataset_uri = manafest_uri_1 = stage_1['@id']
    source_dataset_uri_1 = stage_1['prov:wasDerivedFrom']['@id']

    ingressed_dataset = stage_1_manafest = requests.get(manafest_uri_1).json()
    source_dataset_1 = requests.get(source_dataset_uri_1).json()

    source_dataset_content_address_equivalence_1 = content_address_equivalence(
        source_dataset_uri_1, 
        origin_dataset_uri_0
    )
    print("Ingressed Dataset wasDerivedFrom Origin Dataset:", source_dataset_content_address_equivalence_1)
    ingressed_dataset
    return (ingresed_dataset_uri,)


@app.cell
def cat0_egressed_data(
    bom0,
    content_address_equivalence,
    ingresed_dataset_uri,
    requests,
):
    stage_2 = bom0['stageLineage'][2]
    manafest_uri_2 = stage_2['@id']
    source_dataset_uri_2 = stage_2['prov:wasDerivedFrom']['@id']

    egressed_dataset = stage_2_manafest = requests.get(manafest_uri_2).json()
    source_dataset_2 = requests.get(source_dataset_uri_2).json()

    source_dataset_content_address_equivalence_2 = content_address_equivalence(
        source_dataset_uri_2, 
        ingresed_dataset_uri
    )
    print("Egressed Dataset wasDerivedFrom Igressed Dataset:", source_dataset_content_address_equivalence_2)
    egressed_dataset
    return


@app.cell
def cat0_executed_structure(bom0, requests):
    stage_3 = bom0['stageLineage'][3]
    executed_Structure_url_3 = stage_3_url = stage_3['@id']
    executed_Structure_3 = requests.get(executed_Structure_url_3).json()
    executed_Structure_3
    return (executed_Structure_3,)


@app.cell
def cat0_executed_plant(executed_Structure_3, requests):
    executed_Plant_uri_3 = executed_Structure_3['plant_as_executed_uri']
    executed_Plant_3 = requests.get(executed_Plant_uri_3).json()
    executed_Plant_3
    return


@app.cell
def cat0_executed_infrastructure(executed_Structure_3, pprint, requests):
    executed_InfraStructure_uri_3 = executed_Structure_3['infrastructure_as_executed_uri']
    executed_InfraStructure_3 = requests.get(executed_InfraStructure_uri_3).json()

    executed_ObjectStore_uri_3 = executed_InfraStructure_3['object_store_as_executed_uri']
    executed_ObjectStore_3 = requests.get(executed_ObjectStore_uri_3).json()

    pprint(executed_ObjectStore_3)
    executed_InfraStructure_3
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Execute CAT1 — Function lineage (`linkProcess`)

    CAT1 is **not** a fresh Order on the input tree. `linkProcess` rebuilds
    Function (here: `process_1` as hotF), carries Structure, and chains CAT0
    Invoice **data** equality as CAT1 input.

    Same-Node alternative (not required here):
    `linkProcess(content_id=…, integrated_subproc=process_1)` via the BOM
    registry — seeds mesh federation of the index; still Node-local.
    """)
    return


@app.cell
def _(cat_bom_response_0, contentMesh, pprint, process_1):
    cat_order_request_1 = contentMesh.linkProcess(
        cat_bom_response_0,
        integrated_subproc=process_1,
    )
    pprint(cat_order_request_1)
    return (cat_order_request_1,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Submit CAT1 Order request to CAT Node
    """)
    return


@app.cell
def _(cat_order_request_1, contentMesh, pprint):
    cat_bom_response_1 = contentMesh.catSubmit(cat_order_request_1)
    # pprint(cat_bom_response_1)
    flat_cat_response_1 = contentMesh.flatten_bom(cat_bom_response_1)
    pprint(flat_cat_response_1)
    return


if __name__ == "__main__":
    app.run()
