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
    ### Execute Initial CAT0:
    ##### Instantiate CAT Mesh Client:
    """)
    return


@app.cell
def _():
    from pprint import pprint
    import pandas as pd

    from cats import MESH_CLIENT as meshClient
    from cats import INPUT_STRUCTURE_HOME, INPUT_DATA_HOME

    return INPUT_DATA_HOME, INPUT_STRUCTURE_HOME, meshClient, pprint


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Compose Initial CAT Order request for CAT Node
    """)
    return


@app.cell
def _(INPUT_DATA_HOME, INPUT_STRUCTURE_HOME, meshClient, pprint):
    from data.input.process import (
        egress,
        infrafunction_subproc,
        ingress,
        integration_cache,
        process_0,
        process_1,
    )

    cat_order_request_0 = meshClient.create_order_request(
        ingress_subproc=ingress,
        integrated_subproc=process_0,
        egress_subproc=egress,
        integration_cache_subproc=integration_cache,
        infrafunction_subproc=infrafunction_subproc,
        data_dirpath=INPUT_DATA_HOME,  # f'{INPUT_DATA_HOME}/iris.csv',
        structure_filepath=INPUT_STRUCTURE_HOME,
        endpoint="http://127.0.0.1:5000/cat/node/init",
    )
    pprint(cat_order_request_0)
    return cat_order_request_0, egress, infrafunction_subproc, ingress, integration_cache, process_1


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Submit Initial CAT Order request to CAT Node
    """)
    return


@app.cell
def _(cat_order_request_0, meshClient, pprint):
    cat_invoiced_response_0 = meshClient.catSubmit(cat_order_request_0)
    pprint(cat_invoiced_response_0)
    flat_cat_invoiced_response_0 = meshClient.flatten_bom(cat_invoiced_response_0)
    pprint(flat_cat_invoiced_response_0)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Execute CAT1:
    #### Compose a modified CAT Order request that executes CAT1 with CAT0's Structure a new Process
    """)
    return


@app.cell
def _(
    INPUT_DATA_HOME,
    INPUT_STRUCTURE_HOME,
    egress,
    infrafunction_subproc,
    ingress,
    integration_cache,
    meshClient,
    pprint,
    process_1,
):
    cat_order_request_1 = meshClient.create_order_request(
        ingress_subproc=ingress,
        integrated_subproc=process_1,
        egress_subproc=egress,
        integration_cache_subproc=integration_cache,
        infrafunction_subproc=infrafunction_subproc,
        data_dirpath=INPUT_DATA_HOME, # f'{INPUT_DATA_HOME}/iris.csv',
        structure_filepath=INPUT_STRUCTURE_HOME,
        endpoint='http://127.0.0.1:5000/cat/node/init'
    )
    pprint(cat_order_request_1)
    return (cat_order_request_1,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ##### Submit modified CAT Order request to CAT Node
    """)
    return


@app.cell
def _(cat_order_request_1, meshClient, pprint):
    cat_invoiced_response_1 = meshClient.catSubmit(cat_order_request_1)
    pprint(cat_invoiced_response_1)
    flat_cat_invoiced_response_1 = meshClient.flatten_bom(cat_invoiced_response_1)
    pprint(flat_cat_invoiced_response_1)
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
