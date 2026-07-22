"""Function source directory CIDs + pickle bind hybrid on function_cid."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cats.network import (
    MeshClient,
    resolve_function_package_dirs,
    stage_function_package,
)


def _write_function_fixture(input_home: Path, *, with_pycache=True):
    process = input_home / 'function' / 'process'
    ifr = input_home / 'function' / 'infrafunction'
    process.mkdir(parents=True)
    ifr.mkdir(parents=True)
    (process / '__init__.py').write_text('# process\n')
    (process / 'callables.py').write_text('def process_0():\n    pass\n')
    (ifr / '__init__.py').write_text('# infrafunction\n')
    (ifr / 'actuator.py').write_text('def infrafunction_subproc():\n    pass\n')
    if with_pycache:
        cache = process / '__pycache__'
        cache.mkdir()
        (cache / 'callables.cpython-312.pyc').write_bytes(b'\x00pyc')
        (process / 'orphan.pyc').write_bytes(b'\x00pyc')
    return process, ifr


def test_resolve_function_package_dirs(tmp_path):
    """resolve_function_package_dirs finds process and infrafunction packages."""
    structure = tmp_path / 'structure'
    structure.mkdir()
    _write_function_fixture(tmp_path)
    paths = resolve_function_package_dirs(str(structure))
    assert Path(paths['process']).is_dir()
    assert Path(paths['infrafunction']).is_dir()


def test_resolve_function_package_dirs_fails_if_missing(tmp_path):
    """resolve_function_package_dirs raises when Function packages are missing."""
    structure = tmp_path / 'structure'
    structure.mkdir()
    with pytest.raises(FileNotFoundError, match='missing'):
        resolve_function_package_dirs(str(structure))


def test_stage_function_package_excludes_pycache(tmp_path):
    """stage_function_package copies sources and excludes __pycache__ / .pyc."""
    process, _ = _write_function_fixture(tmp_path)
    staging_parent = tmp_path / 'stage'
    staging_parent.mkdir()
    staged = stage_function_package(
        str(process), staging_parent=str(staging_parent), basename='process'
    )
    staged_path = Path(staged)
    assert staged_path.name == 'process'
    assert (staged_path / 'callables.py').is_file()
    assert not (staged_path / '__pycache__').exists()
    assert not (staged_path / 'orphan.pyc').exists()


def test_create_order_request_emits_source_cids(monkeypatch, tmp_path):
    """create_order_request emits process_source_cid and infrafunction_source_cid."""
    fake = MagicMock()
    fake.add_str.side_effect = lambda s: f'cid-{hash(s) & 0xFFFF:x}'
    fake.add_pyobj.side_effect = lambda *_a, **_k: 'QmPy'

    structure = tmp_path / 'structure'
    (structure / 'plant').mkdir(parents=True)
    (structure / 'infrastructure').mkdir(parents=True)
    (structure / 'main.tf').write_text('module "plant" { source = "./plant" }\n')
    (structure / 'outputs.tf').write_text('output "x" { value = 1 }\n')
    (structure / '.terraform.lock.hcl').write_text('# lock\n')
    (structure / 'plant' / 'x.tf').write_text('x')
    (structure / 'infrastructure' / 'y.tf').write_text('y')
    _write_function_fixture(tmp_path)
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'f.csv').write_text('a\n')

    def _cid_dir(path):
        name = Path(path).name
        return f'Qm{name}', name

    client = MeshClient(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cidDir', _cid_dir)

    client.create_order_request(
        ingress_subproc=lambda: None,
        integrated_subproc=lambda: None,
        egress_subproc=lambda: None,
        integration_cache_subproc=lambda: None,
        infrafunction_subproc=lambda: None,
        data_dirpath=str(data),
        structure_filepath=str(structure),
    )
    function_payload = json.loads(
        next(
            args[0]
            for args, _ in fake.add_str.call_args_list
            if '"process_source_cid"' in args[0]
            and '"infrafunction_source_cid"' in args[0]
        )
    )
    assert function_payload['process_source_cid'] == 'Qmprocess'
    assert function_payload['infrafunction_source_cid'] == 'Qminfrafunction'
    assert 'process_cid' in function_payload
    assert 'infrafunction_cid' in function_payload


def test_get_enhanced_bom_requires_function_source_cids(monkeypatch, tmp_path):
    """getEnhancedBom fails when function_cid lacks source CIDs."""
    fake = MagicMock()
    client = MeshClient(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    input_home = tmp_path / 'input'
    output_home = tmp_path / 'output'
    input_home.mkdir()
    output_home.mkdir()

    bom = {'invoice_cid': 'QmInv', 'log_cid': None, 'init_data_cid': 'QmData'}
    invoice = {'order_cid': 'QmOrder'}
    order = {
        'structure_cid': 'QmStruct',
        'structure_filepath': 'structure',
        'function_cid': 'QmFn',
        'invoice_cid': 'QmInv2',
    }
    structure = {
        'root_cid': 'QmRoot',
        'plant_cid': 'QmPlant',
        'infrastructure_cid': 'QmInfra',
    }
    # Legacy function pairing without source keys.
    function = {
        'process_cid': 'QmProcBind',
        'infrafunction_cid': 'QmIfrBind',
    }

    def _get(cid, filepath, output=None):
        dest_root = Path(output or tmp_path)
        path = dest_root / filepath
        path.parent.mkdir(parents=True, exist_ok=True)
        if filepath == 'bom.json':
            path.write_text(json.dumps(bom))
        elif filepath == 'invoice.json':
            path.write_text(json.dumps(invoice))
        elif filepath == 'order.json':
            path.write_text(json.dumps(order))
        elif filepath == 'structure-root':
            path.mkdir(parents=True, exist_ok=True)
            (path / 'main.tf').write_text('root\n')
            (path / 'outputs.tf').write_text('out\n')
            (path / '.terraform.lock.hcl').write_text('lock\n')
        elif filepath.endswith('/plant') or filepath.endswith('/infrastructure'):
            path.mkdir(parents=True, exist_ok=True)
        return filepath

    def _cat(cid):
        if cid == 'QmStruct':
            return json.dumps(structure)
        if cid == 'QmFn':
            return json.dumps(function)
        return '{}'

    monkeypatch.setattr(client, 'get', _get)
    monkeypatch.setattr(client, 'cat', _cat)

    with pytest.raises(RuntimeError, match='process_source_cid'):
        client.getEnhancedBom(
            'QmBom', INPUT_HOME=str(input_home), OUTPUT_HOME=str(output_home)
        )


def test_get_enhanced_bom_materializes_function_sources(monkeypatch, tmp_path):
    """getEnhancedBom fetches process/infrafunction source trees by source CID."""
    fake = MagicMock()
    client = MeshClient(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)

    input_home = tmp_path / 'input'
    output_home = tmp_path / 'output'
    input_home.mkdir()
    output_home.mkdir()

    bom = {'invoice_cid': 'QmInv', 'log_cid': None, 'init_data_cid': 'QmData'}
    invoice = {'order_cid': 'QmOrder'}
    order = {
        'structure_cid': 'QmStruct',
        'structure_filepath': 'structure',
        'function_cid': 'QmFn',
        'invoice_cid': 'QmInv2',
    }
    structure = {
        'root_cid': 'QmRoot',
        'plant_cid': 'QmPlant',
        'infrastructure_cid': 'QmInfra',
    }
    function = {
        'process_cid': 'QmProcBind',
        'infrafunction_cid': 'QmIfrBind',
        'process_source_cid': 'QmProcSrc',
        'infrafunction_source_cid': 'QmIfrSrc',
    }
    gets = []

    def _get(cid, filepath, output=None):
        gets.append((cid, filepath))
        dest_root = Path(output or tmp_path)
        path = dest_root / filepath
        path.parent.mkdir(parents=True, exist_ok=True)
        if filepath == 'bom.json':
            path.write_text(json.dumps(bom))
        elif filepath == 'invoice.json':
            path.write_text(json.dumps(invoice))
        elif filepath == 'order.json':
            path.write_text(json.dumps(order))
        elif filepath == 'structure-root':
            path.mkdir(parents=True, exist_ok=True)
            (path / 'main.tf').write_text('root\n')
            (path / 'outputs.tf').write_text('out\n')
            (path / '.terraform.lock.hcl').write_text('lock\n')
        elif filepath.endswith('/plant') or filepath.endswith('/infrastructure'):
            path.mkdir(parents=True, exist_ok=True)
        elif filepath == 'function/process':
            path.mkdir(parents=True, exist_ok=True)
            (path / 'callables.py').write_text('# from-order\n')
        elif filepath == 'function/infrafunction':
            path.mkdir(parents=True, exist_ok=True)
            (path / 'actuator.py').write_text('# from-order\n')
        return filepath

    def _cat(cid):
        if cid == 'QmStruct':
            return json.dumps(structure)
        if cid == 'QmFn':
            return json.dumps(function)
        return '{}'

    monkeypatch.setattr(client, 'get', _get)
    monkeypatch.setattr(client, 'cat', _cat)

    client.getEnhancedBom(
        'QmBom', INPUT_HOME=str(input_home), OUTPUT_HOME=str(output_home)
    )
    assert (input_home / 'function' / 'process' / 'callables.py').read_text() == (
        '# from-order\n'
    )
    assert (input_home / 'function' / 'infrafunction' / 'actuator.py').read_text() == (
        '# from-order\n'
    )
    assert ('QmProcSrc', 'function/process') in gets
    assert ('QmIfrSrc', 'function/infrafunction') in gets


def test_link_process_carries_source_cids(monkeypatch, tmp_path):
    """linkProcess preserves prior process_source_cid / infrafunction_source_cid."""
    fake = MagicMock()
    fake.add_str.side_effect = lambda s: f'cid-{hash(s) & 0xFFFF:x}'
    fake.add_pyobj.side_effect = lambda *_a, **_k: 'QmNewPy'

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
    order = {
        'function_cid': 'QmFn',
        'structure_cid': 'QmStruct',
        'invoice_cid': 'QmInvOld',
        'structure_filepath': 'structure',
        'flat': {'function': prev_function},
        'endpoint': 'http://127.0.0.1:5000/cat/node/init',
    }
    invoice = {
        'data_cid': 'QmData',
        'order_cid': 'QmOrder',
        'order': order,
    }
    cat_response = {
        'bom': {
            'invoice_cid': 'QmInv',
            'log_cid': 'QmLog',
            'plant_snapshot_cid': 'QmPlantSnap',
        }
    }

    def _cat(cid):
        if cid == 'QmInv':
            return json.dumps({'order_cid': 'QmOrder', 'data_cid': 'QmData'})
        if cid == 'QmOrder':
            return json.dumps({
                'function_cid': 'QmFn',
                'structure_cid': 'QmStruct',
                'invoice_cid': 'QmInvOld',
                'structure_filepath': 'structure',
                'endpoint': 'http://127.0.0.1:5000/cat/node/init',
            })
        if cid == 'QmFn':
            return json.dumps(prev_function)
        if cid == 'QmStruct':
            return json.dumps({
                'root_cid': 'QmRoot',
                'plant_cid': 'QmPlant',
                'infrastructure_cid': 'QmInfra',
            })
        if cid == 'QmInvOld':
            return json.dumps({'data_cid': 'QmData'})
        if cid == 'QmProcBind':
            return json.dumps(prev_process)
        if cid == 'QmIfrBind':
            return json.dumps(prev_infrafunction)
        if cid == 'QmLog':
            return json.dumps({})
        if cid == 'QmPlantSnap':
            return json.dumps({'rebuilt': False})
        return '{}'

    client = MeshClient(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)
    monkeypatch.setenv('CAT_NODE_HOST', '127.0.0.1')
    monkeypatch.setenv('CAT_NODE_PORT', '5000')

    # flatten_bom uses cat; linkProcess calls flatten_bom then rebuilds.
    client.linkProcess(cat_response, integrated_subproc=lambda: 'new')

    function_payload = json.loads(
        next(
            args[0]
            for args, _ in fake.add_str.call_args_list
            if '"process_source_cid"' in args[0]
            and '"infrafunction_source_cid"' in args[0]
            and '"process_cid"' in args[0]
        )
    )
    assert function_payload['process_source_cid'] == 'QmProcSrc'
    assert function_payload['infrafunction_source_cid'] == 'QmIfrSrc'


def test_link_process_fails_without_source_cids(monkeypatch, tmp_path):
    """linkProcess fails when prior function_cid lacks source CIDs."""
    fake = MagicMock()
    prev_function = {
        'process_cid': 'QmProcBind',
        'infrafunction_cid': 'QmIfrBind',
    }
    cat_response = {
        'bom': {
            'invoice_cid': 'QmInv',
            'log_cid': 'QmLog',
            'plant_snapshot_cid': 'QmPlantSnap',
        }
    }

    def _cat(cid):
        if cid == 'QmInv':
            return json.dumps({'order_cid': 'QmOrder', 'data_cid': 'QmData'})
        if cid == 'QmOrder':
            return json.dumps({
                'function_cid': 'QmFn',
                'structure_cid': 'QmStruct',
                'invoice_cid': 'QmInvOld',
                'structure_filepath': 'structure',
            })
        if cid == 'QmFn':
            return json.dumps(prev_function)
        if cid == 'QmStruct':
            return json.dumps({
                'root_cid': 'QmRoot',
                'plant_cid': 'QmPlant',
                'infrastructure_cid': 'QmInfra',
            })
        if cid == 'QmInvOld':
            return json.dumps({'data_cid': 'QmData'})
        if cid == 'QmLog':
            return json.dumps({})
        if cid == 'QmPlantSnap':
            return json.dumps({'rebuilt': False})
        return '{}'

    client = MeshClient(ipfsClient=fake, CATS_HOME=str(tmp_path))
    monkeypatch.setattr(client, 'ensure_bootstrap_content_store', lambda: None)
    monkeypatch.setattr(client, 'cat', _cat)

    with pytest.raises(RuntimeError, match='process_source_cid'):
        client.linkProcess(cat_response, integrated_subproc=lambda: 'new')
