"""InfraStructure [IaaS] object-store helpers (MinIO) for Plant scratch +
durable Entity Relationship.

Ships inside `infrastructure/` so it is part of `infrastructure_id`
(directory model). Owns ObjectStore resolution, credential-free snapshots,
job scratch config write / host download, durable Entity Relationship
structure-scoped writes + er/current pointer index, pointer-aware GC,
stale Terraform/compose cleanup, and a local CLI. Ray job landing
(entrypoint / ``RayComputePort``) is Plant-owned under ``plant_cid``.
There is no CAT Node HTTP API — operators use the MinIO Console / S3 API,
or this module's CLI. Durable CAT product retrieval remains IPFS
`integration_data_id` (scratch path); durable MinIO is for Entity
Relationship lookups across Structure generations.

See docs/MinIO.md and docs/STORAGE.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from typing import Optional

import pyarrow.fs

# Scratch defaults match local.minio_scratch_* / cats-scratch in main.tf.
_DEFAULT_SCRATCH_ENDPOINT = os.environ.get(
    'MINIO_SCRATCH_ENDPOINT',
    os.environ.get('MINIO_ENDPOINT', 'http://127.0.0.1:9000'),
)
_DEFAULT_SCRATCH_BUCKET = os.environ.get(
    'MINIO_SCRATCH_BUCKET', os.environ.get('MINIO_BUCKET', 'cats-scratch')
)
_DEFAULT_SCRATCH_ACCESS_KEY = os.environ.get(
    'MINIO_SCRATCH_ACCESS_KEY',
    os.environ.get('MINIO_ACCESS_KEY', 'cats-scratch'),
)
_DEFAULT_SCRATCH_SECRET_KEY = os.environ.get(
    'MINIO_SCRATCH_SECRET_KEY',
    os.environ.get('MINIO_SECRET_KEY', 'cats-scratch-secret'),
)

# Durable Entity Relationship defaults (hard-isolated MinIO).
_DEFAULT_DURABLE_ENDPOINT = os.environ.get(
    'MINIO_DURABLE_ENDPOINT', 'http://127.0.0.1:9100'
)
_DEFAULT_DURABLE_BUCKET = os.environ.get('MINIO_DURABLE_BUCKET', 'cats-durable')
_DEFAULT_DURABLE_ACCESS_KEY = os.environ.get(
    'MINIO_DURABLE_ACCESS_KEY', 'cats-durable'
)
_DEFAULT_DURABLE_SECRET_KEY = os.environ.get(
    'MINIO_DURABLE_SECRET_KEY', 'cats-durable-secret'
)

# Terraform / compose identifiers for the scratch object-store stack.
_DOCKER_COMPOSE_SCRATCH_RESOURCE = (
    'module.infrastructure.shell_script.docker_compose_minio_scratch'
)
_SCRATCH_OBJ_STORE_CONTAINER = 'structure-minio_scratch-1'
_DOCKER_COMPOSE_DURABLE_RESOURCE = (
    'module.infrastructure.shell_script.docker_compose_minio_durable'
)
_DURABLE_OBJ_STORE_CONTAINER = 'structure-minio_durable-1'

_JOB_UUID_RE = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)
# Structure CIDs / ER names: alphanumeric plus common CID/path-safe chars.
_SAFE_CID_RE = re.compile(r'^[A-Za-z0-9._-]+$')
_SAFE_NAME_RE = re.compile(r'^[A-Za-z0-9._-]+$')

UTILS_FILENAME = 'obj_store_utils.py'
ER_STRUCTURES_PREFIX = 'structures'
ER_CURRENT_PREFIX = 'er/current'


@dataclass(frozen=True)
class JobHandle:
    """Correlator for one Plant job's object-store scratch prefix."""

    prefix: str  # jobs/{uuid}

    def result_key(self) -> str:
        return f'{self.prefix}/result'


