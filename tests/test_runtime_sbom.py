"""P3 Invoice runtime_sbom stem — flag, nest refs, signed BOM has no SBOM payload."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from cats.network.bom import attach_runtime_sbom, cats_sbom_enabled
from cats.network.cas import ref_id, sha256_hex, to_ni
from cats.network.content_mesh import ContentMesh
from cats.network.feedback import build_execution_bom, sign_execution_bom
from cats.network.identity import node_did


FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        'bomFormat',
        'profileConformance',
        'dcat:dataset',
        'artifacts',
        'spdxVersion',
        'SPDXID',
    }
)
FORBIDDEN_BOM_ID = 'FORBIDDEN_BOM_CONTENT_ID'


def _walk_keys(obj) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        found.update(obj)
        for value in obj.values():
            found.update(_walk_keys(value))
    elif isinstance(obj, list):
        for item in obj:
            found.update(_walk_keys(item))
    return found


def _mesh(tmp_path, monkeypatch) -> ContentMesh:
    client = ContentMesh(ipfsClient=MagicMock(), CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    return client


def test_cats_sbom_enabled(monkeypatch):
    monkeypatch.delenv('CATS_SBOM', raising=False)
    assert cats_sbom_enabled() is False
    monkeypatch.setenv('CATS_SBOM', '1')
    assert cats_sbom_enabled() is True
    monkeypatch.setenv('CATS_SBOM', 'true')
    assert cats_sbom_enabled() is True
    monkeypatch.setenv('CATS_SBOM', '0')
    assert cats_sbom_enabled() is False


def test_attach_runtime_sbom_flag_off(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    monkeypatch.delenv('CATS_SBOM', raising=False)
    sae_id = mesh.put_json({'rebuilt': False})
    invoice: dict = {}
    assert (
        attach_runtime_sbom(
            invoice,
            mesh,
            structure_as_executed={},
            structure_as_executed_id=sae_id,
        )
        is None
    )
    assert 'runtime_sbom_uri' not in invoice


def test_attach_runtime_sbom_flag_on_nest_refs_only(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    monkeypatch.setenv('CATS_SBOM', '1')
    monkeypatch.setattr(
        'cats.network.bom.syft.syft_binary', lambda explicit=None: None
    )
    monkeypatch.setattr(
        'cats.network.bom.syft.docker_image_digest',
        lambda ref, timeout=15: None,
    )
    sae_id = mesh.put_json({'rebuilt': False})
    invoice: dict = {}
    nest_id = attach_runtime_sbom(
        invoice,
        mesh,
        structure_as_executed={},
        structure_as_executed_id=sae_id,
    )
    assert nest_id
    assert invoice.get('runtime_sbom_uri')
    dumped = json.dumps(invoice)
    assert 'bomFormat' not in dumped
    assert 'artifacts' not in dumped
    nest = json.loads(mesh.cat(nest_id))
    assert nest.get('cyclonedx_uri')
    assert 'syft_uri' not in nest
    assert _walk_keys(nest).isdisjoint(FORBIDDEN_PAYLOAD_KEYS)
    cdx = json.loads(mesh.cat(ref_id(nest, 'cyclonedx')))
    assert cdx['bomFormat'] == 'CycloneDX'
    assert FORBIDDEN_BOM_ID not in json.dumps(cdx)
    assert FORBIDDEN_BOM_ID not in json.dumps(nest)


def test_signed_bom_has_no_sbom_payload_keys(monkeypatch, tmp_path):
    monkeypatch.delenv('CAT_NODE_DID', raising=False)
    did = node_did(cats_home=str(tmp_path))
    signed = sign_execution_bom(
        build_execution_bom(
            log_id='QmLog',
            invoice_id='QmInv',
            node_did=did,
        ),
        cats_home=str(tmp_path),
    )
    keys = _walk_keys(signed)
    assert keys.isdisjoint(FORBIDDEN_PAYLOAD_KEYS)
    assert 'invoice_uri' in signed
    assert 'log_uri' in signed
    assert 'runtime_sbom_uri' not in signed
    assert FORBIDDEN_BOM_ID not in json.dumps(signed)


def test_runtime_nest_omits_execution_bom_content_id(tmp_path, monkeypatch):
    mesh = _mesh(tmp_path, monkeypatch)
    monkeypatch.setenv('CATS_SBOM', '1')
    monkeypatch.setattr(
        'cats.network.bom.syft.syft_binary', lambda explicit=None: None
    )
    image_hex = sha256_hex(b'p3-oci')
    monkeypatch.setattr(
        'cats.network.bom.syft.docker_image_digest',
        lambda ref, timeout=15: image_hex if 'kindest' in ref else None,
    )
    sae_id = mesh.put_json({'rebuilt': False})
    invoice = {'content_id': FORBIDDEN_BOM_ID}
    nest_id = attach_runtime_sbom(
        invoice,
        mesh,
        structure_as_executed={},
        structure_as_executed_id=sae_id,
        image_refs=[f'kindest/node@sha256:{image_hex}'],
    )
    nest = json.loads(mesh.cat(nest_id))
    cdx = json.loads(mesh.cat(ref_id(nest, 'cyclonedx')))
    assert FORBIDDEN_BOM_ID not in json.dumps(nest)
    assert FORBIDDEN_BOM_ID not in json.dumps(cdx)
    assert to_ni(image_hex)
