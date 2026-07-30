"""Integration tests: live Order provenance records + CAT0/CAT1 data lineage.

Runs CAT0 and CAT1 once (module-scoped), then asserts full content-addressed
provenance (BOM.md / LineageOfProvenance.md) and data_cid payload equality on
the cached results — same coverage as the former per-test re-submits.
"""
import glob
import json
import os
import time
from pprint import pprint
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from cats import DATA_HOME, CONTENT_MESH as contentMesh
from cats import INPUT_STRUCTURE_HOME, INPUT_DATA_HOME
from cats.network.feedback import verify_execution_bom

from data.input.function.process import (
    egress,
    ingress,
    integration_cache,
    process_0,
    process_1,
)
from data.input.function.infrafunction import infrafunction_subproc

PROCESS_BIND_KEYS = (
    'ingress_subproc_cid',
    'integrated_subproc_cid',
    'egress_subproc_cid',
    'integration_cache_subproc_cid',
)
INFRAFUNCTION_BIND_KEYS = ('infrafunction_subproc_cid',)
FUNCTION_PAIRING_KEYS = (
    'process_cid',
    'infrafunction_cid',
    'process_source_cid',
    'infrafunction_source_cid',
)
STRUCTURE_PAIRING_KEYS = ('root_cid', 'plant_cid', 'infrastructure_cid')
PLANT_SNAPSHOT_KEYS = (
    'applied_structure_cid',
    'kind_cluster_name',
    'kubeconfig_context',
    'ray_dashboard_address',
    'ray_release_name',
    'rebuilt',
)
INFRASTRUCTURE_SNAPSHOT_KEYS = (
    'minio_scratch_bucket',
    'minio_scratch_endpoint_host',
    'minio_scratch_endpoint_pod',
    'minio_durable_bucket',
    'minio_durable_endpoint_host',
    'minio_durable_endpoint_pod',
)

CAT_INPUT_PATH = f'{DATA_HOME}/testing/cat_input'
CAT_OUTPUT_PATH = f'{DATA_HOME}/testing/cat_output'


def files_to_pandasDF(output, format):
    files = glob.glob(os.path.join(output, format))
    dfs = list(pd.read_csv(f).assign(filename=f) for f in files)
    df = None
    for dfx in dfs:
        if df is None:
            df = dfx
        else:
            df = pd.concat([df, dfx], ignore_index=True)
    return df


def cid_to_pandasDF(cid, download_dir, format='*.csv'):
    os.makedirs(download_dir)
    contentMesh.testGet(cid, download_dir)
    return files_to_pandasDF(output=download_dir, format=format)


def _assert_job_handle_uri(object_store_result_uri):
    """JobHandle correlator shape (s3://<bucket>/<prefix>/result)."""
    assert object_store_result_uri, "log.object_store_result_uri should be set"
    assert object_store_result_uri.startswith('s3://'), (
        f"log.object_store_result_uri should be an s3 URI: "
        f"{object_store_result_uri}"
    )
    assert object_store_result_uri.endswith('/result'), (
        f"log.object_store_result_uri should end with JobHandle result_key "
        f"suffix /result: {object_store_result_uri}"
    )
    remainder = object_store_result_uri[len('s3://'):]
    assert '/' in remainder and not remainder.startswith('/'), (
        f"log.object_store_result_uri missing bucket/prefix: "
        f"{object_store_result_uri}"
    )
    bucket, _, key = remainder.partition('/')
    assert bucket and key and key.endswith('/result'), (
        f"log.object_store_result_uri not JobHandle-shaped: "
        f"{object_store_result_uri}"
    )


def _assert_named_bind_leaf(leaf_cid, *, expected_source_cid):
    """Stock leaf CID is named-bind JSON pinned to the package source_cid."""
    leaf = json.loads(contentMesh.cat(leaf_cid))
    assert set(leaf) == {'source_cid', 'module', 'qualname'}, (
        f'named-bind leaf keys unexpected: {leaf!r}'
    )
    assert leaf['source_cid'] == expected_source_cid
    assert isinstance(leaf['module'], str) and leaf['module']
    assert isinstance(leaf['qualname'], str) and leaf['qualname']


