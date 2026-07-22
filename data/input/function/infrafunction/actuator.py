"""InfraFunction (FaaS): Plant-agnostic actuator for Process tHOFs.

Receives Process [REPL(aC)] ``integrated_subproc`` and dispatches it onto
Plant via Function-owned ``PlantPort`` (submit_job / wait). Scratch correlator
is InfraStructure ``ObjectStore.begin_job()`` → ``JobHandle``.

No Ray Job Submission or Ray Data imports here — those live in Structure
adapters (``RayPlantPort``, ``RayComputePort``). cloudpickle serializes the
tHOF by value for the remote working_dir (cluster has no repo install).

Ingress / integration_cache / egress are transport callables and are not
dispatched here.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

import cloudpickle

def _write_infrafunction_job_dir(job_dir, input, integrated_subproc, object_store, handle):
    # Named "input", not "data", so it can't collide with the "data"
    # top-level package (e.g. data.input.function.process.callables) some
    # subprocs live in.
    shutil.copytree(input, os.path.join(job_dir, 'input'), dirs_exist_ok=True)

    # By default cloudpickle serializes a plain top-level function by
    # reference (module + qualname). The remote Plant job does not have
    # this repo installed, so register_pickle_by_value forces by-value.
    subproc_module = sys.modules.get(getattr(integrated_subproc, '__module__', None))
    if subproc_module is not None:
        cloudpickle.register_pickle_by_value(subproc_module)
    try:
        with open(os.path.join(job_dir, 'subproc.pkl'), 'wb') as subproc_file:
            cloudpickle.dump(integrated_subproc, subproc_file)
    finally:
        if subproc_module is not None:
            cloudpickle.unregister_pickle_by_value(subproc_module)

    object_store.write_job_scratch(job_dir, handle)


def _resolve_plant_port(plant):
    """Accept PlantPort or PlantContext-like object with plant_port_from_context."""
    if hasattr(plant, 'submit_job') and hasattr(plant, 'wait'):
        return plant
    # Order-submitted plant utils may attach a helper on the context module path
    # via Executor passing an already-built RayPlantPort; fail loud otherwise.
    raise RuntimeError(
        'InfraFunction requires a PlantPort (submit_job / wait). '
        'Pass plant_port_from_context(Plant.context()) from Executor.'
    )


def infrafunction_subproc(
    integrated_subproc, input, output, object_store, plant,
):
    """Dispatch tHOF onto Plant; object_store supplies shared S3 scratch endpoints.

    ``object_store`` must provide begin_job / write_job_scratch /
    download_job_result / result_uri. ``plant`` must implement PlantPort.
    Returns ``(output, JobHandle)`` for BOM object_store_result_uri correlator.
    """
    for attr in ('begin_job', 'write_job_scratch', 'download_job_result'):
        if not hasattr(object_store, attr):
            raise RuntimeError(
                f'ObjectStore.{attr} is required for this InfraFunction'
            )

    plant_port = _resolve_plant_port(plant)
    handle = object_store.begin_job()
    job_dir = tempfile.mkdtemp(prefix='infrafunction_job_')
    try:
        _write_infrafunction_job_dir(
            job_dir, input, integrated_subproc, object_store, handle,
        )
        job_id = plant_port.submit_job(
            entrypoint='python entrypoint.py',
            working_dir=job_dir,
        )
        plant_port.wait(job_id)
        object_store.download_job_result(handle, output)
        return output, handle
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
