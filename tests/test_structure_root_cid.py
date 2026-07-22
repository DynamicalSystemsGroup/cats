"""Structure root_cid staging and apply-complete getEnhancedBom materialize."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cats.network import (
    STRUCTURE_ROOT_FILES,
    MeshClient,
    materialize_structure_root_files,
    stage_structure_root,
)


def _write_structure_fixture(structure: Path, *, with_noise=True):
    structure.mkdir(parents=True, exist_ok=True)
    (structure / 'main.tf').write_text('module "plant" { source = "./plant" }\n')
    (structure / 'outputs.tf').write_text('output "x" { value = 1 }\n')
    (structure / '.terraform.lock.hcl').write_text('# lock\n')
    (structure / 'plant').mkdir()
    (structure / 'infrastructure').mkdir()
    (structure / 'plant' / 'main.tf').write_text('# plant\n')
    (structure / 'infrastructure' / 'main.tf').write_text('# infra\n')
    if with_noise:
        (structure / 'terraform.tfstate').write_text('{}')
        (structure / '.applied-structure.cid').write_text('QmOld')
        (structure / '.terraform-data').mkdir()
        (structure / '.terraform-data' / 'x').write_text('y')


def test_stage_structure_root_copies_allowlist_only(tmp_path):
    structure = tmp_path / 'structure'
    _write_structure_fixture(structure)
    staging_parent = tmp_path / 'stage'
    staging_parent.mkdir()
    staging = stage_structure_root(str(structure), staging_parent=str(staging_parent))
    assert Path(staging).name == 'structure-root'
    names = {p.name for p in Path(staging).iterdir()}
    assert names == set(STRUCTURE_ROOT_FILES)
    assert 'terraform.tfstate' not in names
    assert 'plant' not in names


def test_stage_structure_root_fails_if_allowlist_incomplete(tmp_path):
    structure = tmp_path / 'structure'
    structure.mkdir()
    (structure / 'main.tf').write_text('x\n')
    with pytest.raises(FileNotFoundError, match='missing'):
        stage_structure_root(str(structure), staging_parent=str(tmp_path / 'stage'))


def test_materialize_structure_root_files_preserves_siblings(tmp_path):
    fetched = tmp_path / 'fetched'
    fetched.mkdir()
    (fetched / 'main.tf').write_text('root-main\n')
    (fetched / 'outputs.tf').write_text('root-out\n')
    (fetched / '.terraform.lock.hcl').write_text('lock\n')
    home = tmp_path / 'structure'
    home.mkdir()
    (home / 'terraform.tfstate').write_text('keep-me')
    (home / 'plant').mkdir()
    (home / 'plant' / 'main.tf').write_text('plant\n')

    materialize_structure_root_files(str(fetched), str(home))
    assert (home / 'main.tf').read_text() == 'root-main\n'
    assert (home / 'terraform.tfstate').read_text() == 'keep-me'
    assert (home / 'plant' / 'main.tf').read_text() == 'plant\n'


def test_get_enhanced_bom_requires_root_cid(monkeypatch, tmp_path):
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
        'plant_cid': 'QmPlant',
        'infrastructure_cid': 'QmInfra',
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
        return filepath

    function = {
        'process_cid': 'QmProcBind',
        'infrafunction_cid': 'QmIfrBind',
        'process_source_cid': 'QmProcSrc',
        'infrafunction_source_cid': 'QmIfrSrc',
    }

    def _cat(cid):
        if cid == 'QmStruct':
            return json.dumps(structure)
        if cid == 'QmFn':
            return json.dumps(function)
        return '{}'

    monkeypatch.setattr(client, 'get', _get)
    monkeypatch.setattr(client, 'cat', _cat)

    with pytest.raises(RuntimeError, match='root_cid'):
        client.getEnhancedBom(
            'QmBom', INPUT_HOME=str(input_home), OUTPUT_HOME=str(output_home)
        )


def test_get_enhanced_bom_materializes_root_then_modules(monkeypatch, tmp_path):
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
        gets.append((cid, filepath, output))
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
            (path / 'main.tf').write_text('from-order-root\n')
            (path / 'outputs.tf').write_text('out\n')
            (path / '.terraform.lock.hcl').write_text('lock\n')
        elif filepath.endswith('/plant'):
            path.mkdir(parents=True, exist_ok=True)
            (path / 'main.tf').write_text('plant\n')
        elif filepath.endswith('/infrastructure'):
            path.mkdir(parents=True, exist_ok=True)
            (path / 'main.tf').write_text('infra\n')
        elif filepath.endswith('function/process'):
            path.mkdir(parents=True, exist_ok=True)
            (path / '__init__.py').write_text('# process\n')
        elif filepath.endswith('function/infrafunction'):
            path.mkdir(parents=True, exist_ok=True)
            (path / '__init__.py').write_text('# ifr\n')
        return filepath

    def _cat(cid):
        if cid == 'QmStruct':
            return json.dumps(structure)
        if cid == 'QmFn':
            return json.dumps(function)
        return '{}'

    monkeypatch.setattr(client, 'get', _get)
    monkeypatch.setattr(client, 'cat', _cat)

    # Pre-existing state must survive root materialize.
    structure_home = input_home / 'structure'
    structure_home.mkdir()
    (structure_home / 'terraform.tfstate').write_text('state')

    enhanced, _ = client.getEnhancedBom(
        'QmBom', INPUT_HOME=str(input_home), OUTPUT_HOME=str(output_home)
    )
    assert enhanced['order']['structure_filepath'] == 'structure'
    assert (structure_home / 'main.tf').read_text() == 'from-order-root\n'
    assert (structure_home / 'terraform.tfstate').read_text() == 'state'
    assert (structure_home / 'plant' / 'main.tf').read_text() == 'plant\n'
    assert (structure_home / 'infrastructure' / 'main.tf').read_text() == 'infra\n'
    assert (input_home / 'function' / 'process' / '__init__.py').is_file()
    assert (input_home / 'function' / 'infrafunction' / '__init__.py').is_file()

    # Root fetch before plant/infra module fetches.
    module_gets = [(c, f) for c, f, _ in gets if c in ('QmRoot', 'QmPlant', 'QmInfra')]
    assert module_gets[0] == ('QmRoot', 'structure-root')
    assert ('QmPlant', 'structure/plant') in module_gets
    assert ('QmInfra', 'structure/infrastructure') in module_gets
    assert module_gets.index(('QmRoot', 'structure-root')) < module_gets.index(
        ('QmPlant', 'structure/plant')
    )
