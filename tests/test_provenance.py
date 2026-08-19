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
from cats.network import _node_init_endpoint
from cats.network.cas import ref_id, ref_uri
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
    'ingress_subproc',
    'integrated_subproc',
    'egress_subproc',
    'integration_cache_subproc',
)
INFRAFUNCTION_BIND_KEYS = ('infrafunction_subproc',)
FUNCTION_PAIRING_KEYS = (
    'process',
    'infrafunction',
    'process_source',
    'infrafunction_source',
)
STRUCTURE_PAIRING_KEYS = ('root', 'plant', 'infrastructure')
PLANT_SNAPSHOT_KEYS = (
    'applied_structure_id',
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


def _assert_named_bind_leaf(leaf_id, *, expected_source_id):
    """Stock leaf is named-bind JSON pinned to the package source id."""
    leaf = json.loads(contentMesh.cat(leaf_id))
    assert 'module' in leaf and 'qualname' in leaf
    assert 'source_cid' not in leaf
    source = leaf.get('contentId') or ref_id(leaf, 'source')
    assert source == expected_source_id, (
        f'named-bind source unexpected: {leaf!r}'
    )
    assert isinstance(leaf['module'], str) and leaf['module']
    assert isinstance(leaf['qualname'], str) and leaf['qualname']


def assert_provenance_record(bom_response, order_request):
    """Assert full Order / Invoice / BOM / log / as-executed provenance coverage."""
    assert 'error' not in bom_response, bom_response.get('error')
    assert 'bom' in bom_response
    assert 'content_id' in bom_response and bom_response['content_id']
    assert 'bom_cid' not in bom_response
    # content_id is response-only; never written into the addressed bom dict.
    bom = bom_response['bom']
    assert 'bom_cid' not in bom
    assert 'content_id' not in bom

    assert bom.get('invoice_uri'), 'bom.invoice_uri should be set'
    assert bom.get('log_uri'), 'bom.log_uri should be set'
    assert 'invoice_cid' not in bom
    assert 'log_cid' not in bom
    assert bom.get('node_did'), 'bom.node_did should be set'
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
    assert not any(
        isinstance(k, str) and k.endswith('_cid') for k in bom
    ), f'bom still has *_cid keys: {sorted(k for k in bom if str(k).endswith("_cid"))}'


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
    order_id = order_request.get('content_id') or order_request.get('order_cid')
    assert order_id, 'order_request.content_id missing'
    assert ref_id(invoice, 'order') == order_id, (
        'Invoice.order ref must equal the submitted Order content id'
    )
    assert ref_id(order, 'function'), 'order.function ref missing'
    assert ref_id(order, 'structure'), 'order.structure ref missing'
    assert ref_id(order, 'invoice'), 'order.invoice ref missing'
    assert order.get('structure_filepath'), 'order.structure_filepath missing'
    assert not any(k.endswith('_cid') for k in order), (
        f'order still has *_cid keys: {sorted(k for k in order if k.endswith("_cid"))}'
    )

    # --- Function pairing (hybrid source refs) ---
    for stem in FUNCTION_PAIRING_KEYS:
        assert ref_id(function, stem), f'function.{stem} should be set'
    assert not any(k.endswith('_cid') for k in function), (
        f'function still has *_cid keys: '
        f'{sorted(k for k in function if k.endswith("_cid"))}'
    )

    process_id = ref_id(function, 'process')
    process_bind = json.loads(contentMesh.cat(ref_uri(function, 'process') or process_id))
    process_source = ref_id(function, 'process_source')
    for stem in PROCESS_BIND_KEYS:
        leaf_id = ref_id(process_bind, stem)
        assert leaf_id, f'process bind missing {stem}'
        _assert_named_bind_leaf(leaf_id, expected_source_id=process_source)

    ifr_id = ref_id(function, 'infrafunction')
    ifr_bind = json.loads(
        contentMesh.cat(ref_uri(function, 'infrafunction') or ifr_id)
    )
    ifr_source = ref_id(function, 'infrafunction_source')
    for stem in INFRAFUNCTION_BIND_KEYS:
        leaf_id = ref_id(ifr_bind, stem)
        assert leaf_id, f'infrafunction bind missing {stem}'
        _assert_named_bind_leaf(leaf_id, expected_source_id=ifr_source)

    # --- Structure pairing (apply-complete) ---
    for stem in STRUCTURE_PAIRING_KEYS:
        assert ref_id(structure, stem), f'structure.{stem} should be set'
    assert not any(k.endswith('_cid') for k in structure), (
        f'structure still has *_cid keys: '
        f'{sorted(k for k in structure if k.endswith("_cid"))}'
    )

    # --- Invoice: data + stage refs; Seed (#187) ---
    data_id = ref_id(invoice, 'data')
    ingress_id = ref_id(invoice, 'ingress_data')
    integration_id = ref_id(invoice, 'integration_data')
    seed_id = ref_id(invoice, 'seed')
    assert data_id, 'invoice.data should be set'
    assert ingress_id, 'invoice.ingress_data should be set'
    assert integration_id, 'invoice.integration_data should be set'
    assert seed_id, 'invoice.seed should be a real content id, not null'
    seed = invoice.get('seed')
    assert seed is not None, (
        'flat_bom.invoice.seed should be resolved by flatten_bom from seed ref'
    )
    assert set(seed) == {'seed', 'rng_seed', 'num_partitions'}, (
        f'seed keys unexpected: {seed!r}'
    )
    assert isinstance(seed['seed'], str) and seed['seed'], (
        f"seed['seed'] should be a non-empty identity hex: {seed!r}"
    )
    assert isinstance(seed['rng_seed'], int) and 0 <= seed['rng_seed'] <= 0x7FFFFFFF, (
        f"seed['rng_seed'] should be a non-negative 31-bit int "
        f"(np.random.default_rng / Ray Data seed=-safe): {seed!r}"
    )
    assert isinstance(seed['num_partitions'], int) and seed['num_partitions'] >= 1, (
        f"seed['num_partitions'] should be a positive int: {seed!r}"
    )
    assert ref_id(invoice, 'structure_as_executed'), (
        'invoice.structure_as_executed should be set'
    )
    assert ref_id(input_invoice, 'data'), (
        'order.flat.invoice.data (input) should be set'
    )
    assert not any(k.endswith('_cid') for k in invoice if k != 'order'), (
        f'invoice still has *_cid keys: '
        f'{sorted(k for k in invoice if k.endswith("_cid"))}'
    )

    structure_as_executed = flat['structure_as_executed']
    assert structure_as_executed is not None
    assert ref_id(structure_as_executed, 'plant_as_executed')
    assert ref_id(structure_as_executed, 'infrastructure_as_executed')
    infrastructure_as_executed = flat['infrastructure_as_executed']
    assert infrastructure_as_executed is not None
    assert ref_id(infrastructure_as_executed, 'object_store_as_executed')

    # --- Log mirrors stage refs + JobHandle correlator ---
    assert ref_id(log, 'ingress_data') == ingress_id
    assert ref_id(log, 'integration_data') == integration_id
    assert ref_id(log, 'egress_data') == data_id
    assert 'plant_rebuilt' in log
    assert isinstance(log['plant_rebuilt'], bool)
    _assert_job_handle_uri(log.get('object_store_result_uri'))
    assert not any(k.endswith('_cid') for k in log), (
        f'log still has *_cid keys: {sorted(k for k in log if k.endswith("_cid"))}'
    )

    # --- Plant as-executed (observed; flattened) ---
    assert plant is not None
    for key in PLANT_SNAPSHOT_KEYS:
        assert key in plant, f'plant as-executed missing {key}'
    assert plant['applied_structure_id'] == ref_id(order, 'structure'), (
        'plant.applied_structure_id must equal order.structure content id'
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
        'input_data_cid': ref_id(input_invoice, 'data'),
        'output_data_cid': data_id,
        'invoice': invoice,
        'seed': seed,
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
        endpoint=_node_init_endpoint(),
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

    def test_cat0_cat1_seed_uniqueness(self, cat_runs):
        """CAT0 and CAT1 each mint a distinct Seed replay dict (#187)."""
        seed0 = cat_runs.cat0.provenance['seed']
        seed1 = cat_runs.cat1.provenance['seed']
        assert seed0['seed'] != seed1['seed'], (
            'CAT0/CAT1 seed identity hex should differ per execution'
        )
        assert seed0['rng_seed'] != seed1['rng_seed'], (
            'CAT0/CAT1 rng_seed should differ (derived from distinct seed hex)'
        )
