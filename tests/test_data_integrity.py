"""Phase 1b Data Integrity (eddsa-jcs-2022) round-trip and failure cases."""
import pytest

from cats.network.feedback import (
    build_execution_bom,
    sign_execution_bom,
    verify_execution_bom,
)
from cats.network.feedback.data_integrity import CRYPTOSUITE, PROOF_TYPE
from cats.network.identity import load_node_signing_material, node_did


def test_sign_verify_round_trip(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    bom = build_execution_bom(
        log_cid='QmLog',
        invoice_cid='QmInv',
        node_did=did,
    )
    signed = sign_execution_bom(bom, cats_home=str(tmp_path))
    proof = signed['proof']
    assert proof['type'] == PROOF_TYPE
    assert proof['cryptosuite'] == CRYPTOSUITE
    assert proof['proofValue'].startswith('z')
    assert proof['verificationMethod'].startswith(did + '#')
    verify_execution_bom(signed)


def test_tamper_invoice_cid_fails_verify(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    signed = sign_execution_bom(
        build_execution_bom(
            log_cid='QmLog',
            invoice_cid='QmInv',
            node_did=did,
        ),
        cats_home=str(tmp_path),
    )
    signed['invoice_cid'] = 'QmTampered'
    with pytest.raises(ValueError, match='verification failed'):
        verify_execution_bom(signed)


def test_cat_node_did_mismatch_raises(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did, _ = load_node_signing_material(str(tmp_path))
    monkeypatch.setenv('CAT_NODE_DID', 'did:key:zMismatchOther')
    bom = build_execution_bom(
        log_cid='QmLog',
        invoice_cid='QmInv',
        node_did=did,
    )
    with pytest.raises(ValueError, match='does not match keyfile DID'):
        sign_execution_bom(bom, cats_home=str(tmp_path))


def test_cat_node_did_without_keyfile_raises(monkeypatch, tmp_path):
    monkeypatch.setenv('CAT_NODE_DID', 'did:key:zEnvOnlyNoKey')
    bom = build_execution_bom(
        log_cid='QmLog',
        invoice_cid='QmInv',
        node_did='did:key:zEnvOnlyNoKey',
    )
    with pytest.raises(ValueError, match='no local keyfile'):
        sign_execution_bom(bom, cats_home=str(tmp_path))


def test_bom_node_did_mismatch_raises(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    load_node_signing_material(str(tmp_path))
    bom = build_execution_bom(
        log_cid='QmLog',
        invoice_cid='QmInv',
        node_did='did:key:zOtherAttribution',
    )
    with pytest.raises(ValueError, match='bom.node_did'):
        sign_execution_bom(bom, cats_home=str(tmp_path))
