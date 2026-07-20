import os, shutil, sys, tempfile, time, uuid, ray
from ray.job_submission import JobStatus, JobSubmissionClient


# InfraFunction (FaaS): actuator that receives the Transfer Higher-Order Function
# (tHOF) — Process [REPL(aC)]'s `integrated_subproc` — and dispatches it onto
# the Plant (SaaS) via the Ray Job Submission API as a real Ray job against the
# deployed KubeRay cluster instead of running it in an ephemeral, local Ray
# session. Ingress / integration_cache / egress are transport callables and are
# not dispatched here.
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
# `integrated_subproc` is the pure transfer function / tHOF - it returns the
# transformed Dataset only. Delivering that Dataset into the shared object
# store is InfraStructure / ObjectStore responsibility
# (`ObjectStore.write_ray_job_scratch` / `download_job_result` in
# `modules/infrastructure/obj_store_utils.py`), not Process and not
# embedded S3 mechanics here — so each write task can run on whichever
# Plant node executes it.


def _write_infrafunction_job_dir(job_dir, input, integrated_subproc, object_store, job_prefix):
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

    object_store.write_ray_job_scratch(job_dir, job_prefix)


def _connect_job_submission_client(job_endpoint, timeout=60, poll_interval=1):
    """Retries connecting to the Plant's job submission endpoint.

    Right after Structure redeploys the Plant, the control-plane Service/pod
    can report Ready slightly before the Ray head process inside it is
    actually accepting job submission API calls - an immediate
    JobSubmissionClient(...) can fail with "Failed to connect to Ray at
    address" in that narrow window.
    """
    deadline = time.time() + timeout
    while True:
        try:
            return JobSubmissionClient(job_endpoint)
        except Exception:
            if time.time() >= deadline:
                raise
            time.sleep(poll_interval)


def infrafunction_subproc(
    integrated_subproc, input, output, object_store, plant,
):
    """Dispatch tHOF onto Plant; object_store supplies shared S3 scratch endpoints.

    `object_store` is an ObjectStore (or duck-type) with write_ray_job_scratch /
    download_job_result — from InfraStructure.obj_store_context(). `plant` is a
    PlantContext (or duck-type) with job_endpoint — from Plant.context(). Must
    not read Service.
    """
    job_endpoint = getattr(plant, 'job_endpoint', None)
    if not job_endpoint:
        raise RuntimeError(
            'PlantContext.job_endpoint is required for this InfraFunction'
        )
    if not hasattr(object_store, 'write_ray_job_scratch') or not hasattr(
        object_store, 'download_job_result'
    ):
        raise RuntimeError(
            'ObjectStore.write_ray_job_scratch and download_job_result are '
            'required for this InfraFunction'
        )

    job_dir = tempfile.mkdtemp(prefix='infrafunction_job_')
    # Namespaces this job's writes within the shared bucket so concurrent
    # or successive jobs never collide.
    job_prefix = f'jobs/{uuid.uuid4()}'
    try:
        _write_infrafunction_job_dir(
            job_dir, input, integrated_subproc, object_store, job_prefix,
        )

        client = _connect_job_submission_client(job_endpoint)
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
            raise RuntimeError(
                f'Ray job {job_id} on Plant job_endpoint {job_endpoint} '
                f'ended in {status}:\n{logs}'
            )

        object_store.download_job_result(job_prefix, output)
        # job_prefix correlates this run's MinIO scratch objects
        # (cats-scratch/jobs/<uuid>/result) with the BOM log's
        # object_store_result_uri; durable retrieval remains integration_data_cid.
        return output, job_prefix
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
