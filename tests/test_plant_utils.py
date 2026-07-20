"""Unit tests for Plant directory-model plant_utils / PlantContext."""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLANT_UTILS = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'modules'
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


def test_plant_context_from_terraform_outputs():
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
