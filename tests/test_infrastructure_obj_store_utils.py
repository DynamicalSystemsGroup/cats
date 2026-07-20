"""Unit tests for InfraStructure directory-model obj_store_utils / ObjectStore."""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OBJ_STORE_UTILS = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'modules'
    / 'infrastructure'
    / 'obj_store_utils.py'
)


def _load_obj_store_utils():
    spec = importlib.util.spec_from_file_location(
        'infrastructure_obj_store_utils', OBJ_STORE_UTILS
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


obj_store_utils = _load_obj_store_utils()


def test_object_store_result_uri():
    store = obj_store_utils.ObjectStore(
        endpoint_host='http://127.0.0.1:9000',
        endpoint_pod='http://172.19.0.1:9000',
        bucket='cats-scratch',
        access_key='cats-minio',
        secret_key='cats-minio-secret',
    )
    uri = store.result_uri('jobs/11111111-2222-3333-4444-555555555555')
    assert uri == 's3://cats-scratch/jobs/11111111-2222-3333-4444-555555555555/result'


def test_object_store_snapshot_excludes_credentials():
    store = obj_store_utils.ObjectStore(
        endpoint_host='http://127.0.0.1:9000',
        endpoint_pod='http://172.19.0.1:9000',
        bucket='cats-scratch',
        access_key='cats-minio',
        secret_key='cats-minio-secret',
    )
    snap = store.snapshot()
    assert snap == {
        'minio_endpoint_host': 'http://127.0.0.1:9000',
        'minio_endpoint_pod': 'http://172.19.0.1:9000',
        'minio_bucket': 'cats-scratch',
    }
    assert 'access_key' not in snap
    assert 'secret_key' not in snap


def test_object_store_from_terraform_outputs():
    outputs = {
        'infrastructure_minio_endpoint_host': 'http://127.0.0.1:9000',
        'infrastructure_minio_endpoint_pod': 'http://172.19.0.1:9000',
        'infrastructure_minio_bucket': 'cats-scratch',
        'infrastructure_minio_access_key': 'ak',
        'infrastructure_minio_secret_key': 'sk',
    }
    store = obj_store_utils.ObjectStore.from_terraform_outputs(outputs.get)
    assert store.bucket == 'cats-scratch'
    assert store.access_key == 'ak'


def test_minio_result_uri_helper():
    config = {'bucket': 'cats-scratch'}
    uri = obj_store_utils.minio_result_uri(
        config, '11111111-2222-3333-4444-555555555555'
    )
    assert uri == 's3://cats-scratch/jobs/11111111-2222-3333-4444-555555555555/result'


def test_list_job_files_rejects_bad_uuid():
    with pytest.raises(ValueError, match='invalid job_uuid'):
        obj_store_utils.list_job_files(
            obj_store_utils.default_minio_config(), 'not-a-uuid'
        )


def test_read_job_file_rejects_unsafe_name():
    with pytest.raises(ValueError, match='invalid file name'):
        obj_store_utils.read_job_file(
            obj_store_utils.default_minio_config(),
            '11111111-2222-3333-4444-555555555555',
            '../secret',
        )


def test_cli_list_jobs_help():
    with pytest.raises(SystemExit) as exc:
        obj_store_utils._main(['--help'])
    assert exc.value.code == 0


def test_write_ray_job_scratch_writes_config_and_entrypoint(tmp_path):
    store = obj_store_utils.ObjectStore(
        endpoint_host='http://127.0.0.1:9000',
        endpoint_pod='http://172.19.0.1:9000',
        bucket='cats-scratch',
        access_key='cats-minio',
        secret_key='cats-minio-secret',
    )
    job_dir = tmp_path / 'job'
    job_dir.mkdir()
    prefix = 'jobs/11111111-2222-3333-4444-555555555555'
    store.write_ray_job_scratch(str(job_dir), prefix)

    config_path = job_dir / 'object_store_config.json'
    entry_path = job_dir / 'entrypoint.py'
    assert config_path.is_file()
    assert entry_path.is_file()

    import json
    config = json.loads(config_path.read_text(encoding='utf-8'))
    assert config['endpoint'] == 'http://172.19.0.1:9000'
    assert config['bucket'] == 'cats-scratch'
    assert config['prefix'] == prefix
    assert 'access_key' in config
    assert 'object_store_config.json' in entry_path.read_text(encoding='utf-8')
    assert 'write_csv' in entry_path.read_text(encoding='utf-8')
    source = (
        REPO_ROOT
        / 'data'
        / 'input'
        / 'structure'
        / 'modules'
        / 'infrastructure'
        / 'ray_job_result_entrypoint.py'
    )
    assert entry_path.read_text(encoding='utf-8') == source.read_text(encoding='utf-8')


def test_load_obj_store_utils_from_structure_home():
    structure_home = str(
        REPO_ROOT / 'data' / 'input' / 'structure'
    )
    mod = obj_store_utils.load_obj_store_utils(structure_home)
    assert hasattr(mod, 'ObjectStore')
