"""Terraform module-cache readiness used by InfraStructure.initialize()."""
import json
from pathlib import Path

from cats.executor.structure import modules_installed


def test_modules_installed_false_when_cache_missing(tmp_path):
    assert modules_installed(str(tmp_path)) is False


def test_modules_installed_false_when_dirs_missing(tmp_path):
    modules_dir = tmp_path / '.terraform-data' / 'modules'
    modules_dir.mkdir(parents=True)
    (modules_dir / 'modules.json').write_text(
        json.dumps(
            {
                'Modules': [
                    {'Key': '', 'Source': '', 'Dir': '.'},
                    {
                        'Key': 'plant',
                        'Source': './plant',
                        'Dir': 'plant',
                    },
                ]
            }
        ),
        encoding='utf-8',
    )
    assert modules_installed(str(tmp_path)) is False


def test_modules_installed_true_when_dirs_exist(tmp_path):
    (tmp_path / 'plant').mkdir()
    (tmp_path / 'infrastructure').mkdir()
    modules_dir = tmp_path / '.terraform-data' / 'modules'
    modules_dir.mkdir(parents=True)
    (modules_dir / 'modules.json').write_text(
        json.dumps(
            {
                'Modules': [
                    {'Key': '', 'Source': '', 'Dir': '.'},
                    {
                        'Key': 'plant',
                        'Source': './plant',
                        'Dir': 'plant',
                    },
                    {
                        'Key': 'infrastructure',
                        'Source': './infrastructure',
                        'Dir': 'infrastructure',
                    },
                ]
            }
        ),
        encoding='utf-8',
    )
    assert modules_installed(str(tmp_path)) is True


def test_modules_installed_false_for_stale_modules_prefix(tmp_path):
    """Flatten layout: cache still pointing at modules/plant must force re-init."""
    (tmp_path / 'plant').mkdir()
    modules_dir = tmp_path / '.terraform-data' / 'modules'
    modules_dir.mkdir(parents=True)
    (modules_dir / 'modules.json').write_text(
        json.dumps(
            {
                'Modules': [
                    {'Key': '', 'Source': '', 'Dir': '.'},
                    {
                        'Key': 'plant',
                        'Source': './modules/plant',
                        'Dir': 'modules/plant',
                    },
                ]
            }
        ),
        encoding='utf-8',
    )
    assert modules_installed(str(tmp_path)) is False
