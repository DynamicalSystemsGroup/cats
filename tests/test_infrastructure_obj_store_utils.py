"""Unit tests for InfraStructure directory-model obj_store_utils / ObjectStore."""
import importlib.util
import json
import sys
from pathlib import Path

import pyarrow.fs
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OBJ_STORE_UTILS = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'infrastructure'
    / 'obj_store_utils.py'
)
INFRA_MAIN_TF = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'infrastructure'
    / 'main.tf'
)
SCRATCH_COMPOSE = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'infrastructure'
    / 'minio_scratch_compose.yaml'
)
DURABLE_COMPOSE = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'infrastructure'
    / 'minio_durable_compose.yaml'
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


def _scratch_store(**overrides):
    kwargs = dict(
        scratch_endpoint_host='http://127.0.0.1:9000',
        scratch_endpoint_pod='http://172.19.0.1:9000',
        scratch_bucket='cats-scratch',
        scratch_access_key='cats-scratch',
        scratch_secret_key='cats-scratch-secret',
        durable_endpoint_host='http://127.0.0.1:9100',
        durable_endpoint_pod='http://172.19.0.1:9100',
        durable_bucket='cats-durable',
        durable_access_key='cats-durable',
        durable_secret_key='cats-durable-secret',
    )
    kwargs.update(overrides)
    return obj_store_utils.ObjectStore(**kwargs)


@pytest.fixture
def local_s3(tmp_path, monkeypatch):
    """Route _s3_fs through a SubTree LocalFileSystem under tmp_path."""
    root = tmp_path / 's3root'
    root.mkdir()

    def fake_s3_fs(config):
        local = pyarrow.fs.LocalFileSystem()
        return pyarrow.fs.SubTreeFileSystem(str(root), local)

    monkeypatch.setattr(obj_store_utils, '_s3_fs', fake_s3_fs)
    return root


def test_object_store_result_uri():
    """result_uri builds an s3 JobHandle URI and rejects non-JobHandle args."""
    store = _scratch_store()
    handle = obj_store_utils.JobHandle(
        prefix='jobs/11111111-2222-3333-4444-555555555555'
    )
    uri = store.result_uri(handle)
    assert uri == f's3://{store.scratch_bucket}/{handle.result_key()}'
    with pytest.raises(TypeError, match='JobHandle'):
        store.result_uri(handle.prefix)


def test_download_job_result_requires_job_handle(tmp_path):
    """download_job_result requires a JobHandle, not a raw prefix string."""
    store = _scratch_store()
    with pytest.raises(TypeError, match='JobHandle'):
        store.download_job_result('jobs/not-a-handle', str(tmp_path / 'out'))


def test_object_store_snapshot_excludes_credentials():
    """BOM snapshot includes scratch + durable endpoints/buckets, never creds."""
    store = _scratch_store()
    snap = store.snapshot()
    assert snap == {
        'minio_scratch_endpoint_host': 'http://127.0.0.1:9000',
        'minio_scratch_endpoint_pod': 'http://172.19.0.1:9000',
        'minio_scratch_bucket': 'cats-scratch',
        'minio_durable_endpoint_host': 'http://127.0.0.1:9100',
        'minio_durable_endpoint_pod': 'http://172.19.0.1:9100',
        'minio_durable_bucket': 'cats-durable',
    }
    assert 'access_key' not in snap
    assert 'secret_key' not in snap
    assert 'durable_access_key' not in snap
    assert 'durable_secret_key' not in snap


def test_object_store_from_terraform_outputs():
    """ObjectStore.from_terraform_outputs maps scratch + durable TF keys."""
    outputs = {
        'infrastructure_minio_scratch_endpoint_host': 'http://127.0.0.1:9000',
        'infrastructure_minio_scratch_endpoint_pod': 'http://172.19.0.1:9000',
        'infrastructure_minio_scratch_bucket': 'cats-scratch',
        'infrastructure_minio_scratch_access_key': 'ak',
        'infrastructure_minio_scratch_secret_key': 'sk',
        'infrastructure_minio_durable_endpoint_host': 'http://127.0.0.1:9100',
        'infrastructure_minio_durable_endpoint_pod': 'http://172.19.0.1:9100',
        'infrastructure_minio_durable_bucket': 'cats-durable',
        'infrastructure_minio_durable_access_key': 'dak',
        'infrastructure_minio_durable_secret_key': 'dsk',
    }
    store = obj_store_utils.ObjectStore.from_terraform_outputs(outputs.get)
    assert store.scratch_bucket == 'cats-scratch'
    assert store.scratch_access_key == 'ak'
    assert store.durable_bucket == 'cats-durable'
    assert store.durable_access_key == 'dak'
    assert store.durable_endpoint_pod == 'http://172.19.0.1:9100'


