"""Intra-run PROV stageLineage (wasDerivedFrom) on ExecutionBom."""
import pytest

from cats.network.feedback import build_execution_bom, sign_execution_bom, verify_execution_bom
from cats.network.feedback.envelope import EXECUTOR_RUN_ID
from cats.network.identity.node_did import node_did


def _by_cid(lineage: list, cid: str) -> dict:
    needle = f'ipfs://{cid}'
    for ent in lineage:
        if ent.get('@id') == needle:
            return ent
    raise AssertionError(f'no stageLineage entity for {cid!r}')


def test_stage_lineage_derivation_chain():
    bom = build_execution_bom(
        log_cid='log1',
        invoice_cid='inv1',
        node_did='did:key:zTest',
        order_cid='ord1',
        input_data_cid='inputData',
        ingress_data_cid='ingress',
        integration_data_cid='integration',
        data_cid='egress',
        structure_as_executed_cid='structExec',
    )
    activity = bom['prov:wasGeneratedBy']
    assert activity['@id'] == EXECUTOR_RUN_ID
    assert activity['@type'] == 'prov:Activity'
    assert activity['prov:used'] == [
        {'@id': 'ipfs://ord1'},
        {'@id': 'ipfs://inv1'},
    ]

    lineage = bom['stageLineage']
    assert len(lineage) == 4

    ingress = _by_cid(lineage, 'ingress')
    assert ingress['prov:wasGeneratedBy'] == {'@id': EXECUTOR_RUN_ID}
    assert ingress['prov:wasDerivedFrom'] == {'@id': 'ipfs://inputData'}

    integration = _by_cid(lineage, 'integration')
    assert integration['prov:wasDerivedFrom'] == {'@id': 'ipfs://ingress'}

    egress = _by_cid(lineage, 'egress')
    assert egress['prov:wasDerivedFrom'] == {'@id': 'ipfs://integration'}

    structure = _by_cid(lineage, 'structExec')
    assert structure['prov:wasGeneratedBy'] == {'@id': EXECUTOR_RUN_ID}
    assert 'prov:wasDerivedFrom' not in structure


def test_stage_lineage_omits_null_stages():
    bom = build_execution_bom(
        log_cid='log1',
        invoice_cid='inv1',
        ingress_data_cid='ingress',
        data_cid='egress',
    )
    lineage = bom['stageLineage']
    assert [e['@id'] for e in lineage] == [
        'ipfs://ingress',
        'ipfs://egress',
    ]
    # No integration → egress has no wasDerivedFrom (no invented edges).
    egress = _by_cid(lineage, 'egress')
    assert 'prov:wasDerivedFrom' not in egress
    ingress = _by_cid(lineage, 'ingress')
    assert 'prov:wasDerivedFrom' not in ingress


def test_stage_lineage_absent_when_no_stage_cids():
    bom = build_execution_bom(log_cid='log1', invoice_cid='inv1')
    assert 'stageLineage' not in bom
    assert bom['prov:wasGeneratedBy']['@id'] == EXECUTOR_RUN_ID
    assert bom['prov:wasGeneratedBy']['prov:used'] == {'@id': 'ipfs://inv1'}


def test_stage_lineage_covered_by_data_integrity(tmp_path):
    did = node_did(cats_home=str(tmp_path))
    bom = build_execution_bom(
        log_cid='log1',
        invoice_cid='inv1',
        node_did=did,
        ingress_data_cid='ingress',
        integration_data_cid='integration',
        data_cid='egress',
    )
    signed = sign_execution_bom(bom, cats_home=str(tmp_path))
    verify_execution_bom(signed)

    # Tamper a lineage edge → proof fails.
    signed['stageLineage'][0]['prov:wasDerivedFrom'] = {'@id': 'ipfs://evil'}
    with pytest.raises(ValueError, match='verification failed'):
        verify_execution_bom(signed)


def test_context_binds_stage_lineage():
    bom = build_execution_bom(
        log_cid='log1',
        invoice_cid='inv1',
        ingress_data_cid='ingress',
    )
    ctx = bom['@context'][1]
    assert ctx['stageLineage'] == 'cats:stageLineage'
