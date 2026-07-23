"""ContentMesh.linkStructure — Structure lineage twin of linkProcess."""
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
        if cid == 'QmLog':
            return json.dumps({})
        return '{}'

    return cat_response, _cat, structure, function_cid, data_cid


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


def test_cid_structure_pairing(monkeypatch, tmp_path):
    """cid_structure_pairing CIDs root, plant, and infrastructure directories."""
    fake = MagicMock()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    def _cid_dir(path):
        name = Path(path).name
        return f'Qm{name}', name

    monkeypatch.setattr(client, 'cidDir', _cid_dir)
    structure = _write_structure_tree(tmp_path)
    pairing = client.cid_structure_pairing(str(structure))
    assert pairing == {
        'root_cid': 'Qmstructure-root',
        'plant_cid': 'Qmplant',
        'infrastructure_cid': 'Qminfrastructure',
    }


def test_link_structure_from_filepath(monkeypatch, tmp_path):
    """linkStructure from filepath rebuilds structure_cid and chains data_cid."""
    fake = MagicMock()
    fake.add_str.side_effect = lambda s: f'cid-{hash(s) & 0xFFFF:x}'

    cat_response, _cat, prev_structure, function_cid, data_cid = _cat_response_fixture()
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

    order_req = client.linkStructure(
        cat_response, structure_filepath=str(structure)
    )
    assert order_req['order_cid']

    order = json.loads(
        next(
            args[0]
            for args, _ in reversed(fake.add_str.call_args_list)
            if '"endpoint"' in args[0] and '"function_cid"' in args[0]
        )
    )
    assert order['function_cid'] == function_cid
    assert order['structure_cid'] != 'QmStruct'
    assert order['structure_filepath'] == 'structure'
    assert order['endpoint'] == 'http://127.0.0.1:5000/cat/node/init'

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
        'root_cid': 'QmNewstructure-root',
        'plant_cid': 'QmNewplant',
        'infrastructure_cid': 'QmNewinfrastructure',
    }
    assert pairing != prev_structure

    invoice = json.loads(
        next(
            args[0]
            for args, _ in fake.add_str.call_args_list
            if args[0].startswith('{"data_cid"')
        )
    )
    assert invoice == {'data_cid': data_cid}


def test_link_structure_plant_override_only(monkeypatch, tmp_path):
    """linkStructure can override plant_cid while keeping root/infra CIDs."""
    fake = MagicMock()
    fake.add_str.side_effect = lambda s: f'cid-{hash(s) & 0xFFFF:x}'

    cat_response, _cat, prev_structure, function_cid, _ = _cat_response_fixture()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')

    client.linkStructure(cat_response, plant_cid='QmPlantV2')

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

    order = json.loads(
        next(
            args[0]
            for args, _ in reversed(fake.add_str.call_args_list)
            if '"endpoint"' in args[0] and '"function_cid"' in args[0]
        )
    )
    assert order['function_cid'] == function_cid
    assert order['structure_filepath'] == 'structure'


def test_link_structure_fails_without_root_cid(monkeypatch, tmp_path):
    """linkStructure fails when prior structure_cid lacks root_cid."""
    fake = MagicMock()
    cat_response, _cat, _, _, _ = _cat_response_fixture(
        structure={'plant_cid': 'QmPlant', 'infrastructure_cid': 'QmInfra'}
    )
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)

    with pytest.raises(RuntimeError, match='missing root_cid'):
        client.linkStructure(cat_response, plant_cid='QmX')


def test_link_structure_fails_without_args(monkeypatch, tmp_path):
    """linkStructure requires structure_filepath or a pairing override."""
    fake = MagicMock()
    cat_response, _cat, _, _, _ = _cat_response_fixture()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)

    with pytest.raises(RuntimeError, match='requires structure_filepath'):
        client.linkStructure(cat_response)


def test_link_structure_fails_when_pairing_unchanged(monkeypatch, tmp_path):
    """linkStructure rejects overrides that leave structure pairing unchanged."""
    fake = MagicMock()
    fake.add_str.side_effect = lambda s: f'cid-{hash(s) & 0xFFFF:x}'
    cat_response, _cat, prev_structure, _, _ = _cat_response_fixture()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)

    with pytest.raises(RuntimeError, match='unchanged structure pairing'):
        client.linkStructure(
            cat_response, plant_cid=prev_structure['plant_cid']
        )
