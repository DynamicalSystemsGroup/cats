import json, os, shutil, subprocess, sys, tempfile, time, uuid, ray
from typing import Dict

import numpy as np
import pyarrow.fs
from ray.job_submission import JobStatus, JobSubmissionClient

from cats.network.ipfs_docker import (
    IPFS_GET_TIMEOUT,
    MIGRATION_CONTAINER,
    INTEGRATION_CONTAINER,
    ensure_docker_ipfs_peers,
)

STRUCTURE_HOME = os.path.join(os.path.dirname(__file__), 'structure')


def docker_ipfs_cmd(container, input_dir_cid, output_dir):
    return (
        f"docker exec {container} sh -c '"
        f'ipfs get {input_dir_cid} -o {output_dir} && '
        f'cd {output_dir} && '
        f"rm -f api config datastore_spec gateway repo.lock version && "
        f"ipfs add -r ."
        f"'"
    )


def _run_docker_ipfs(cmd, cwd=None):
    ensure_docker_ipfs_peers()
    return subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd or STRUCTURE_HOME,
        timeout=IPFS_GET_TIMEOUT,
    )


def ipfs_migration(input_dir_cid, container=MIGRATION_CONTAINER):
    unix_ts = int(time.time())
    output_dir = f'/outputs/data_{unix_ts}'
    cmd = docker_ipfs_cmd(container, input_dir_cid, output_dir)
    try:
        result = _run_docker_ipfs(cmd)

        if result.returncode == 0:
            output_lines = result.stdout.splitlines()
            for line in output_lines:
                print(line)
                if line.startswith('added') and line.endswith(f'data_{unix_ts}'):
                    cid = line.split()[1]
                    return cid, f'data_{unix_ts}'
            return "CID not found in the output."
        return f"Command failed with error: {result.stderr}"

    except subprocess.TimeoutExpired:
        return (
            f"Command timed out after {IPFS_GET_TIMEOUT}s fetching CID {input_dir_cid}. "
            "Ensure `ipfs daemon` is running on the host and Docker IPFS nodes are peered."
        )
    except Exception as e:
        return f"An error occurred: {str(e)}"


def ingress(input_dir_cid):
    return ipfs_migration(input_dir_cid=input_dir_cid)


def egress(input_dir_cid):
    result = ipfs_migration(input_dir_cid=input_dir_cid)
    if isinstance(result, tuple):
        return result[0]
    return result


def integration_cache(
    input_dir_cid: str,
    cwd: str,
    container=INTEGRATION_CONTAINER,
):
    print("Integration Cache:")
    exec_cmd = (
        f"docker exec {container} "
        f"sh -c 'ipfs get {input_dir_cid} -o outputs && "
        f"rm -f api config datastore_spec gateway repo.lock version && chmod -R 777 .'"
    )
    print(exec_cmd)
    try:
        result = _run_docker_ipfs(exec_cmd, cwd=cwd)

        if result.returncode == 0:
            output_lines = result.stdout.splitlines()
            for line in output_lines:
                if line.startswith('added') and line.endswith('data'):
                    cid = line.split()[1]
                    return cid
            return "CID not found in the output."
        return f"Command failed with error: {result.stderr}"

    except subprocess.TimeoutExpired:
        return (
            f"Command timed out after {IPFS_GET_TIMEOUT}s fetching CID {input_dir_cid}. "
            "Ensure `ipfs daemon` is running on the host and Docker IPFS nodes are peered."
        )
    except Exception as e:
        return f"An error occurred: {str(e)}"


