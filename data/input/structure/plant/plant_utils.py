"""Plant [SaaS] context helpers for deploy-time dispatch / BOM observation.

Ships inside `plant/` so it is part of `plant_cid` (directory model).
Owns PlantContext resolution from terraform outputs, credential-free snapshots,
Plant-specific Terraform/kind stale-state cleanup, and the Ray PlantPort adapter
(``RayPlantPort`` / ``plant_port_from_context``). Ray-specific observation JSON
keys and TF resource addresses stay here (this Plant's SaaS shape); InfraFunction
speaks Function-owned ``PlantPort`` only.

See docs/DASHBOARDS.md and docs/BOM.md.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

UTILS_FILENAME = 'plant_utils.py'
ENTRYPOINT_FILENAME = 'ray_job_result_entrypoint.py'
COMPUTE_UTILS_FILENAME = 'ray_compute_utils.py'
JOB_ENTRYPOINT_NAME = 'entrypoint.py'

# Terraform / kind identifiers for this Plant (module.plant in Structure root).
_KIND_CLUSTER_NAME = 'cats'
_KIND_CLUSTER_RESOURCE = 'module.plant.kind_cluster.default'
# Resources that depend on kind_cluster.default and thus can't be reconciled
# (or even refreshed) once its cluster is gone from the host.
_KIND_DEPENDENT_RESOURCES = (
    'module.plant.helm_release.ray-cluster',
    'module.plant.helm_release.kuberay-operator',
    'module.plant.kubernetes_service.ray_dashboard_nodeport',
)


@dataclass(frozen=True)
class PlantContext:
    """Plant observation handle; Ray dashboard URL feeds RayPlantPort."""

    job_endpoint: Optional[str]
    kind_cluster_name: Optional[str]
    kubeconfig_context: Optional[str]
    # BOM observation fields (tool-specific JSON keys; not Executor vocabulary).
    ray_release_name: Optional[str]
    ray_dashboard_address: Optional[str]

    def snapshot(self, *, rebuilt, applied_structure_cid) -> dict:
        """Credential-free dict for plant_as_executed (JSON keys stable)."""
        return {
            'kind_cluster_name': self.kind_cluster_name,
            'kubeconfig_context': self.kubeconfig_context,
            'ray_release_name': self.ray_release_name,
            'ray_dashboard_address': self.ray_dashboard_address,
            'applied_structure_cid': applied_structure_cid,
            'rebuilt': rebuilt,
        }

    @classmethod
    def from_terraform_outputs(cls, get_output) -> 'PlantContext':
        """Build from a callable name -> raw terraform output string."""
        kind_cluster_name = get_output('plant_kind_cluster_name')
        kubeconfig_context = get_output('plant_kubeconfig_context')
        ray_release_name = get_output('plant_ray_release_name')
        ray_dashboard_address = get_output('plant_ray_dashboard_address') or None
        return cls(
            job_endpoint=ray_dashboard_address,
            kind_cluster_name=kind_cluster_name or None,
            kubeconfig_context=kubeconfig_context or None,
            ray_release_name=ray_release_name or None,
            ray_dashboard_address=ray_dashboard_address,
        )


class RayPlantPort:
    """PlantPort adapter: Ray Job Submission against KubeRay dashboard URL."""

    def __init__(self, job_endpoint: str, *, connect_timeout: int = 60, poll_interval: float = 1):
        if not job_endpoint:
            raise RuntimeError('RayPlantPort requires a non-empty job_endpoint')
        self.job_endpoint = job_endpoint
        self.connect_timeout = connect_timeout
        self.poll_interval = poll_interval
        self._client = None

    def _connect(self):
        from ray.job_submission import JobSubmissionClient

        deadline = time.time() + self.connect_timeout
        while True:
            try:
                return JobSubmissionClient(self.job_endpoint)
            except Exception:
                if time.time() >= deadline:
                    raise
                time.sleep(self.poll_interval)

    @property
    def client(self):
        if self._client is None:
            self._client = self._connect()
        return self._client

    def submit_job(self, *, entrypoint: str, working_dir: str) -> str:
        # Plant-owned Ray landing (plant_cid): stage before Job Submission.
        write_job_result_entrypoint(working_dir)
        write_job_compute_utils(working_dir)
        return self.client.submit_job(
            entrypoint=entrypoint,
            runtime_env={'working_dir': working_dir},
        )

    def wait(self, job_id: str) -> None:
        from ray.job_submission import JobStatus

        status = self.client.get_job_status(job_id)
        while status not in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.STOPPED):
            time.sleep(self.poll_interval)
            status = self.client.get_job_status(job_id)

        if status != JobStatus.SUCCEEDED:
            logs = self.client.get_job_logs(job_id)
            raise RuntimeError(
                f'Ray job {job_id} on Plant job_endpoint {self.job_endpoint} '
                f'ended in {status}:\n{logs}'
            )


def write_job_result_entrypoint(job_dir):
    """Copy Order-submitted ray_job_result_entrypoint.py into the job working_dir.

    Ray submits ``python entrypoint.py``; the source ships beside this module
    in ``plant/`` so it is part of ``plant_cid``.
    """
    source = os.path.join(os.path.dirname(os.path.abspath(__file__)), ENTRYPOINT_FILENAME)
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    shutil.copyfile(source, os.path.join(job_dir, JOB_ENTRYPOINT_NAME))


def write_job_compute_utils(job_dir):
    """Copy RayComputePort adapter into the job working_dir for entrypoint import."""
    source = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), COMPUTE_UTILS_FILENAME
    )
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    shutil.copyfile(source, os.path.join(job_dir, COMPUTE_UTILS_FILENAME))


def plant_port_from_context(plant) -> RayPlantPort:
    """Build RayPlantPort from PlantContext (or any object with job_endpoint).

    Objects that already implement ``submit_job`` / ``wait`` are returned as-is.
    """
    if hasattr(plant, 'submit_job') and hasattr(plant, 'wait'):
        return plant
    job_endpoint = getattr(plant, 'job_endpoint', None)
    if not job_endpoint:
        raise RuntimeError(
            'PlantContext.job_endpoint is required to build RayPlantPort'
        )
    return RayPlantPort(job_endpoint)


def load_plant_utils(structure_home: str):
    """importlib-load this module from a materialized Structure tree."""
    path = os.path.join(structure_home, 'plant', UTILS_FILENAME)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(
        'plant_plant_utils', path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Required before exec_module so @dataclass can resolve cls.__module__.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _subproc_run(cmd, cwd=None):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        text=True,
        cwd=cwd,
    )


def _kind_cluster_names() -> set:
    proc = _subproc_run('kind get clusters')
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _terraform_state_resources(terraform_bin: str, structure_home: str) -> set:
    proc = _subproc_run(f'{terraform_bin} state list', cwd=structure_home)
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def cleanup_orphan_kind_cluster(
    structure_home: str,
    terraform_bin: str,
    *,
    configure_tf_data_dir=None,
):
    """Remove a leftover kind cluster when it exists on the host but not in state."""
    if configure_tf_data_dir is not None:
        configure_tf_data_dir(structure_home)

    clusters = _kind_cluster_names()
    if _KIND_CLUSTER_NAME not in clusters:
        return

    state = _terraform_state_resources(terraform_bin, structure_home)
    if _KIND_CLUSTER_RESOURCE in state:
        return

    print(
        f'Removing orphan kind cluster "{_KIND_CLUSTER_NAME}" '
        f'({_KIND_CLUSTER_RESOURCE} is not in Terraform state)'
    )
    proc = _subproc_run(f'kind delete cluster --name {_KIND_CLUSTER_NAME}')
    if proc.returncode != 0:
        raise RuntimeError(
            f'Failed to delete orphan kind cluster "{_KIND_CLUSTER_NAME}": '
            f'{proc.stderr.strip()}'
        )
    if proc.stdout.strip():
        print(proc.stdout.strip())


def cleanup_stale_kind_cluster_state(
    structure_home: str,
    terraform_bin: str,
    *,
    configure_tf_data_dir=None,
):
    """Remove state for the kind cluster and Plant dependents when the host
    has no kind cluster (e.g. Docker Desktop wiped containers under Terraform).

    Left alone, the next apply fails during refresh before it can recreate
    the Plant."""
    if configure_tf_data_dir is not None:
        configure_tf_data_dir(structure_home)

    state = _terraform_state_resources(terraform_bin, structure_home)
    clusters = _kind_cluster_names()
    if _KIND_CLUSTER_NAME in clusters:
        return

    stale_resources = [
        resource
        for resource in (*_KIND_DEPENDENT_RESOURCES, _KIND_CLUSTER_RESOURCE)
        if resource in state
    ]
    if not stale_resources:
        return

    print(
        f'No kind cluster named "{_KIND_CLUSTER_NAME}" on the host; removing '
        f'stale Terraform Plant state for: {", ".join(stale_resources)}'
    )
    proc = _subproc_run(
        f'{terraform_bin} state rm {" ".join(stale_resources)}',
        cwd=structure_home,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f'Failed to remove stale Terraform state for "{_KIND_CLUSTER_NAME}": '
            f'{proc.stderr.strip()}'
        )
    if proc.stdout.strip():
        print(proc.stdout.strip())


def cleanup_stale_plant_state(
    structure_home: str,
    terraform_bin: str,
    *,
    configure_tf_data_dir=None,
):
    """Heal Plant/kind Terraform drift before Structure apply (directory model).

    Parallel to InfraStructure object-store stale cleanup in obj_store_utils.
    """
    cleanup_orphan_kind_cluster(
        structure_home,
        terraform_bin,
        configure_tf_data_dir=configure_tf_data_dir,
    )
    cleanup_stale_kind_cluster_state(
        structure_home,
        terraform_bin,
        configure_tf_data_dir=configure_tf_data_dir,
    )
