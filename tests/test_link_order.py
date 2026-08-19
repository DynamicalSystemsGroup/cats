"""ContentMesh.linkOrder — combined Function/Structure lineage helper."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cats.network import ContentMesh
from data.input.function.process import process_1


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
        if cid == 'QmProcBind':
            return json.dumps(prev_process)
        if cid == 'QmIfrBind':
            return json.dumps(prev_infrafunction)
        if cid == 'QmLog':
            return json.dumps({})
        return '{}'

    return cat_response, _cat, structure, function_id, structure_id, data_id


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


def _last_order(put_objs):
    return next(
        obj for obj in reversed(put_objs)
        if isinstance(obj, dict) and 'endpoint' in obj and 'function_uri' in obj
    )


def _invoice_payloads(put_objs):
    return [
        obj for obj in put_objs
        if isinstance(obj, dict) and set(obj) == {'data_uri'}
    ]


def test_link_order_function_only(monkeypatch, tmp_path):
    """linkOrder Function-only mutates function_id and chains prior data_id."""
    fake = MagicMock()

    cat_response, _cat, _, function_id, structure_id, data_id = (
        _cat_response_fixture()
    )
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')
    put_objs = _spy_put_json(client, monkeypatch)

    order_req = client.linkOrder(cat_response, integrated_subproc=process_1)
    assert order_req['content_id']
    assert 'order_cid' not in order_req
    assert 'invoice_cid' not in order_req
    assert 'order_uri' in order_req
    assert 'invoice_uri' in order_req

    order = _last_order(put_objs)
    assert order['function_uri'] != function_id
    assert order['structure_uri'] == structure_id
    assert order['endpoint'] == 'http://127.0.0.1:5000/cat/node/init'
    assert _invoice_payloads(put_objs) == [{'data_uri': data_id}]
    assert not any(k.endswith('_cid') for k in order)


def test_link_order_structure_only(monkeypatch, tmp_path):
    """linkOrder Structure-only mutates pairing and keeps function_id."""
    fake = MagicMock()

    cat_response, _cat, prev_structure, function_id, structure_id, data_id = (
        _cat_response_fixture()
    )
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')
    put_objs = _spy_put_json(client, monkeypatch)

    client.linkOrder(cat_response, plant_id='QmPlantV2')

    order = _last_order(put_objs)
    assert order['function_uri'] == function_id
    assert order['structure_uri'] != structure_id
    assert order['structure_filepath'] == 'structure'

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
    assert _invoice_payloads(put_objs) == [{'data_uri': data_id}]


def test_link_order_both_sides_single_invoice(monkeypatch, tmp_path):
    """linkOrder can change Function and Structure with one Invoice data_id."""
    fake = MagicMock()

    cat_response, _cat, _, function_id, structure_id, data_id = (
        _cat_response_fixture()
    )
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

    client.linkOrder(
        cat_response,
        integrated_subproc=process_1,
        structure_filepath=str(structure),
    )

    order = _last_order(put_objs)
    assert order['function_uri'] != function_id
    assert order['structure_uri'] != structure_id
    assert order['structure_filepath'] == 'structure'
    assert _invoice_payloads(put_objs) == [{'data_uri': data_id}]


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
    cat_response, _cat, prev_structure, _, _, _ = _cat_response_fixture()
    client = ContentMesh(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)

    with pytest.raises(RuntimeError, match='unchanged structure pairing'):
        client.linkOrder(
            cat_response, plant_id=prev_structure['plant_cid']
        )
