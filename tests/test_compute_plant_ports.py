"""ComputePort, PlantPort, JobHandle, and Process/InfraFunction surface guards."""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESS_PY = (
    REPO_ROOT / 'data' / 'input' / 'function' / 'process' / 'callables.py'
)
INFRAFUNCTION_PY = (
    REPO_ROOT / 'data' / 'input' / 'function' / 'infrafunction' / 'actuator.py'
)
ENTRYPOINT_PY = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'plant'
    / 'ray_job_result_entrypoint.py'
)
RAY_COMPUTE_PY = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'plant'
    / 'ray_compute_utils.py'
)
OBJ_STORE_UTILS = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'infrastructure'
    / 'obj_store_utils.py'

)
PLANT_UTILS = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'plant'
    / 'plant_utils.py'
)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _FakeCompute:
    def __init__(self):
        self.calls = []

    def run_transfer(
        self, batch_fn, input_path, *, zip_with_range=False, num_partitions: int = 1
    ):
        self.calls.append((batch_fn, input_path, zip_with_range))
        return f'dataset-for-{input_path}'


class _FakePlantPort:
    def __init__(self):
        self.submitted = []
        self.waited = []

    def submit_job(self, *, entrypoint, working_dir):
        self.submitted.append((entrypoint, working_dir))
        return 'job-1'

    def wait(self, job_id):
        self.waited.append(job_id)


def test_process_uses_compute_port_no_ray():
    """Process hotFs use ComputePort and must not import Ray adapters."""
    from data.input.function import process as proc
    from data.input.function.process.compute_port import ComputePort

    text = PROCESS_PY.read_text(encoding='utf-8')
    for banned in ('import ray', 'ray.data', 'JobSubmissionClient', '_run_ray_batches'):
        assert banned not in text, banned

    fake = _FakeCompute()
    assert isinstance(fake, ComputePort)
    assert proc.process_0('/in', fake) == 'dataset-for-/in'
    assert fake.calls[0][2] is True  # zip_with_range
    assert proc.process_1('/in2', fake) == 'dataset-for-/in2'
    assert fake.calls[1][2] is False


def test_infrafunction_has_no_job_submission_client():
    """InfraFunction actuator must not import Ray Job Submission / ray.data."""
    text = INFRAFUNCTION_PY.read_text(encoding='utf-8')
    for banned in ('JobSubmissionClient', 'ray.data', 'import ray', 'from ray'):
        assert banned not in text, banned


def test_entrypoint_wires_compute_port():
    """Plant job entrypoint constructs RayComputePort and calls the subproc."""
    text = ENTRYPOINT_PY.read_text(encoding='utf-8')
    assert 'RayComputePort' in text
    assert "subproc('input', compute)" in text
    assert RAY_COMPUTE_PY.is_file()


def test_job_handle_begin_and_scratch_writes_config_only(tmp_path):
    """begin_job + write_job_scratch write ObjectStore config, not Ray landing."""
    ou = _load(OBJ_STORE_UTILS, 'infrastructure_obj_store_utils_ports')
    store = ou.ObjectStore(
        scratch_endpoint_host='http://127.0.0.1:9000',
        scratch_endpoint_pod='http://172.19.0.1:9000',
        scratch_bucket='cats-scratch',
        scratch_access_key='cats-scratch',
        scratch_secret_key='cats-scratch-secret',
    )
    handle = store.begin_job()
    assert handle.prefix.startswith('jobs/')
    assert store.result_uri(handle) == (
        f's3://{store.scratch_bucket}/{handle.result_key()}'
    )

    job_dir = tmp_path / 'job'
    job_dir.mkdir()
    store.write_job_scratch(str(job_dir), handle)
    assert (job_dir / 'object_store_scratch_config.json').is_file()
    assert not (job_dir / 'entrypoint.py').exists()
    assert not (job_dir / 'ray_compute_utils.py').exists()