def function_0(batch: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    vec_a = batch["petal length (cm)"].astype('double')
    vec_b = batch["petal width (cm)"].astype('double')
    batch["petal area (cm^2)"] = vec_a * vec_b
    return batch


def function_1(batch: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    vec_a = batch["petal length (cm)"].astype('double')
    vec_b = batch["petal width (cm)"].astype('double')
    batch["DUPLICATE petal area (cm^2)"] = vec_a * vec_b
    return batch


def _run_ray_batches(input, output, batch_fn, zip_with_range, minio_fs=None, minio_output_key=None):
    """Ray Data work for a single CAT process invocation.

    Dispatched by infrafunction_subproc as its own Ray Job against the
    deployed Plant, so - unlike when this ran locally in the long-lived
    CAT node process - it's already isolated in its own OS process by Ray
    Job Submission; no local `ray.shutdown()`/subprocess wrapper needed
    (and `ray.init()` here connects to that job's cluster rather than
    starting a new one, since one is already running).
    """
    ray.init(ignore_reinit_error=True)
    ds_in = ray.data.read_csv(input)
    print(ds_in.schema())
    print()
    ds_out = ds_in.map_batches(batch_fn)
    if zip_with_range:
        ds_out = ds_out.materialize()
        ds_out = ray.data.range(ds_out.count()).zip(ds_out)
    print(ds_out.show(limit=1))
    if minio_fs is not None:
        # Every node writes its own blocks directly to the shared MinIO
        # bucket, so this stays genuinely distributed regardless of how
        # many nodes participate - unlike the local-gather fallback
        # below, which forces the whole result set through one node.
        ds_out.write_csv(minio_output_key, filesystem=minio_fs)
    else:
        # Fallback for direct/local invocation outside the full
        # infrafunction_subproc dispatch path (e.g. no Plant deployed).
        # ds_out.write_csv(output) would have Ray Data write each output
        # block directly from whichever worker node executes that
        # block's write task - on a multi-node cluster those nodes don't
        # share a filesystem, so a block written on a different node
        # than this one would be invisible here. Gathering to the driver
        # first keeps the write on this process/node.
        os.makedirs(output, exist_ok=True)
        ds_out.to_pandas().to_csv(os.path.join(output, 'part-00000.csv'), index=False)
    return output


def process_0(input, output, minio_fs=None, minio_output_key=None):
    return _run_ray_batches(input, output, function_0, True, minio_fs, minio_output_key)


def process_1(input, output, minio_fs=None, minio_output_key=None):
    return _run_ray_batches(input, output, function_1, False, minio_fs, minio_output_key)


# InfraFunction (FaaS): orchestrates Process (FaaS) onto the Plant (SaaS)
# via the Ray Job Submission API, dispatching `integrated_subproc` as a
# real Ray job against the deployed KubeRay cluster instead of running it
# in an ephemeral, local Ray session.
#
# Runs inside the Ray cluster (the job's working_dir becomes its cwd).
# `ray.init()` inside `integrated_subproc` (e.g. process_0/process_1)
# auto-attaches to this node's already-running Ray session instead of
# starting a new one, so it needs no changes to run remotely.
#
# Uses ray.cloudpickle (bundled with ray, so always present wherever this
# entrypoint runs) rather than stdlib pickle: plain pickle only records a
# module path for a plain function like process_0/process_1, which the
# remote Ray cluster can't resolve since it doesn't have this repo
# installed. cloudpickle instead serializes the function by value.
#
# Builds its own S3FileSystem against MinIO (reachable from inside this
# job's pod via the kind Docker network's gateway IP, not any in-cluster
# Service - see minio_endpoint_pod) and has `integrated_subproc` write
# directly to it, so each of the job's write tasks can run on whichever
# node executes it rather than all needing to land on this node's disk.
_INFRAFUNCTION_ENTRYPOINT_SCRIPT = '''\
import json
import ray.cloudpickle as cloudpickle
from pyarrow.fs import S3FileSystem

with open("subproc.pkl", "rb") as subproc_file:
    subproc = cloudpickle.load(subproc_file)

with open("minio_config.json", encoding="utf-8") as config_file:
    minio_config = json.load(config_file)

minio_fs = S3FileSystem(
    endpoint_override=minio_config["endpoint"],
    access_key=minio_config["access_key"],
    secret_key=minio_config["secret_key"],
    scheme="http",
)
minio_output_key = "{}/{}/result".format(minio_config["bucket"], minio_config["prefix"])

subproc("input", "result", minio_fs=minio_fs, minio_output_key=minio_output_key)
'''


def _write_infrafunction_job_dir(
    job_dir, input, integrated_subproc,
    minio_endpoint_pod, minio_bucket, minio_access_key, minio_secret_key, job_prefix,
):
    # Named "input", not "data", so it can't collide with the "data"
    # top-level package (e.g. data.input.process) some subprocs live in.
    shutil.copytree(input, os.path.join(job_dir, 'input'), dirs_exist_ok=True)

    # By default cloudpickle, like pickle, serializes a plain top-level
    # function (e.g. process_0) by reference (its module + qualname) since
    # it's normally importable - but the remote Ray cluster doesn't have
    # this repo installed, so that reference can't resolve there.
    # register_pickle_by_value forces cloudpickle to instead serialize
    # everything defined in integrated_subproc's module by value.
    subproc_module = sys.modules.get(getattr(integrated_subproc, '__module__', None))
    if subproc_module is not None:
        ray.cloudpickle.register_pickle_by_value(subproc_module)
    try:
        with open(os.path.join(job_dir, 'subproc.pkl'), 'wb') as subproc_file:
            ray.cloudpickle.dump(integrated_subproc, subproc_file)
    finally:
        if subproc_module is not None:
            ray.cloudpickle.unregister_pickle_by_value(subproc_module)

    # Kept in its own file (rather than templated into entrypoint.py's
    # source) so credentials never end up embedded in a script that could
    # be echoed back through job logs.
    with open(os.path.join(job_dir, 'minio_config.json'), 'w', encoding='utf-8') as config_file:
        json.dump({
            'endpoint': minio_endpoint_pod,
            'access_key': minio_access_key,
            'secret_key': minio_secret_key,
            'bucket': minio_bucket,
            'prefix': job_prefix,
        }, config_file)

    with open(os.path.join(job_dir, 'entrypoint.py'), 'w', encoding='utf-8') as entrypoint_file:
        entrypoint_file.write(_INFRAFUNCTION_ENTRYPOINT_SCRIPT)


def _download_infrafunction_job_result(
    minio_endpoint_host, minio_bucket, minio_access_key, minio_secret_key, job_prefix, output,
):
    """Lists and downloads a completed job's result prefix out of MinIO -
    the host-side counterpart to the entrypoint's own S3FileSystem, using
    the host-reachable endpoint since this runs outside any Ray pod."""
    fs = pyarrow.fs.S3FileSystem(
        endpoint_override=minio_endpoint_host,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        scheme='http',
    )
    os.makedirs(output, exist_ok=True)
    result_key = f'{minio_bucket}/{job_prefix}/result'
    for file_info in fs.get_file_info(pyarrow.fs.FileSelector(result_key, recursive=True)):
        if file_info.type != pyarrow.fs.FileType.File:
            continue
        name = os.path.basename(file_info.path)
        with fs.open_input_stream(file_info.path) as src_file, \
                open(os.path.join(output, name), 'wb') as dst_file:
            dst_file.write(src_file.read())


def _connect_job_submission_client(dashboard_address, timeout=60, poll_interval=1):
    """Retries connecting to the Plant's Ray dashboard.

    Right after Structure redeploys the Plant, the dashboard Service/pod
    can report Ready slightly before the Ray head process inside it is
    actually accepting job submission API calls - an immediate
    JobSubmissionClient(...) can fail with "Failed to connect to Ray at
    address" in that narrow window.
    """
    deadline = time.time() + timeout
    while True:
        try:
            return JobSubmissionClient(dashboard_address)
        except Exception:
            if time.time() >= deadline:
                raise
            time.sleep(poll_interval)


def infrafunction_subproc(
    integrated_subproc, input, output, dashboard_address,
    minio_endpoint_pod, minio_endpoint_host, minio_bucket, minio_access_key, minio_secret_key,
):
    job_dir = tempfile.mkdtemp(prefix='infrafunction_job_')
    # Namespaces this job's writes within the shared bucket so concurrent
    # or successive jobs never collide.
    job_prefix = f'jobs/{uuid.uuid4()}'
    try:
        _write_infrafunction_job_dir(
            job_dir, input, integrated_subproc,
            minio_endpoint_pod, minio_bucket, minio_access_key, minio_secret_key, job_prefix,
        )

        client = _connect_job_submission_client(dashboard_address)
        job_id = client.submit_job(
            entrypoint='python entrypoint.py',
            runtime_env={'working_dir': job_dir},
        )

        status = client.get_job_status(job_id)
        while status not in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.STOPPED):
            time.sleep(1)
            status = client.get_job_status(job_id)

        if status != JobStatus.SUCCEEDED:
            logs = client.get_job_logs(job_id)
            raise RuntimeError(f'Ray job {job_id} on Plant dashboard {dashboard_address} ended in {status}:\n{logs}')

        _download_infrafunction_job_result(
            minio_endpoint_host, minio_bucket, minio_access_key, minio_secret_key, job_prefix, output,
        )
        return output
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
