"""ContentMesh.linkStructure — Structure lineage twin of linkProcess."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cats.network import ContentMesh
from cats.network.registry import (
    assert_invoice_data_chain,
    assert_order_pairing_lineage,
)


def _cat_response_fixture(
    *,
    function_id='QmFn',
    structure_id='QmStruct',
    data_id='QmDataOut',
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
            return json.dumps({'order_cid': 'QmOrder', 'data_cid': data_id})
        if cid == 'QmOrder':
            return json.dumps({
                'function_cid': function_id,
                'structure_cid': structure_id,
                'invoice_cid': 'QmInvOld',
                'structure_filepath': 'structure',
                'endpoint': 'http://127.0.0.1:5000/cat/node/init',
            })
        if cid == function_id:
            return json.dumps(prev_function)
        if cid == structure_id:
            return json.dumps(structure)
        if cid == 'QmInvOld':
            return json.dumps({'data_cid': data_id})
        if cid == 'QmLog':
            return json.dumps({})
        return '{}'

    return cat_response, _cat, structure, function_id, data_id


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


def _spy_put_json(client, monkeypatch):
    put_objs = []
    real = client.put_json

    def _spy(obj, **kwargs):
        put_objs.append(obj)
        return real(obj, **kwargs)

    monkeypatch.setattr(client, 'put_json', _spy)
    return put_objs


def test_structure_pairing(monkeypatch, tmp_path):
    """structure_pairing addresses root, plant, and infrastructure directories."""
    fake = MagicMock()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    def _put_dir(path):
        name = Path(path).name
        return f'Qm{name}', name

    monkeypatch.setattr(client, 'put_dir', _put_dir)
    structure = _write_structure_tree(tmp_path)
    pairing = client.structure_pairing(str(structure))
    assert pairing == {
        'root_uri': 'Qmstructure-root',
        'plant_uri': 'Qmplant',
        'infrastructure_uri': 'Qminfrastructure',
    }


def test_link_structure_from_filepath(monkeypatch, tmp_path):
    """linkStructure from filepath rebuilds structure_id and chains data_id."""
    fake = MagicMock()

    cat_response, _cat, prev_structure, function_id, data_id = _cat_response_fixture()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')
    put_objs = _spy_put_json(client, monkeypatch)

    structure = _write_structure_tree(tmp_path)

    def _put_dir(path):
        name = Path(path).name
        return f'QmNew{name}', name

    monkeypatch.setattr(client, 'put_dir', _put_dir)

    order_req = client.linkStructure(
        cat_response, structure_filepath=str(structure)
    )
    assert order_req['content_id']
    assert 'order_cid' not in order_req
    assert 'invoice_cid' not in order_req
    assert 'order_uri' in order_req
    assert 'invoice_uri' in order_req

    order = next(
        obj for obj in reversed(put_objs)
        if isinstance(obj, dict) and 'endpoint' in obj and 'function_uri' in obj
    )
    assert_order_pairing_lineage(
        {'function_cid': function_id, 'structure_cid': 'QmStruct'},
        order,
        function='carried',
        structure='mutated',
    )
    assert order['structure_filepath'] == 'structure'
    assert order['endpoint'] == 'http://127.0.0.1:5000/cat/node/init'
    assert not any(k.endswith('_cid') for k in order)

    pairing = next(
        obj for obj in put_objs
        if isinstance(obj, dict)
        and 'root_uri' in obj
        and 'plant_uri' in obj
        and 'infrastructure_uri' in obj
    )
    assert pairing == {
        'root_uri': 'QmNewstructure-root',
        'plant_uri': 'QmNewplant',
        'infrastructure_uri': 'QmNewinfrastructure',
    }
    assert pairing != prev_structure

    invoice = next(
        obj for obj in put_objs
        if isinstance(obj, dict) and set(obj) == {'data_uri'}
    )
    assert_invoice_data_chain({'data_cid': data_id}, invoice)


def test_link_structure_plant_override_only(monkeypatch, tmp_path):
    """linkStructure can override plant_cid while keeping root/infra CIDs."""
    fake = MagicMock()

    cat_response, _cat, prev_structure, function_id, _ = _cat_response_fixture()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')
    put_objs = _spy_put_json(client, monkeypatch)

    client.linkStructure(cat_response, plant_id='QmPlantV2')

    pairing = next(
        obj for obj in put_objs
        if isinstance(obj, dict)
        and 'root_uri' in obj
        and 'plant_uri' in obj
        and 'infrastructure_uri' in obj
    )
    assert pairing == {
        'root_uri': prev_structure['root_cid'],
        'plant_uri': 'QmPlantV2',
        'infrastructure_uri': prev_structure['infrastructure_cid'],
    }

    order = next(
        obj for obj in reversed(put_objs)
        if isinstance(obj, dict) and 'endpoint' in obj and 'function_uri' in obj
    )
    assert_order_pairing_lineage(
        {'function_cid': function_id, 'structure_cid': 'QmStruct'},
        order,
        function='carried',
        structure='mutated',
    )
    assert order['structure_filepath'] == 'structure'


def test_link_structure_fails_without_root_cid(monkeypatch, tmp_path):
    """linkStructure fails when prior structure_id lacks root_cid."""
    fake = MagicMock()
    cat_response, _cat, _, _, _ = _cat_response_fixture(
        structure={'plant_cid': 'QmPlant', 'infrastructure_cid': 'QmInfra'}
    )
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)

    with pytest.raises(RuntimeError, match='missing root_cid'):
        client.linkStructure(cat_response, plant_id='QmX')


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
    cat_response, _cat, prev_structure, _, _ = _cat_response_fixture()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)

    with pytest.raises(RuntimeError, match='unchanged structure pairing'):
        client.linkStructure(
            cat_response, plant_id=prev_structure['plant_cid']
        )
