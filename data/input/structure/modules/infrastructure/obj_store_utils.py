"""InfraStructure [IaaS] object-store helpers (MinIO) for Ray job scratch.

Ships inside `modules/infrastructure` so it is part of `infrastructure_cid`
(directory model). Owns ObjectStore resolution, credential-free snapshots,
Ray-job scratch write/download (entrypoint + host retrieval), stale
Terraform/compose cleanup, and a local CLI. There is no CAT Node HTTP API —
operators use the MinIO Console / S3 API, or this module's CLI. Durable
retrieval remains IPFS `integration_data_cid`.

See docs/MinIO.md and docs/STORAGE.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

import pyarrow.fs

# Defaults match local.minio_* / cats-scratch in this module's main.tf.
_DEFAULT_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'http://127.0.0.1:9000')
_DEFAULT_BUCKET = os.environ.get('MINIO_BUCKET', 'cats-scratch')
_DEFAULT_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'cats-minio')
_DEFAULT_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'cats-minio-secret')

# Terraform / compose identifiers for the object-store stack (module.infrastructure).
_DOCKER_COMPOSE_OBJ_STORE_RESOURCE = (
    'module.infrastructure.shell_script.docker_compose_minio'
)
_OBJ_STORE_CONTAINER = 'structure-minio-1'

_JOB_UUID_RE = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)
_SAFE_NAME_RE = re.compile(r'^[A-Za-z0-9._-]+$')

UTILS_FILENAME = 'obj_store_utils.py'
ENTRYPOINT_FILENAME = 'ray_job_result_entrypoint.py'
JOB_ENTRYPOINT_NAME = 'entrypoint.py'


@dataclass(frozen=True)
class ObjectStore:
    endpoint_host: str
    endpoint_pod: str
    bucket: str
    access_key: str
    secret_key: str

    def result_uri(self, job_prefix: str) -> str:
        return f's3://{self.bucket}/{job_prefix}/result'

    def snapshot(self) -> dict:
        """Credential-free dict for BOM infrastructure_snapshot (JSON keys stable)."""
        return {
            'minio_endpoint_host': self.endpoint_host,
            'minio_endpoint_pod': self.endpoint_pod,
            'minio_bucket': self.bucket,
        }

    def as_cli_config(self) -> dict:
        return {
            'endpoint': self.endpoint_host,
            'bucket': self.bucket,
            'access_key': self.access_key,
            'secret_key': self.secret_key,
        }

    def write_ray_job_scratch(self, job_dir: str, job_prefix: str) -> None:
        """Write pod-reachable object-store config + Ray job result entrypoint.

        InfraFunction supplies subproc.pkl / input/; this owns MinIO scratch
        mechanics so Function does not embed S3FileSystem / key layout.
        """
        write_job_object_store_config(
            job_dir,
            endpoint=self.endpoint_pod,
            access_key=self.access_key,
            secret_key=self.secret_key,
            bucket=self.bucket,
            prefix=job_prefix,
        )
        write_job_result_entrypoint(job_dir)

    def download_job_result(self, job_prefix: str, output: str) -> None:
        """Host-side download of a completed job's result prefix."""
        download_job_result_prefix(self.as_cli_config(), job_prefix, output)

    @classmethod
    def from_terraform_outputs(cls, get_output) -> 'ObjectStore':
        """Build from a callable name -> raw terraform output string."""
        endpoint_host = get_output('infrastructure_minio_endpoint_host')
        endpoint_pod = get_output('infrastructure_minio_endpoint_pod')
        bucket = get_output('infrastructure_minio_bucket')
        access_key = get_output('infrastructure_minio_access_key')
        secret_key = get_output('infrastructure_minio_secret_key')
        missing = [
            name for name, value in (
                ('infrastructure_minio_endpoint_host', endpoint_host),
                ('infrastructure_minio_endpoint_pod', endpoint_pod),
                ('infrastructure_minio_bucket', bucket),
                ('infrastructure_minio_access_key', access_key),
                ('infrastructure_minio_secret_key', secret_key),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                'ObjectStore terraform outputs missing or empty: ' + ', '.join(missing)
            )
        return cls(
            endpoint_host=endpoint_host,
            endpoint_pod=endpoint_pod,
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
        )


def load_obj_store_utils(structure_home: str):
    """importlib-load this module from a materialized Structure tree."""
    path = os.path.join(
        structure_home, 'modules', 'infrastructure', UTILS_FILENAME
    )
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(
        'infrastructure_obj_store_utils', path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Required before exec_module so @dataclass can resolve cls.__module__.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Back-compat alias used by older call sites / drafts.
load_minIO_utils = load_obj_store_utils


def write_job_object_store_config(
    job_dir,
    *,
    endpoint,
    access_key,
    secret_key,
    bucket,
    prefix,
):
    """Write object_store_config.json for the Ray job (pod-reachable endpoint)."""
    path = os.path.join(job_dir, 'object_store_config.json')
    with open(path, 'w', encoding='utf-8') as config_file:
        json.dump({
            'endpoint': endpoint,
            'access_key': access_key,
            'secret_key': secret_key,
            'bucket': bucket,
            'prefix': prefix,
        }, config_file)


def write_job_result_entrypoint(job_dir):
    """Copy Order-submitted ray_job_result_entrypoint.py into the job working_dir.

    Ray submits `python entrypoint.py`; the source file ships beside this module
    in `modules/infrastructure` so it is part of `infrastructure_cid`.
    """
    source = os.path.join(os.path.dirname(os.path.abspath(__file__)), ENTRYPOINT_FILENAME)
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    shutil.copyfile(source, os.path.join(job_dir, JOB_ENTRYPOINT_NAME))


def download_job_result_prefix(config, job_prefix, output):
    """Download all files under bucket/job_prefix/result to output/."""
    fs = _s3_fs(config)
    os.makedirs(output, exist_ok=True)
    result_key = f"{config['bucket']}/{job_prefix}/result"
    for file_info in fs.get_file_info(
        pyarrow.fs.FileSelector(result_key, recursive=True)
    ):
        if file_info.type != pyarrow.fs.FileType.File:
            continue
        name = os.path.basename(file_info.path)
        with fs.open_input_stream(file_info.path) as src_file, \
                open(os.path.join(output, name), 'wb') as dst_file:
            dst_file.write(src_file.read())


def default_minio_config():
    return {
        'endpoint': _DEFAULT_ENDPOINT,
        'bucket': _DEFAULT_BUCKET,
        'access_key': _DEFAULT_ACCESS_KEY,
        'secret_key': _DEFAULT_SECRET_KEY,
    }


def _s3_fs(config):
    return pyarrow.fs.S3FileSystem(
        endpoint_override=config['endpoint'],
        access_key=config['access_key'],
        secret_key=config['secret_key'],
        scheme='http',
    )


def list_job_uuids(config):
    fs = _s3_fs(config)
    base = f"{config['bucket']}/jobs"
    try:
        infos = fs.get_file_info(pyarrow.fs.FileSelector(base, recursive=False))
    except (OSError, FileNotFoundError):
        return []
    jobs = []
    for info in infos:
        name = os.path.basename(info.path.rstrip('/'))
        if name and _JOB_UUID_RE.match(name):
            jobs.append(name)
    return sorted(jobs)


def list_job_files(config, job_uuid):
    if not _JOB_UUID_RE.match(job_uuid):
        raise ValueError('invalid job_uuid')
    fs = _s3_fs(config)
    result_key = f"{config['bucket']}/jobs/{job_uuid}/result"
    try:
        infos = fs.get_file_info(pyarrow.fs.FileSelector(result_key, recursive=True))
    except (OSError, FileNotFoundError):
        return []
    files = []
    for info in infos:
        if info.type != pyarrow.fs.FileType.File:
            continue
        files.append(os.path.basename(info.path))
    return sorted(files)


def read_job_file(config, job_uuid, name):
    if not _JOB_UUID_RE.match(job_uuid):
        raise ValueError('invalid job_uuid')
    if not _SAFE_NAME_RE.match(name):
        raise ValueError('invalid file name')
    fs = _s3_fs(config)
    path = f"{config['bucket']}/jobs/{job_uuid}/result/{name}"
    info = fs.get_file_info(path)
    if info.type != pyarrow.fs.FileType.File:
        raise FileNotFoundError(path)
    with fs.open_input_stream(path) as src:
        return src.read()


def minio_result_uri(config, job_uuid):
    return f"s3://{config['bucket']}/jobs/{job_uuid}/result"


def _subproc_run(cmd, cwd=None):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        text=True,
        cwd=cwd,
    )


def _docker_container_running(container: str) -> bool:
    proc = _subproc_run(
        f"docker ps --format '{{{{.Names}}}}' | grep -qx '{container}'"
    )
    return proc.returncode == 0


def _terraform_state_resources(terraform_bin: str, structure_home: str) -> set:
    proc = _subproc_run(f'{terraform_bin} state list', cwd=structure_home)
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def cleanup_stale_obj_store_state(
    structure_home: str,
    terraform_bin: str,
    *,
    configure_tf_data_dir=None,
):
    """Remove Terraform state for the object-store compose resource when the
    container is gone (scottwinkler/shell drift), so apply recreates it."""
    if configure_tf_data_dir is not None:
        configure_tf_data_dir(structure_home)

    state = _terraform_state_resources(terraform_bin, structure_home)
    if _DOCKER_COMPOSE_OBJ_STORE_RESOURCE not in state:
        return

    if _docker_container_running(_OBJ_STORE_CONTAINER):
        return

    print(
        f'Terraform state has "{_DOCKER_COMPOSE_OBJ_STORE_RESOURCE}" but container '
        f'"{_OBJ_STORE_CONTAINER}" is not running on the host; removing stale state '
        f'so apply recreates it'
    )
    proc = _subproc_run(
        f'{terraform_bin} state rm {_DOCKER_COMPOSE_OBJ_STORE_RESOURCE}',
        cwd=structure_home,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f'Failed to remove stale Terraform state for '
            f'"{_DOCKER_COMPOSE_OBJ_STORE_RESOURCE}": {proc.stderr.strip()}'
        )
    if proc.stdout.strip():
        print(proc.stdout.strip())


def _main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'List or fetch object-store Ray job scratch under cats-scratch/jobs/ '
            '(InfraStructure [IaaS]; no CAT Node API).'
        )
    )
    sub = parser.add_subparsers(dest='cmd', required=True)

    sub.add_parser('list-jobs', help='List job UUIDs under the scratch bucket')

    p_files = sub.add_parser('list-files', help='List CSV shards for a job UUID')
    p_files.add_argument('job_uuid')

    p_get = sub.add_parser('get-file', help='Download one CSV shard to stdout')
    p_get.add_argument('job_uuid')
    p_get.add_argument('name')

    args = parser.parse_args(argv)
    config = default_minio_config()

    if args.cmd == 'list-jobs':
        for job_uuid in list_job_uuids(config):
            print(f"{job_uuid}\t{minio_result_uri(config, job_uuid)}")
        return 0

    if args.cmd == 'list-files':
        for name in list_job_files(config, args.job_uuid):
            print(name)
        return 0

    if args.cmd == 'get-file':
        sys.stdout.buffer.write(read_job_file(config, args.job_uuid, args.name))
        return 0

    return 1


if __name__ == '__main__':
    raise SystemExit(_main())
