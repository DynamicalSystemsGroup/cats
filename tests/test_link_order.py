"""ContentMesh.linkOrder — combined Function/Structure lineage helper."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cats.network import ContentMesh


def _cat_response_fixture(
    *,
    function_cid='QmFn',
    structure_cid='QmStruct',
    data_cid='QmDataOut',
    structure=None,
):
    if structure is None:
        structure = {
            'root_cid': 'QmRoot',
            'plant_cid': 'QmPlant',
            'infrastructure_cid': 'QmInfra',
        }
    prev_process = {
        'ingress_subproc_cid': 'QmIn',
        'integrated_subproc_cid': 'QmInt',
        'egress_subproc_cid': 'QmEg',
        'integration_cache_subproc_cid': 'QmCache',
    }
    prev_infrafunction = {'infrafunction_subproc_cid': 'QmIfr'}
    prev_function = {
        'process_cid': 'QmProcBind',
        'infrafunction_cid': 'QmIfrBind',
        'process_source_cid': 'QmProcSrc',
        'infrafunction_source_cid': 'QmIfrSrc',
    }
    cat_response = {
        'bom': {
            'invoice_cid': 'QmInv',
            'log_cid': 'QmLog',
        }
    }

    def _cat(cid):
        if cid == 'QmInv':
            return json.dumps({'order_cid': 'QmOrder', 'data_cid': data_cid})
        if cid == 'QmOrder':
            return json.dumps({
                'function_cid': function_cid,
                'structure_cid': structure_cid,
                'invoice_cid': 'QmInvOld',
                'structure_filepath': 'structure',
                'endpoint': 'http://127.0.0.1:5000/cat/node/init',
            })
        if cid == function_cid:
            return json.dumps(prev_function)
        if cid == structure_cid:
            return json.dumps(structure)
        if cid == 'QmInvOld':
            return json.dumps({'data_cid': data_cid})
        if cid == 'QmProcBind':
            return json.dumps(prev_process)
        if cid == 'QmIfrBind':
            return json.dumps(prev_infrafunction)
        if cid == 'QmLog':
            return json.dumps({})
        return '{}'

    return cat_response, _cat, structure, function_cid, structure_cid, data_cid


def _write_structure_tree(tmp_path: Path):
    structure = tmp_path / 'structure'
    (structure / 'plant').mkdir(parents=True)
    (structure / 'infrastructure').mkdir(parents=True)
    (structure / 'main.tf').write_text('module "plant" { source = "./plant" }\n')
    (structure / 'outputs.tf').write_text('output "x" { value = 1 }\n')
    (structure / '.terraform.lock.hcl').write_text('# lock\n')
    (structure / 'plant' / 'main.tf').write_text('# plant\n')
    (structure / 'infrastructure' / 'main.tf').write_text('# infra\n')
    return structure


def _last_order_json(fake):
    return json.loads(
        next(
            args[0]
            for args, _ in reversed(fake.add_str.call_args_list)
            if '"endpoint"' in args[0] and '"function_cid"' in args[0]
        )
    )


def _invoice_payloads(fake):
    return [
        json.loads(args[0])
        for args, _ in fake.add_str.call_args_list
        if args[0].startswith('{"data_cid"')
    ]


def test_link_order_function_only(monkeypatch, tmp_path):
    """linkOrder Function-only mutates function_cid and chains prior data_cid."""
    fake = MagicMock()
    fake.add_str.side_effect = lambda s: f'cid-{hash(s) & 0xFFFF:x}'
    fake.add_pyobj.side_effect = lambda *_a, **_k: 'QmNewPy'

    cat_response, _cat, _, function_cid, structure_cid, data_cid = (
        _cat_response_fixture()
    )
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')

    order_req = client.linkOrder(
        cat_response, integrated_subproc=lambda: 'new'
    )
    assert order_req['order_cid']

    order = _last_order_json(fake)
    assert order['function_cid'] != function_cid
    assert order['structure_cid'] == structure_cid
    assert order['endpoint'] == 'http://127.0.0.1:5000/cat/node/init'
    assert _invoice_payloads(fake) == [{'data_cid': data_cid}]


def test_link_order_structure_only(monkeypatch, tmp_path):
    """linkOrder Structure-only mutates pairing and keeps function_cid."""
    fake = MagicMock()
    fake.add_str.side_effect = lambda s: f'cid-{hash(s) & 0xFFFF:x}'

    cat_response, _cat, prev_structure, function_cid, structure_cid, data_cid = (
        _cat_response_fixture()
    )
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')

    client.linkOrder(cat_response, plant_cid='QmPlantV2')

    order = _last_order_json(fake)
    assert order['function_cid'] == function_cid
    assert order['structure_cid'] != structure_cid
    assert order['structure_filepath'] == 'structure'

    pairing = json.loads(
        next(
            args[0]
            for args, _ in fake.add_str.call_args_list
            if '"root_cid"' in args[0]
            and '"plant_cid"' in args[0]
            and '"infrastructure_cid"' in args[0]
        )
    )
    assert pairing == {
        'root_cid': prev_structure['root_cid'],
        'plant_cid': 'QmPlantV2',
        'infrastructure_cid': prev_structure['infrastructure_cid'],
    }
    assert _invoice_payloads(fake) == [{'data_cid': data_cid}]


def test_link_order_both_sides_single_invoice(monkeypatch, tmp_path):
    """linkOrder can change Function and Structure with one Invoice data_cid."""
    fake = MagicMock()
    fake.add_str.side_effect = lambda s: f'cid-{hash(s) & 0xFFFF:x}'
    fake.add_pyobj.side_effect = lambda *_a, **_k: 'QmNewPy'

    cat_response, _cat, _, function_cid, structure_cid, data_cid = (
        _cat_response_fixture()
    )
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')

    structure = _write_structure_tree(tmp_path)

    def _cid_dir(path):
        name = Path(path).name
        return f'QmNew{name}', name

    monkeypatch.setattr(client, 'cidDir', _cid_dir)

    client.linkOrder(
        cat_response,
        integrated_subproc=lambda: 'new',
        structure_filepath=str(structure),
    )

    order = _last_order_json(fake)
    assert order['function_cid'] != function_cid
    assert order['structure_cid'] != structure_cid
    assert order['structure_filepath'] == 'structure'
    assert _invoice_payloads(fake) == [{'data_cid': data_cid}]


def test_link_order_fails_when_neither_side(monkeypatch, tmp_path):
    """linkOrder requires at least one Function or Structure mutation."""
    fake = MagicMock()
    cat_response, _cat, _, _, _, _ = _cat_response_fixture()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)

    with pytest.raises(RuntimeError, match='requires a Function slot change'):
        client.linkOrder(cat_response)


def test_link_order_fails_when_structure_pairing_unchanged(monkeypatch, tmp_path):
    """linkOrder rejects Structure overrides that leave pairing unchanged."""
    fake = MagicMock()
    fake.add_str.side_effect = lambda s: f'cid-{hash(s) & 0xFFFF:x}'
    cat_response, _cat, prev_structure, _, _, _ = _cat_response_fixture()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)

    with pytest.raises(RuntimeError, match='unchanged structure pairing'):
        client.linkOrder(
            cat_response, plant_cid=prev_structure['plant_cid']
        )