@dataclass(frozen=True)
class ObjectStore:
    # Scratch facet (Structure lifetime).
    scratch_endpoint_host: str
    scratch_endpoint_pod: str
    scratch_bucket: str
    scratch_access_key: str
    scratch_secret_key: str
    # Durable Entity Relationship facet (Node lifetime).
    durable_endpoint_host: str = _DEFAULT_DURABLE_ENDPOINT
    durable_endpoint_pod: str = _DEFAULT_DURABLE_ENDPOINT
    durable_bucket: str = _DEFAULT_DURABLE_BUCKET
    durable_access_key: str = _DEFAULT_DURABLE_ACCESS_KEY
    durable_secret_key: str = _DEFAULT_DURABLE_SECRET_KEY

    def begin_job(self) -> JobHandle:
        """Allocate a unique scratch prefix for one InfraFunction dispatch."""
        return JobHandle(prefix=f'jobs/{uuid.uuid4()}')

    def result_uri(self, handle: JobHandle) -> str:
        if not isinstance(handle, JobHandle):
            raise TypeError(
                f'result_uri requires JobHandle, got {type(handle).__name__}'
            )
        return f's3://{self.scratch_bucket}/{handle.result_key()}'

    def snapshot(self) -> dict:
        """Credential-free dict for object_store_as_executed (JSON keys stable)."""
        return {
            'minio_scratch_endpoint_host': self.scratch_endpoint_host,
            'minio_scratch_endpoint_pod': self.scratch_endpoint_pod,
            'minio_scratch_bucket': self.scratch_bucket,
            'minio_durable_endpoint_host': self.durable_endpoint_host,
            'minio_durable_endpoint_pod': self.durable_endpoint_pod,
            'minio_durable_bucket': self.durable_bucket,
        }

    def as_scratch_cli_config(self) -> dict:
        return {
            'endpoint': self.scratch_endpoint_host,
            'bucket': self.scratch_bucket,
            'access_key': self.scratch_access_key,
            'secret_key': self.scratch_secret_key,
        }

    def as_durable_cli_config(self) -> dict:
        return {
            'endpoint': self.durable_endpoint_host,
            'bucket': self.durable_bucket,
            'access_key': self.durable_access_key,
            'secret_key': self.durable_secret_key,
        }

    def write_job_scratch(self, job_dir: str, handle: JobHandle) -> None:
        """Write pod-reachable object-store config for the Plant job working_dir.

        InfraFunction supplies subproc.pkl / input/; Plant stages Ray landing
        on ``submit_job``. This owns MinIO scratch config so Function does not
        embed S3FileSystem / key layout.
        """
        write_job_scratch_object_store_config(
            job_dir,
            endpoint=self.scratch_endpoint_pod,
            access_key=self.scratch_access_key,
            secret_key=self.scratch_secret_key,
            bucket=self.scratch_bucket,
            prefix=handle.prefix,
        )

    def write_job_durable_config(self, job_dir: str, structure_id: str) -> None:
        """Write optional durable Entity Relationship config for future Ray jobs.

        Not consumed by the current scratch CSV entrypoint; stages pod-reachable
        durable endpoint + structure namespace prefix.
        """
        write_job_durable_object_store_config(
            job_dir,
            endpoint=self.durable_endpoint_pod,
            access_key=self.durable_access_key,
            secret_key=self.durable_secret_key,
            bucket=self.durable_bucket,
            structure_id=structure_id,
        )

    def download_job_result(self, handle: JobHandle, output: str) -> None:
        """Host-side download of a completed job's result prefix."""
        if not isinstance(handle, JobHandle):
            raise TypeError(
                f'download_job_result requires JobHandle, got '
                f'{type(handle).__name__}'
            )
        download_job_result_prefix(self.as_scratch_cli_config(), handle.prefix, output)

    def er_prefix(self, structure_id: str, name: str) -> str:
        """Key prefix under the durable bucket for one Entity Relationship."""
        _validate_structure_id(structure_id)
        _validate_er_name(name)
        return f'{ER_STRUCTURES_PREFIX}/{structure_id}/er/{name}'

    def er_uri(self, structure_id: str, name: str) -> str:
        """Structure-scoped durable Entity Relationship URI."""
        return f's3://{self.durable_bucket}/{self.er_prefix(structure_id, name)}'

    def durable_er_pointer_uri(self, name: str) -> str:
        """Global read-index URI for an Entity Relationship name."""
        _validate_er_name(name)
        return f's3://{self.durable_bucket}/{ER_CURRENT_PREFIX}/{name}'

    def write_er(self, structure_id: str, name: str, local_path: str) -> str:
        """Upload a local file or directory under the structure ER namespace.

        Returns the structure-scoped ``er_uri``.
        """
        return write_er_objects(
            self.as_durable_cli_config(),
            structure_id,
            name,
            local_path,
        )

    def promote_er(self, structure_id: str, name: str) -> dict:
        """Write ``er/current/<name>`` pointer JSON targeting structure NS URI."""
        return promote_er_pointer(
            self.as_durable_cli_config(), structure_id, name
        )

    def resolve_er(self, name: str) -> Optional[dict]:
        """Read global ``er/current/<name>`` pointer, or None if missing."""
        return resolve_er_pointer(self.as_durable_cli_config(), name)

    def list_er(self, structure_id: str) -> list:
        """List Entity Relationship names under a structure namespace."""
        return list_er_names(self.as_durable_cli_config(), structure_id)

    def gc_er(
        self,
        *,
        delete: bool = False,
        structure_id: Optional[str] = None,
        force: bool = False,
    ) -> list:
        """Pointer-aware durable GC; see ``gc_er_prefixes``."""
        return gc_er_prefixes(
            self.as_durable_cli_config(),
            delete=delete,
            structure_id=structure_id,
            force=force,
        )

    @classmethod
    def from_terraform_outputs(cls, get_output) -> 'ObjectStore':
        """Build from a callable name -> raw terraform output string."""
        scratch_endpoint_host = get_output(
            'infrastructure_minio_scratch_endpoint_host'
        )
        scratch_endpoint_pod = get_output(
            'infrastructure_minio_scratch_endpoint_pod'
        )
        scratch_bucket = get_output('infrastructure_minio_scratch_bucket')
        scratch_access_key = get_output(
            'infrastructure_minio_scratch_access_key'
        )
        scratch_secret_key = get_output(
            'infrastructure_minio_scratch_secret_key'
        )
        durable_endpoint_host = get_output(
            'infrastructure_minio_durable_endpoint_host'
        )
        durable_endpoint_pod = get_output(
            'infrastructure_minio_durable_endpoint_pod'
        )
        durable_bucket = get_output('infrastructure_minio_durable_bucket')
        durable_access_key = get_output(
            'infrastructure_minio_durable_access_key'
        )
        durable_secret_key = get_output(
            'infrastructure_minio_durable_secret_key'
        )
        missing = [
            name for name, value in (
                (
                    'infrastructure_minio_scratch_endpoint_host',
                    scratch_endpoint_host,
                ),
                (
                    'infrastructure_minio_scratch_endpoint_pod',
                    scratch_endpoint_pod,
                ),
                ('infrastructure_minio_scratch_bucket', scratch_bucket),
                (
                    'infrastructure_minio_scratch_access_key',
                    scratch_access_key,
                ),
                (
                    'infrastructure_minio_scratch_secret_key',
                    scratch_secret_key,
                ),
                (
                    'infrastructure_minio_durable_endpoint_host',
                    durable_endpoint_host,
                ),
                (
                    'infrastructure_minio_durable_endpoint_pod',
                    durable_endpoint_pod,
                ),
                ('infrastructure_minio_durable_bucket', durable_bucket),
                (
                    'infrastructure_minio_durable_access_key',
                    durable_access_key,
                ),
                (
                    'infrastructure_minio_durable_secret_key',
                    durable_secret_key,
                ),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                'ObjectStore terraform outputs missing or empty: '
                + ', '.join(missing)
            )
        return cls(
            scratch_endpoint_host=scratch_endpoint_host,
            scratch_endpoint_pod=scratch_endpoint_pod,
            scratch_bucket=scratch_bucket,
            scratch_access_key=scratch_access_key,
            scratch_secret_key=scratch_secret_key,
            durable_endpoint_host=durable_endpoint_host,
            durable_endpoint_pod=durable_endpoint_pod,
            durable_bucket=durable_bucket,
            durable_access_key=durable_access_key,
            durable_secret_key=durable_secret_key,
        )


def load_obj_store_utils(structure_home: str):
    """importlib-load this module from a materialized Structure tree."""
    path = os.path.join(
        structure_home, 'infrastructure', UTILS_FILENAME
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


def _validate_structure_id(structure_id: str) -> None:
    if not structure_id or not _SAFE_CID_RE.match(structure_id):
        raise ValueError('invalid structure_id')


def _validate_er_name(name: str) -> None:
    if not name or not _SAFE_NAME_RE.match(name):
        raise ValueError('invalid er name')


def _pointer_structure_id(ptr: dict) -> Optional[str]:
    """Read structure id from pointer JSON (``structure_id`` or legacy ``structure_cid``)."""
    return ptr.get('structure_id') or ptr.get('structure_cid')


def write_job_scratch_object_store_config(
    job_dir,
    *,
    endpoint,
    access_key,
    secret_key,
    bucket,
    prefix,
):
    """Write object_store_scratch_config.json (pod-reachable scratch MinIO)."""
    path = os.path.join(job_dir, 'object_store_scratch_config.json')
    with open(path, 'w', encoding='utf-8') as config_file:
        json.dump({
            'endpoint': endpoint,
            'access_key': access_key,
            'secret_key': secret_key,
            'bucket': bucket,
            'prefix': prefix,
        }, config_file)


def write_job_durable_object_store_config(
    job_dir,
    *,
    endpoint,
    access_key,
    secret_key,
    bucket,
    structure_id,
):
    """Write object_store_durable_config.json for future Ray ER writers."""
    _validate_structure_id(structure_id)
    path = os.path.join(job_dir, 'object_store_durable_config.json')
    with open(path, 'w', encoding='utf-8') as config_file:
        json.dump({
            'endpoint': endpoint,
            'access_key': access_key,
            'secret_key': secret_key,
            'bucket': bucket,
            'structure_id': structure_id,
            'structures_prefix': (
                f'{ER_STRUCTURES_PREFIX}/{structure_id}/er'
            ),
        }, config_file)


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


def default_scratch_minio_config():
    return {
        'endpoint': _DEFAULT_SCRATCH_ENDPOINT,
        'bucket': _DEFAULT_SCRATCH_BUCKET,
        'access_key': _DEFAULT_SCRATCH_ACCESS_KEY,
        'secret_key': _DEFAULT_SCRATCH_SECRET_KEY,
    }


# Back-compat alias.
default_minio_config = default_scratch_minio_config


def default_durable_minio_config():
    return {
        'endpoint': _DEFAULT_DURABLE_ENDPOINT,
        'bucket': _DEFAULT_DURABLE_BUCKET,
        'access_key': _DEFAULT_DURABLE_ACCESS_KEY,
        'secret_key': _DEFAULT_DURABLE_SECRET_KEY,
    }


def _s3_fs(config):
    return pyarrow.fs.S3FileSystem(
        endpoint_override=config['endpoint'],
        access_key=config['access_key'],
        secret_key=config['secret_key'],
        scheme='http',
    )


def _er_prefix(structure_id: str, name: str) -> str:
    _validate_structure_id(structure_id)
    _validate_er_name(name)
    return f'{ER_STRUCTURES_PREFIX}/{structure_id}/er/{name}'


def _er_uri(config, structure_id: str, name: str) -> str:
    return f"s3://{config['bucket']}/{_er_prefix(structure_id, name)}"


def _pointer_key(name: str) -> str:
    _validate_er_name(name)
    return f'{ER_CURRENT_PREFIX}/{name}'


def _ensure_parent_dir(fs, path: str) -> None:
    """Create parent directories for ``path`` when the filesystem supports it.

    S3 ignores empty prefixes; LocalFileSystem (tests) needs mkdir.
    """
    parent = path.rsplit('/', 1)[0] if '/' in path else ''
    if not parent:
        return
    try:
        fs.create_dir(parent, recursive=True)
    except (OSError, FileExistsError, NotImplementedError):
        pass


def write_er_objects(config, structure_id, name, local_path) -> str:
    """Put local file or directory contents under structures/<cid>/er/<name>/."""
    if not os.path.exists(local_path):
        raise FileNotFoundError(local_path)
    fs = _s3_fs(config)
    prefix = _er_prefix(structure_id, name)
    base = f"{config['bucket']}/{prefix}"

    if os.path.isfile(local_path):
        dest = f"{base}/{os.path.basename(local_path)}"
        _ensure_parent_dir(fs, dest)
        with open(local_path, 'rb') as src, fs.open_output_stream(dest) as dst:
            dst.write(src.read())
    else:
        for root, _dirs, files in os.walk(local_path):
            for filename in files:
                abs_path = os.path.join(root, filename)
                rel = os.path.relpath(abs_path, local_path).replace(os.sep, '/')
                dest = f"{base}/{rel}"
                _ensure_parent_dir(fs, dest)
                with open(abs_path, 'rb') as src, \
                        fs.open_output_stream(dest) as dst:
                    dst.write(src.read())
    return _er_uri(config, structure_id, name)


def promote_er_pointer(config, structure_id, name) -> dict:
    """Write er/current/<name> JSON pointer to the structure-scoped URI."""
    pointer = {
        'uri': _er_uri(config, structure_id, name),
        'structure_id': structure_id,
        'name': name,
    }
    fs = _s3_fs(config)
    key = f"{config['bucket']}/{_pointer_key(name)}"
    payload = json.dumps(pointer, separators=(',', ':')).encode('utf-8')
    _ensure_parent_dir(fs, key)
    with fs.open_output_stream(key) as out:
        out.write(payload)
    return pointer


def resolve_er_pointer(config, name) -> Optional[dict]:
    """Read er/current/<name> pointer JSON, or None if absent."""
    _validate_er_name(name)
    fs = _s3_fs(config)
    key = f"{config['bucket']}/{_pointer_key(name)}"
    info = fs.get_file_info(key)
    if info.type != pyarrow.fs.FileType.File:
        return None
    with fs.open_input_stream(key) as src:
        return json.loads(src.read().decode('utf-8'))


def list_er_names(config, structure_id) -> list:
    """List ER names under structures/<cid>/er/ that still have objects."""
    _validate_structure_id(structure_id)
    fs = _s3_fs(config)
    base = f"{config['bucket']}/{ER_STRUCTURES_PREFIX}/{structure_id}/er"
    try:
        infos = fs.get_file_info(
            pyarrow.fs.FileSelector(base, recursive=True)
        )
    except (OSError, FileNotFoundError):
        return []
    names = set()
    prefix = base.rstrip('/') + '/'
    for info in infos:
        if info.type != pyarrow.fs.FileType.File:
            continue
        rel = info.path[len(prefix):] if info.path.startswith(prefix) else ''
        name = rel.split('/', 1)[0] if rel else ''
        if name and _SAFE_NAME_RE.match(name):
            names.add(name)
    return sorted(names)


def list_structure_ids(config) -> list:
    """List structure_id prefixes under structures/."""
    fs = _s3_fs(config)
    base = f"{config['bucket']}/{ER_STRUCTURES_PREFIX}"
    try:
        infos = fs.get_file_info(
            pyarrow.fs.FileSelector(base, recursive=False)
        )
    except (OSError, FileNotFoundError):
        return []
    cids = []
    for info in infos:
        name = os.path.basename(info.path.rstrip('/'))
        if name and _SAFE_CID_RE.match(name):
            cids.append(name)
    return sorted(set(cids))


def list_er_current_pointers(config) -> dict:
    """Map ER name -> pointer dict for all er/current/* objects."""
    fs = _s3_fs(config)
    base = f"{config['bucket']}/{ER_CURRENT_PREFIX}"
    try:
        infos = fs.get_file_info(
            pyarrow.fs.FileSelector(base, recursive=False)
        )
    except (OSError, FileNotFoundError):
        return {}
    pointers = {}
    for info in infos:
        if info.type != pyarrow.fs.FileType.File:
            continue
        name = os.path.basename(info.path)
        if not name or not _SAFE_NAME_RE.match(name):
            continue
        with fs.open_input_stream(info.path) as src:
            pointers[name] = json.loads(src.read().decode('utf-8'))
    return pointers


def _delete_prefix(config, key_prefix: str) -> None:
    """Delete all objects (and empty dirs when supported) under key_prefix/."""
    fs = _s3_fs(config)
    base = f"{config['bucket']}/{key_prefix.rstrip('/')}"
    try:
        infos = fs.get_file_info(
            pyarrow.fs.FileSelector(base, recursive=True)
        )
    except (OSError, FileNotFoundError):
        return
    files = []
    dirs = []
    for info in infos:
        if info.type == pyarrow.fs.FileType.File:
            files.append(info.path)
        elif info.type == pyarrow.fs.FileType.Directory:
            dirs.append(info.path)
    for path in files:
        fs.delete_file(path)
    for path in sorted(dirs, key=len, reverse=True):
        try:
            fs.delete_dir(path)
        except (OSError, FileNotFoundError, NotImplementedError):
            pass
    try:
        fs.delete_dir(base)
    except (OSError, FileNotFoundError, NotImplementedError):
        pass


def _delete_pointer(config, name: str) -> None:
    fs = _s3_fs(config)
    key = f"{config['bucket']}/{_pointer_key(name)}"
    info = fs.get_file_info(key)
    if info.type == pyarrow.fs.FileType.File:
        fs.delete_file(key)


def gc_er_prefixes(
    config,
    *,
    delete: bool = False,
    structure_id: Optional[str] = None,
    force: bool = False,
) -> list:
    """Pointer-aware durable GC.

    Roots are ``er/current/*`` pointers. Unreferenced ``structures/<cid>/``
    prefixes are candidates. Targeted ``structure_id`` refuses if still
    referenced unless ``force`` (which also clears those pointers).

    Returns list of structure_id prefixes that would be / were deleted.
    """
    pointers = list_er_current_pointers(config)
    referenced = {
        sid
        for ptr in pointers.values()
        if (sid := _pointer_structure_id(ptr))
    }

    if structure_id is not None:
        _validate_structure_id(structure_id)
        pointing = [
            name for name, ptr in pointers.items()
            if _pointer_structure_id(ptr) == structure_id
        ]
        if pointing and not force:
            raise RuntimeError(
                f'structure_id {structure_id!r} is referenced by '
                f'er/current pointers: {sorted(pointing)}; '
                f'pass force=True to clear pointers and delete'
            )
        candidates = [structure_id]
        if delete:
            if force:
                for name in pointing:
                    _delete_pointer(config, name)
            _delete_prefix(
                config, f'{ER_STRUCTURES_PREFIX}/{structure_id}'
            )
        return candidates

    all_ids = list_structure_ids(config)
    candidates = [sid for sid in all_ids if sid not in referenced]
    if delete:
        for sid in candidates:
            _delete_prefix(config, f'{ER_STRUCTURES_PREFIX}/{sid}')
    return candidates


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
    """Remove Terraform state for object-store compose resources when the
    scratch/durable containers are gone (scottwinkler/shell drift)."""
    if configure_tf_data_dir is not None:
        configure_tf_data_dir(structure_home)

    state = _terraform_state_resources(terraform_bin, structure_home)

    def _rm_if_stale(resource: str, container: str) -> None:
        if resource not in state:
            return
        if _docker_container_running(container):
            return
        print(
            f'Terraform state has "{resource}" but container '
            f'"{container}" is not running on the host; removing stale state '
            f'so apply recreates it'
        )
        proc = _subproc_run(
            f'{terraform_bin} state rm {resource}',
            cwd=structure_home,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f'Failed to remove stale Terraform state for '
                f'"{resource}": {proc.stderr.strip()}'
            )
        if proc.stdout.strip():
            print(proc.stdout.strip())

    _rm_if_stale(_DOCKER_COMPOSE_SCRATCH_RESOURCE, _SCRATCH_OBJ_STORE_CONTAINER)
    _rm_if_stale(_DOCKER_COMPOSE_DURABLE_RESOURCE, _DURABLE_OBJ_STORE_CONTAINER)


def _main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'InfraStructure object-store CLI: scratch jobs under cats-scratch '
            'and durable Entity Relationship under cats-durable '
            '(no CAT Node API).'
        )
    )
    sub = parser.add_subparsers(dest='cmd', required=True)

    sub.add_parser('list-jobs', help='List job UUIDs under the scratch bucket')

    p_files = sub.add_parser('list-files', help='List CSV shards for a job UUID')
    p_files.add_argument('job_uuid')

    p_get = sub.add_parser('get-file', help='Download one CSV shard to stdout')
    p_get.add_argument('job_uuid')
    p_get.add_argument('name')

    p_list_er = sub.add_parser(
        'list-er', help='List ER names under a structure_id namespace'
    )
    p_list_er.add_argument('structure_id')

    p_promote = sub.add_parser(
        'promote-er',
        help='Write er/current/<name> pointer to structures/<cid>/er/<name>',
    )
    p_promote.add_argument('structure_id')
    p_promote.add_argument('name')

    p_resolve = sub.add_parser(
        'resolve-er', help='Read er/current/<name> pointer JSON'
    )
    p_resolve.add_argument('name')

    p_write = sub.add_parser(
        'write-er',
        help='Upload a local file/dir to structures/<cid>/er/<name>/',
    )
    p_write.add_argument('structure_id')
    p_write.add_argument('name')
    p_write.add_argument('local_path')

    p_gc = sub.add_parser(
        'gc-er',
        help=(
            'Pointer-aware durable GC: list or delete structures/<cid>/ '
            'prefixes not referenced by er/current/*'
        ),
    )
    p_gc.add_argument(
        '--delete',
        action='store_true',
        help='Delete candidates (default is dry-run)',
    )
    p_gc.add_argument(
        '--dry-run',
        action='store_true',
        help='List candidates only (default when --delete is absent)',
    )
    p_gc.add_argument(
        '--structure-id',
        dest='structure_id',
        default=None,
        help='Target a single structure_id namespace',
    )
    p_gc.add_argument(
        '--force',
        action='store_true',
        help='With --structure, clear pointing er/current entries and delete',
    )

    args = parser.parse_args(argv)
    scratch = default_scratch_minio_config()
    durable = default_durable_minio_config()

    if args.cmd == 'list-jobs':
        for job_uuid in list_job_uuids(scratch):
            print(f"{job_uuid}\t{minio_result_uri(scratch, job_uuid)}")
        return 0

    if args.cmd == 'list-files':
        for name in list_job_files(scratch, args.job_uuid):
            print(name)
        return 0

    if args.cmd == 'get-file':
        sys.stdout.buffer.write(read_job_file(scratch, args.job_uuid, args.name))
        return 0

    if args.cmd == 'list-er':
        for name in list_er_names(durable, args.structure_id):
            print(f"{name}\t{_er_uri(durable, args.structure_id, name)}")
        return 0

    if args.cmd == 'promote-er':
        pointer = promote_er_pointer(
            durable, args.structure_id, args.name
        )
        print(json.dumps(pointer))
        return 0

    if args.cmd == 'resolve-er':
        pointer = resolve_er_pointer(durable, args.name)
        if pointer is None:
            print(f'no pointer for {args.name!r}', file=sys.stderr)
            return 1
        print(json.dumps(pointer))
        return 0

    if args.cmd == 'write-er':
        uri = write_er_objects(
            durable, args.structure_id, args.name, args.local_path
        )
        print(uri)
        return 0

    if args.cmd == 'gc-er':
        delete = bool(args.delete)
        candidates = gc_er_prefixes(
            durable,
            delete=delete,
            structure_id=args.structure_id,
            force=bool(args.force),
        )
        mode = 'deleted' if delete else 'would-delete'
        for cid in candidates:
            print(f'{mode}\t{ER_STRUCTURES_PREFIX}/{cid}')
        return 0

    return 1


if __name__ == '__main__':
    raise SystemExit(_main())