def test_plant_port_from_context_and_passthrough():
    """plant_port_from_context wraps PlantContext and passes through PlantPorts."""
    pu = _load(PLANT_UTILS, 'plant_plant_utils_ports')
    ctx = pu.PlantContext(
        job_endpoint='http://127.0.0.1:8265',
        kind_cluster_name='cats',
        kubeconfig_context='kind-cats',
        ray_release_name='raycluster',
        ray_dashboard_address='http://127.0.0.1:8265',
    )
    port = pu.plant_port_from_context(ctx)
    assert isinstance(port, pu.RayPlantPort)
    assert port.job_endpoint == 'http://127.0.0.1:8265'

    fake = _FakePlantPort()
    assert pu.plant_port_from_context(fake) is fake


def test_ray_plant_port_submit_job_stages_landing(tmp_path, monkeypatch):
    """RayPlantPort.submit_job stages Plant landing files into working_dir."""
    pu = _load(PLANT_UTILS, 'plant_plant_utils_submit')
    job_dir = tmp_path / 'job'
    job_dir.mkdir()
    submitted = []

    class _FakeClient:
        def submit_job(self, *, entrypoint, runtime_env):
            submitted.append((entrypoint, runtime_env))
            return 'job-staged'

    port = pu.RayPlantPort(job_endpoint='http://127.0.0.1:8265')
    monkeypatch.setattr(port, '_client', _FakeClient())
    job_id = port.submit_job(
        entrypoint='python entrypoint.py',
        working_dir=str(job_dir),
    )
    assert job_id == 'job-staged'
    assert (job_dir / 'entrypoint.py').is_file()
    assert (job_dir / 'ray_compute_utils.py').is_file()
    assert (job_dir / 'entrypoint.py').read_text(
        encoding='utf-8'
    ) == ENTRYPOINT_PY.read_text(encoding='utf-8')
    assert (job_dir / 'ray_compute_utils.py').read_text(
        encoding='utf-8'
    ) == RAY_COMPUTE_PY.read_text(encoding='utf-8')
    assert submitted == [
        ('python entrypoint.py', {'working_dir': str(job_dir)}),
    ]


def test_infrafunction_subproc_uses_plant_port_and_job_handle(tmp_path, monkeypatch):
    """infrafunction_subproc submits via PlantPort and uses JobHandle scratch."""
    from data.input.function.infrafunction import actuator
    from data.input.function.infrafunction import infrafunction_subproc

    class _Store:
        def __init__(self):
            self.handles = []
            self.downloads = []

        def begin_job(self):
            from types import SimpleNamespace
            h = SimpleNamespace(prefix='jobs/test-uuid')
            self.handles.append(h)
            return h

        def write_job_scratch(self, job_dir, handle):
            Path(job_dir).joinpath('object_store_scratch_config.json').write_text(
                '{}'
            )

        def download_job_result(self, handle, output):
            self.downloads.append((handle.prefix, output))
            Path(output).mkdir(parents=True, exist_ok=True)

        def result_uri(self, handle):
            return f's3://cats-scratch/{handle.prefix}/result'

    store = _Store()
    plant = _FakePlantPort()
    input_dir = tmp_path / 'input'
    input_dir.mkdir()
    (input_dir / 'x.csv').write_text('a\n1\n')
    output = tmp_path / 'out'

    def _fake_subproc(x):
        return x

    def _stub_write(job_dir, input, integrated_subproc, object_store, handle):
        Path(job_dir).joinpath('subproc.pkl').write_bytes(b'x')
        object_store.write_job_scratch(job_dir, handle)

    monkeypatch.setattr(actuator, '_write_infrafunction_job_dir', _stub_write)

    out, handle = infrafunction_subproc(
        _fake_subproc, str(input_dir), str(output), store, plant,
    )
    assert out == str(output)
    assert handle.prefix == 'jobs/test-uuid'
    assert plant.submitted and plant.submitted[0][0] == 'python entrypoint.py'
    assert plant.waited == ['job-1']
    assert store.downloads == [('jobs/test-uuid', str(output))]