def assert_provenance_record(bom_response, order_request):
    """Assert full Order / Invoice / BOM / log / as-executed provenance coverage."""
    assert 'error' not in bom_response, bom_response.get('error')
    assert 'bom' in bom_response
    assert 'bom_cid' in bom_response and bom_response['bom_cid']
    # bom_cid is response-only; never written into the IPFS-addressed bom dict.
    bom = bom_response['bom']
    assert 'bom_cid' not in bom

    for key in ('invoice_cid', 'log_cid', 'node_did'):
        assert bom.get(key), f'bom.{key} should be set'
    assert str(bom['node_did']).startswith('did:'), (
        f'bom.node_did must be a DID, got {bom["node_did"]!r}'
    )
    assert bom.get('@context'), 'bom.@context should be set (JSON-LD Phase 1)'
    assert bom.get('@type'), 'bom.@type should be set (JSON-LD Phase 1)'
    proof = bom.get('proof')
    assert isinstance(proof, dict), 'bom.proof should be set (Phase 1b)'
    assert proof.get('type') == 'DataIntegrityProof'
    assert proof.get('cryptosuite') == 'eddsa-jcs-2022'
    assert proof.get('proofValue'), 'bom.proof.proofValue missing'
    verify_execution_bom(bom)
    assert 'node_uri' not in bom
    assert 'plant_snapshot_cid' not in bom
    assert 'infrastructure_snapshot_cid' not in bom


    flat = bom_response['flat_bom']
    invoice = flat['invoice']
    order = invoice['order']
    function = order['flat']['function']
    structure = order['flat']['structure']
    input_invoice = order['flat']['invoice']
    log = flat['log']
    plant = flat['plant']
    object_store_as_executed = flat['object_store_as_executed']

    # --- Order (submitted) vs Invoice backfill ---
    assert order_request.get('order_cid'), 'order_request.order_cid missing'
    assert invoice.get('order_cid') == order_request['order_cid'], (
        'Invoice.order_cid must equal the submitted Order CID'
    )
    assert order.get('function_cid'), 'order.function_cid missing'
    assert order.get('structure_cid'), 'order.structure_cid missing'
    assert order.get('invoice_cid'), 'order.invoice_cid missing'
    assert order.get('structure_filepath'), 'order.structure_filepath missing'

    # --- Function pairing (hybrid source CIDs) ---
    assert set(FUNCTION_PAIRING_KEYS) <= set(function), (
        f'function_cid missing keys: {function!r}'
    )
    for key in FUNCTION_PAIRING_KEYS:
        assert function[key], f'function.{key} should be set'

    process_bind = json.loads(contentMesh.cat(function['process_cid']))
    for key in PROCESS_BIND_KEYS:
        assert process_bind.get(key), f'process bind missing {key}'
        _assert_named_bind_leaf(
            process_bind[key],
            expected_source_cid=function['process_source_cid'],
        )

    ifr_bind = json.loads(contentMesh.cat(function['infrafunction_cid']))
    for key in INFRAFUNCTION_BIND_KEYS:
        assert ifr_bind.get(key), f'infrafunction bind missing {key}'
        _assert_named_bind_leaf(
            ifr_bind[key],
            expected_source_cid=function['infrafunction_source_cid'],
        )

    # --- Structure pairing (apply-complete) ---
    assert set(STRUCTURE_PAIRING_KEYS) <= set(structure), (
        f'structure_cid missing keys: {structure!r}'
    )
    for key in STRUCTURE_PAIRING_KEYS:
        assert structure[key], f'structure.{key} should be set'

    # --- Invoice: data + stage CIDs; Seed still null (#187) ---
    assert invoice.get('data_cid'), 'invoice.data_cid should be set'
    assert invoice.get('ingress_data_cid'), 'invoice.ingress_data_cid should be set'
    assert invoice.get('integration_data_cid'), (
        'invoice.integration_data_cid should be set'
    )
    assert 'seed_cid' in invoice, 'invoice.seed_cid key should be present'
    assert invoice['seed_cid'] is None, (
        'invoice.seed_cid is still deferred (#187); expected null'
    )
    assert invoice.get('structure_as_executed_cid'), (
        'invoice.structure_as_executed_cid should be set'
    )
    assert input_invoice.get('data_cid'), (
        'order.flat.invoice.data_cid (input) should be set'
    )

    structure_as_executed = flat['structure_as_executed']
    assert structure_as_executed is not None
    assert structure_as_executed.get('plant_as_executed_cid')
    assert structure_as_executed.get('infrastructure_as_executed_cid')
    infrastructure_as_executed = flat['infrastructure_as_executed']
    assert infrastructure_as_executed is not None
    assert infrastructure_as_executed.get('object_store_as_executed_cid')

    # --- Log mirrors stage CIDs + JobHandle correlator ---
    assert log.get('ingress_data_cid') == invoice['ingress_data_cid']
    assert log.get('integration_data_cid') == invoice['integration_data_cid']
    assert log.get('egress_data_cid') == invoice['data_cid']
    assert 'plant_rebuilt' in log
    assert isinstance(log['plant_rebuilt'], bool)
    _assert_job_handle_uri(log.get('object_store_result_uri'))

    # --- Plant as-executed (observed; flattened) ---
    assert plant is not None
    for key in PLANT_SNAPSHOT_KEYS:
        assert key in plant, f'plant as-executed missing {key}'
    assert plant['applied_structure_cid'] == order['structure_cid'], (
        'plant.applied_structure_cid must equal order.structure_cid'
    )
    assert isinstance(plant['rebuilt'], bool)

    # --- ObjectStore as-executed (observed; nested under infrastructure) ---
    assert object_store_as_executed is not None
    for key in INFRASTRUCTURE_SNAPSHOT_KEYS:
        assert object_store_as_executed.get(key), (
            f'object_store as-executed missing {key}'
        )
    assert 'access_key' not in object_store_as_executed
    assert 'secret_key' not in object_store_as_executed

    return {
        'input_data_cid': input_invoice['data_cid'],
        'output_data_cid': invoice['data_cid'],
        'invoice': invoice,
        'log': log,
        'function': function,
        'structure': structure,
        'plant': plant,
        'infrastructure': object_store_as_executed,
    }


