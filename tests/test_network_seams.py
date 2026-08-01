"""Feedback / identity Phase 1 seams (JSON-LD/PROV + DID).

AddressStore (Phase 2a gateway reads) is covered in test_address_store_gateway.py.
"""

from cats.network.feedback import attach_node_did, build_execution_bom
from cats.network.identity import node_did, node_uri


def test_build_execution_bom_includes_node_did_and_cid_keys():
    bom = build_execution_bom(
        log_cid='log',
        invoice_cid='inv',
        node_did='did:key:zTest',
    )
    assert bom['invoice_cid'] == 'inv'
    assert bom['log_cid'] == 'log'
    assert bom['node_did'] == 'did:key:zTest'
    assert bom['@type'] == ['prov:Entity', 'cats:ExecutionBom']
    assert bom['@context'][0] == 'https://www.w3.org/ns/prov#'
    assert bom['prov:wasAttributedTo'] == {'@id': 'did:key:zTest'}
    assert bom['prov:wasGeneratedBy']['@type'] == 'prov:Activity'
    assert bom['prov:wasGeneratedBy']['prov:used'] == {'@id': 'ipfs://inv'}
    assert 'plant_snapshot_cid' not in bom
    assert 'infrastructure_snapshot_cid' not in bom
    assert 'node_uri' not in bom
    assert 'bom_cid' not in bom


def test_build_execution_bom_omits_node_did_when_none():
    bom = build_execution_bom(
        log_cid='log',
        invoice_cid='inv',
    )
    assert 'node_did' not in bom
    assert 'prov:wasAttributedTo' not in bom
    assert bom['invoice_cid'] == 'inv'
    assert bom['log_cid'] == 'log'
    assert '@context' in bom
    assert '@type' in bom


def test_attach_node_did_sets_field():
    pkg = attach_node_did({'invoice_cid': 'inv'}, 'did:key:zNode')
    assert pkg['node_did'] == 'did:key:zNode'


def test_node_uri_respects_env(monkeypatch):
    monkeypatch.setenv('CAT_NODE_HOST', '10.0.0.2')
    monkeypatch.setenv('CAT_NODE_PORT', '6000')
    assert node_uri() == 'http://10.0.0.2:6000'


def test_node_uri_defaults(monkeypatch):
    monkeypatch.delenv('CAT_NODE_HOST', raising=False)
    monkeypatch.delenv('CAT_NODE_PORT', raising=False)
    assert node_uri() == 'http://127.0.0.1:5000'


def test_node_did_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv('CAT_NODE_DID', 'did:key:zFromEnv')
    assert node_did(cats_home=str(tmp_path)) == 'did:key:zFromEnv'


def test_node_did_rejects_non_did_env(monkeypatch, tmp_path):
    monkeypatch.setenv('CAT_NODE_DID', 'http://127.0.0.1:5000')
    try:
        node_did(cats_home=str(tmp_path))
        assert False, 'expected ValueError'
    except ValueError as exc:
        assert 'did:' in str(exc)


def test_node_did_persists_did_key(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    first = node_did(cats_home=str(tmp_path))
    assert first.startswith('did:key:z')
    key_path = tmp_path / '.cats' / 'node_did.json'
    assert key_path.is_file()
    second = node_did(cats_home=str(tmp_path))
    assert second == first


def test_load_node_signing_material_matches_node_did(monkeypatch, tmp_path):
    from cats.network.identity import load_node_signing_material

    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    loaded_did, key = load_node_signing_material(str(tmp_path))
    assert loaded_did == did
    assert key is not None