def test_object_store_from_terraform_outputs_requires_durable():
    """Missing durable TF outputs raise RuntimeError."""
    outputs = {
        'infrastructure_minio_scratch_endpoint_host': 'http://127.0.0.1:9000',
        'infrastructure_minio_scratch_endpoint_pod': 'http://172.19.0.1:9000',
        'infrastructure_minio_scratch_bucket': 'cats-scratch',
        'infrastructure_minio_scratch_access_key': 'ak',
        'infrastructure_minio_scratch_secret_key': 'sk',
    }
    with pytest.raises(RuntimeError, match='durable'):
        obj_store_utils.ObjectStore.from_terraform_outputs(outputs.get)


def test_minio_result_uri_helper():
    """minio_result_uri builds the JobHandle-shaped s3 result path."""
    config = {'bucket': 'cats-scratch'}
    uri = obj_store_utils.minio_result_uri(
        config, '11111111-2222-3333-4444-555555555555'
    )
    assert uri == 's3://cats-scratch/jobs/11111111-2222-3333-4444-555555555555/result'


def test_list_job_files_rejects_bad_uuid():
    """list_job_files rejects non-UUID job identifiers."""
    with pytest.raises(ValueError, match='invalid job_uuid'):
        obj_store_utils.list_job_files(
            obj_store_utils.default_scratch_minio_config(), 'not-a-uuid'
        )


def test_read_job_file_rejects_unsafe_name():
    """read_job_file rejects path-traversal style file names."""
    with pytest.raises(ValueError, match='invalid file name'):
        obj_store_utils.read_job_file(
            obj_store_utils.default_scratch_minio_config(),
            '11111111-2222-3333-4444-555555555555',
            '../secret',
        )


def test_cli_list_jobs_help():
    """CLI --help exits successfully."""
    with pytest.raises(SystemExit) as exc:
        obj_store_utils._main(['--help'])
    assert exc.value.code == 0


def test_write_job_scratch_writes_config_only(tmp_path):
    """write_job_scratch writes object_store_scratch_config.json only."""
    store = _scratch_store()
    job_dir = tmp_path / 'job'
    job_dir.mkdir()
    handle = obj_store_utils.JobHandle(
        prefix='jobs/11111111-2222-3333-4444-555555555555'
    )
    store.write_job_scratch(str(job_dir), handle)

    config_path = job_dir / 'object_store_scratch_config.json'
    assert config_path.is_file()
    assert not (job_dir / 'entrypoint.py').exists()
    assert not (job_dir / 'ray_compute_utils.py').exists()

    config = json.loads(config_path.read_text(encoding='utf-8'))
    assert config['endpoint'] == 'http://172.19.0.1:9000'
    assert config['bucket'] == 'cats-scratch'
    assert config['prefix'] == handle.prefix
    assert 'access_key' in config
    assert store.result_uri(handle) == (
        f's3://{store.scratch_bucket}/{handle.result_key()}'
    )


def test_write_job_durable_config(tmp_path):
    """write_job_durable_config stages durable ER config for future Ray jobs."""
    store = _scratch_store()
    job_dir = tmp_path / 'job'
    job_dir.mkdir()
    structure_cid = 'QmTestStructureCid01'
    store.write_job_durable_config(str(job_dir), structure_cid)
    path = job_dir / 'object_store_durable_config.json'
    assert path.is_file()
    config = json.loads(path.read_text(encoding='utf-8'))
    assert config['endpoint'] == 'http://172.19.0.1:9100'
    assert config['bucket'] == 'cats-durable'
    assert config['structure_cid'] == structure_cid
    assert config['structures_prefix'] == f'structures/{structure_cid}/er'


