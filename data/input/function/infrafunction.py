import json, os, shutil, sys, tempfile, time, uuid, ray
import pyarrow.fs
from ray.job_submission import JobStatus, JobSubmissionClient


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
# `integrated_subproc` (Process [FaaS]) is a pure transfer function - it
# just returns the transformed Dataset. Delivering that Dataset into the
# shared MinIO bucket is this actuator's own responsibility, kept here
# rather than in Process, so each of the job's write tasks can run on
# whichever node executes it rather than all needing to land on this
# node's disk. Builds its own S3FileSystem against MinIO (reachable from
# inside this job's pod via the kind Docker network's gateway IP, not any
# in-cluster Service - see minio_endpoint_pod).
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

# Every node writes its own blocks directly to the shared MinIO bucket, so
# this stays genuinely distributed regardless of how many nodes
# participate in producing the Dataset that `subproc` (Process) returns.
ds_out = subproc("input")
ds_out.write_csv(minio_output_key, filesystem=minio_fs)
'''


def _write_infrafunction_job_dir(
    job_dir, input, integrated_subproc,
    minio_endpoint_pod, minio_bucket, minio_access_key, minio_secret_key, job_prefix,
):
    # Named "input", not "data", so it can't collide with the "data"
    # top-level package (e.g. data.input.function.process) some subprocs
    # live in.
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
