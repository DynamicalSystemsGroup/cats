"""Unit tests for Plant directory-model plant_utils / PlantContext."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
PLANT_UTILS = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'plant'
    / 'plant_utils.py'
)


def _load_plant_utils():
    spec = importlib.util.spec_from_file_location(
        'plant_plant_utils', PLANT_UTILS
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


plant_utils = _load_plant_utils()


def _ok(stdout='', stderr=''):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)


def _fail(stderr='boom'):
    return SimpleNamespace(returncode=1, stdout='', stderr=stderr)


def test_plant_context_from_terraform_outputs():
    """PlantContext.from_terraform_outputs maps plant_* TF output keys."""
    outputs = {
        'plant_kind_cluster_name': 'cats',
        'plant_kubeconfig_context': 'kind-cats',
        'plant_ray_release_name': 'raycluster',
        'plant_ray_dashboard_address': 'http://127.0.0.1:8265',
    }
    ctx = plant_utils.PlantContext.from_terraform_outputs(outputs.get)
    assert ctx.job_endpoint == 'http://127.0.0.1:8265'
    assert ctx.kind_cluster_name == 'cats'
    assert ctx.ray_dashboard_address == 'http://127.0.0.1:8265'


def test_plant_context_job_endpoint_none_when_empty():
    """Empty dashboard address yields job_endpoint None."""
    outputs = {
        'plant_kind_cluster_name': 'cats',
        'plant_kubeconfig_context': 'kind-cats',
        'plant_ray_release_name': 'raycluster',
        'plant_ray_dashboard_address': '',
    }
    ctx = plant_utils.PlantContext.from_terraform_outputs(outputs.get)
    assert ctx.job_endpoint is None
    assert ctx.ray_dashboard_address is None


def test_plant_context_snapshot_shape():
    """PlantContext.snapshot records cluster fields without credentials."""
    ctx = plant_utils.PlantContext(
        job_endpoint='http://127.0.0.1:8265',
        kind_cluster_name='cats',
        kubeconfig_context='kind-cats',
        ray_release_name='raycluster',
        ray_dashboard_address='http://127.0.0.1:8265',
    )
    snap = ctx.snapshot(rebuilt=False, applied_structure_cid='QmTest')
    assert snap == {
        'kind_cluster_name': 'cats',
        'kubeconfig_context': 'kind-cats',
        'ray_release_name': 'raycluster',
        'ray_dashboard_address': 'http://127.0.0.1:8265',
        'applied_structure_cid': 'QmTest',
        'rebuilt': False,
    }


def test_load_plant_utils_from_structure_home():
    """load_plant_utils resolves PlantContext helpers from Structure home."""
    structure_home = str(REPO_ROOT / 'data' / 'input' / 'structure')
    mod = plant_utils.load_plant_utils(structure_home)
    assert hasattr(mod, 'PlantContext')
    assert hasattr(mod, 'cleanup_stale_plant_state')


def test_plant_kind_resource_addresses_live_in_utils():
    """This Ray/KubeRay Plant's TF addresses are Order-submitted, not executor."""
    assert plant_utils._KIND_CLUSTER_NAME == 'cats'
    assert plant_utils._KIND_CLUSTER_RESOURCE == 'module.plant.kind_cluster.default'
    assert 'module.plant.helm_release.ray-cluster' in plant_utils._KIND_DEPENDENT_RESOURCES
    assert (
        'module.plant.kubernetes_service.ray_dashboard_nodeport'
        in plant_utils._KIND_DEPENDENT_RESOURCES
    )


def test_write_job_landing_helpers_copy_from_plant(tmp_path):
    """write_job_* helpers copy Ray landing modules from the Plant tree."""
    job_dir = tmp_path / 'job'
    job_dir.mkdir()
    plant_utils.write_job_result_entrypoint(str(job_dir))
    plant_utils.write_job_compute_utils(str(job_dir))

    entry = job_dir / 'entrypoint.py'
    compute = job_dir / 'ray_compute_utils.py'
    assert entry.is_file()
    assert compute.is_file()
    plant_dir = PLANT_UTILS.parent
    assert entry.read_text(encoding='utf-8') == (
        plant_dir / 'ray_job_result_entrypoint.py'
    ).read_text(encoding='utf-8')
    assert compute.read_text(encoding='utf-8') == (
        plant_dir / 'ray_compute_utils.py'
    ).read_text(encoding='utf-8')


def test_kind_control_plane_running_requires_true():
    with patch.object(
        plant_utils,
        '_subproc_run',
        return_value=_ok(stdout='true\n'),
    ):
        assert plant_utils._kind_control_plane_running('cats') is True
    with patch.object(
        plant_utils,
        '_subproc_run',
        return_value=_ok(stdout='false\n'),
    ):
        assert plant_utils._kind_control_plane_running('cats') is False
    with patch.object(plant_utils, '_subproc_run', return_value=_fail()):
        assert plant_utils._kind_control_plane_running('cats') is False


def test_cleanup_stale_kind_cluster_state_heals_stopped_control_plane(tmp_path):
    """Listed-but-stopped kind must be deleted and TF Plant state removed."""
    calls = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        if cmd == 'kind get clusters':
            return _ok(stdout='cats\n')
        if 'docker inspect' in cmd and 'cats-control-plane' in cmd:
            return _ok(stdout='false\n')
        if cmd.startswith('kind delete cluster'):
            return _ok(stdout='Deleted cluster\n')
        if cmd.endswith('state list'):
            return _ok(
                stdout=(
                    'module.plant.kind_cluster.default\n'
                    'module.plant.helm_release.ray-cluster\n'
                )
            )
        if 'state rm' in cmd:
            return _ok(stdout='Removed\n')
        return _fail(f'unexpected: {cmd}')

    with patch.object(plant_utils, '_subproc_run', side_effect=fake_run):
        plant_utils.cleanup_stale_kind_cluster_state(str(tmp_path), 'terraform')

    assert any(c.startswith('kind delete cluster --name cats') for c in calls)
    assert any('state rm' in c and 'module.plant.kind_cluster.default' in c for c in calls)


def test_cleanup_stale_kind_cluster_state_skips_usable_cluster(tmp_path):
    """Healthy listed kind leaves Terraform state alone."""
    calls = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        if cmd == 'kind get clusters':
            return _ok(stdout='cats\n')
        if 'docker inspect' in cmd:
            return _ok(stdout='true\n')
        if cmd.endswith('state list'):
            return _ok(stdout='module.plant.kind_cluster.default\n')
        return _fail(f'unexpected: {cmd}')

    with patch.object(plant_utils, '_subproc_run', side_effect=fake_run):
        plant_utils.cleanup_stale_kind_cluster_state(str(tmp_path), 'terraform')

    assert not any('kind delete' in c for c in calls)
    assert not any('state rm' in c for c in calls)


def test_cleanup_orphan_kind_cluster_ignores_stopped_listing(tmp_path):
    """Stopped control-plane is not an orphan to keep; stale heal owns it."""
    calls = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        if cmd == 'kind get clusters':
            return _ok(stdout='cats\n')
        if 'docker inspect' in cmd:
            return _ok(stdout='false\n')
        return _fail(f'unexpected: {cmd}')

    with patch.object(plant_utils, '_subproc_run', side_effect=fake_run):
        plant_utils.cleanup_orphan_kind_cluster(str(tmp_path), 'terraform')

    assert not any('kind delete' in c for c in calls)