def test_er_uri_shape():
    """er_uri is structure-scoped under the durable bucket."""
    store = _scratch_store()
    uri = store.er_uri('QmStructA', 'edges')
    assert uri == 's3://cats-durable/structures/QmStructA/er/edges'
    assert store.durable_er_pointer_uri('edges') == (
        's3://cats-durable/er/current/edges'
    )


def test_promote_resolve_er_round_trip(local_s3):
    """promote_er writes er/current pointer; resolve_er reads it back."""
    store = _scratch_store()
    structure_cid = 'QmStructPromote01'
    name = 'edges'
    local_dir = local_s3.parent / 'er_src'
    local_dir.mkdir()
    (local_dir / 'table.csv').write_text('a,b\n1,2\n', encoding='utf-8')

    uri = store.write_er(structure_cid, name, str(local_dir))
    assert uri == store.er_uri(structure_cid, name)
    pointer = store.promote_er(structure_cid, name)
    assert pointer == {
        'uri': uri,
        'structure_cid': structure_cid,
        'name': name,
    }
    assert store.resolve_er(name) == pointer
    assert name in store.list_er(structure_cid)


def test_gc_er_protects_pointer_roots(local_s3):
    """gc-er keeps structure prefixes referenced by er/current; sweeps others."""
    store = _scratch_store()
    live = 'QmLiveStructure01'
    dead = 'QmDeadStructure01'
    src = local_s3.parent / 'er_gc'
    src.mkdir()
    (src / 'x.csv').write_text('x\n1\n', encoding='utf-8')

    store.write_er(live, 'edges', str(src))
    store.write_er(dead, 'edges', str(src))
    store.promote_er(live, 'edges')

    dry = store.gc_er(delete=False)
    assert dead in dry
    assert live not in dry

    deleted = store.gc_er(delete=True)
    assert dead in deleted
    assert live not in deleted
    assert store.list_er(live) == ['edges']
    assert store.list_er(dead) == []
    assert store.resolve_er('edges')['structure_cid'] == live


def test_gc_er_structure_refuses_without_force(local_s3):
    """Targeted gc-er --structure refuses when er/current still points at it."""
    store = _scratch_store()
    structure_cid = 'QmPinnedStruct01'
    src = local_s3.parent / 'er_pin'
    src.mkdir()
    (src / 'x.csv').write_text('x\n1\n', encoding='utf-8')
    store.write_er(structure_cid, 'nodes', str(src))
    store.promote_er(structure_cid, 'nodes')

    with pytest.raises(RuntimeError, match='referenced by'):
        store.gc_er(delete=True, structure_cid=structure_cid)

    store.gc_er(delete=True, structure_cid=structure_cid, force=True)
    assert store.resolve_er('nodes') is None
    assert store.list_er(structure_cid) == []


def test_scratch_destroy_does_not_wipe_durable_volume():
    """Scratch compose down -v must not reference the durable volume name."""
    scratch_yaml = SCRATCH_COMPOSE.read_text(encoding='utf-8')
    durable_yaml = DURABLE_COMPOSE.read_text(encoding='utf-8')
    main_tf = INFRA_MAIN_TF.read_text(encoding='utf-8')

    assert 'structure_minio_scratch_data' in scratch_yaml
    assert 'node_minio_durable_data' not in scratch_yaml
    assert 'node_minio_durable_data' in durable_yaml
    assert 'minio_durable_compose' in main_tf
    assert 'docker_compose_minio_scratch' in main_tf

    scratch_resource = main_tf.split('docker_compose_minio_durable')[0]
    durable_resource = main_tf.split('docker_compose_minio_durable', 1)[1]
    assert 'docker_compose_minio_scratch' in scratch_resource
    assert 'down -v' in scratch_resource
    assert 'down -v' not in durable_resource
    # Durable delete lifecycle is a no-op (`true`), not compose down.
    assert '\n      true\n' in durable_resource or 'true' in durable_resource


def test_load_obj_store_utils_from_structure_home():
    """load_obj_store_utils resolves ObjectStore from the Structure home tree."""
    structure_home = str(REPO_ROOT / 'data' / 'input' / 'structure')
    mod = obj_store_utils.load_obj_store_utils(structure_home)
    assert hasattr(mod, 'ObjectStore')
    assert hasattr(mod, 'gc_er_prefixes')