def _create_order_request(*, integrated_subproc):
    order_request = contentMesh.create_order_request(
        ingress_subproc=ingress,
        integrated_subproc=integrated_subproc,
        egress_subproc=egress,
        integration_cache_subproc=integration_cache,
        infrafunction_subproc=infrafunction_subproc,
        data_dirpath=INPUT_DATA_HOME,
        structure_filepath=INPUT_STRUCTURE_HOME,
        endpoint='http://127.0.0.1:5000/cat/node/init',
    )
    pprint(order_request)
    print()
    return order_request


def _submit_and_load(order_request):
    """Submit once: provenance assert + input/output DataFrames."""
    response = contentMesh.catSubmit(order_request)
    pprint(response)
    print()
    if 'error' in response:
        raise RuntimeError(
            f"CAT node returned an error: {response['error']}"
        )
    flat = contentMesh.flatten_bom(response)
    pprint(flat)
    print()

    provenance = assert_provenance_record(flat, order_request)
    print(provenance['input_data_cid'])
    print()
    print(provenance['output_data_cid'])
    print()

    stamp = int(time.time())
    input_df = cid_to_pandasDF(
        cid=provenance['input_data_cid'],
        download_dir=f'{CAT_INPUT_PATH}_{stamp}',
    )
    input_df = input_df.drop(columns=['filename'])
    input_df = (
        input_df.apply(pd.to_numeric, errors='coerce')
        .astype(float)
        .sort_values(by=list(input_df.columns))
        .reset_index(drop=True)
    )

    output_df = cid_to_pandasDF(
        cid=provenance['output_data_cid'],
        download_dir=f'{CAT_OUTPUT_PATH}_{stamp}',
    )
    return SimpleNamespace(
        order_request=order_request,
        provenance=provenance,
        input_df=input_df,
        output_df=output_df,
    )


def _cat0_transfer_link(output_df):
    linked = (
        output_df.sort_values(by='id')
        .drop(columns=['id', 'filename', 'petal area (cm^2)'])
        .apply(pd.to_numeric, errors='coerce')
        .astype(float)
    )
    return linked.sort_values(by=list(linked.columns)).reset_index(drop=True)


def _cat1_transfer_link(output_df):
    linked = (
        output_df.drop(columns=['filename', 'DUPLICATE petal area (cm^2)'])
        .apply(pd.to_numeric, errors='coerce')
        .astype(float)
    )
    return linked.sort_values(by=list(linked.columns)).reset_index(drop=True)


@pytest.fixture(scope='module')
def cat_runs():
    """Execute CAT0 then CAT1 once; all tests assert against this cache."""
    cat0 = _submit_and_load(
        _create_order_request(integrated_subproc=process_0)
    )
    cat0.linked_output_df = _cat0_transfer_link(cat0.output_df)

    cat1 = _submit_and_load(
        _create_order_request(integrated_subproc=process_1)
    )
    cat1.linked_output_df = _cat1_transfer_link(cat1.output_df)

    return SimpleNamespace(cat0=cat0, cat1=cat1)


class TestProvenanceCATs:
    """Live Node provenance + data lineage (one CAT0 + one CAT1 submit)."""

    def test_cat0_provenance_record(self, cat_runs):
        """CAT0 BOM/Invoice/Order/log/snapshots form a complete provenance record."""
        assert cat_runs.cat0.provenance is not None

    def test_cat1_provenance_record(self, cat_runs):
        """CAT1 BOM/Invoice/Order/log/snapshots form a complete provenance record."""
        assert cat_runs.cat1.provenance is not None

    def test_cat0_data_verification(self, cat_runs):
        """CAT0 output data equals CAT0 input after Process transform."""
        assert np.array_equal(
            cat_runs.cat0.input_df.values,
            cat_runs.cat0.linked_output_df.values,
        )

    def test_cat1_data_verification(self, cat_runs):
        """CAT1 output data equals CAT1 input after Process transform."""
        assert np.array_equal(
            cat_runs.cat1.input_df.values,
            cat_runs.cat1.linked_output_df.values,
        )

    def test_cat1_input_lineage_verification(self, cat_runs):
        """CAT0 and CAT1 share the same input Invoice data_cid content."""
        assert np.array_equal(
            cat_runs.cat0.input_df.values,
            cat_runs.cat1.input_df.values,
        )

    def test_cat1_output_lineage_verification(self, cat_runs):
        """CAT1 output matches CAT0 input (duplicate-petal Process lineage)."""
        assert np.array_equal(
            cat_runs.cat0.input_df.values,
            cat_runs.cat1.linked_output_df.values,
        )

    def test_catMesh_data_transfer_verification(self, cat_runs):
        """CAT0 output columns match CAT1 input (mesh transfer continuity)."""
        assert np.array_equal(
            cat_runs.cat0.linked_output_df.values,
            cat_runs.cat1.input_df.values,
        )
