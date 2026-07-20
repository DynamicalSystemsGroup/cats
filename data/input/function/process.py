# Process [REPL(aC)] callables a Read-Eval-Print Loop as Code (e.g. cats_demo.py
# Marimo notebook) composes and submits:
#   - ingress / integration_cache / egress — transport (IPFS/Docker), not transfer
#     functions
#   - process_0 / process_1 (Order slot: integrated_subproc) — the Transfer
#     Higher-Order Function (tHOF): input→output data transform
#     (https://en.wikipedia.org/wiki/Transfer_function), higher-order because it
#     applies a batch function (e.g. via Ray map_batches)
# InfraFunction [FaaS] dispatches only the tHOF onto Plant [SaaS]; transport runs
# locally around that dispatch.

import os, subprocess, time, ray
from typing import Dict

import numpy as np

from cats.network.docker_ipfs_transport_peering import (
    IPFS_GET_TIMEOUT,
    MIGRATION_CONTAINER,
    INTEGRATION_CONTAINER,
    ensure_docker_ipfs_peers,
)

# One level up from data/input/function/ - this module lives inside
# data/input/function/, not data/input/ itself, so STRUCTURE_HOME has to
# walk up past that extra directory to reach the sibling data/input/structure.
STRUCTURE_HOME = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'structure')


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
    """Shared Docker IPFS get→re-add used by ingress and egress transport.

    Returns (cid, data_dir_name). Raises RuntimeError on failure.
    """
    unix_ts = int(time.time())
    output_dir = f'/outputs/data_{unix_ts}'
    cmd = docker_ipfs_cmd(container, input_dir_cid, output_dir)
    try:
        result = _run_docker_ipfs(cmd)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"Command timed out after {IPFS_GET_TIMEOUT}s fetching CID {input_dir_cid}. "
            "Ensure `ipfs daemon` is running on the host and Docker IPFS nodes are peered."
        ) from e

    if result.returncode != 0:
        raise RuntimeError(f"Command failed with error: {result.stderr}")

    for line in result.stdout.splitlines():
        print(line)
        if line.startswith('added') and line.endswith(f'data_{unix_ts}'):
            cid = line.split()[1]
            return cid, f'data_{unix_ts}'
    raise RuntimeError("CID not found in the output.")


def ingress(input_dir_cid):
    """Transport: migrate invoice data CID onto the shared cache mount."""
    return ipfs_migration(input_dir_cid=input_dir_cid)


def egress(input_dir_cid):
    """Transport: migrate integration output CID; return CID only for Invoice."""
    cid, _ = ipfs_migration(input_dir_cid=input_dir_cid)
    return cid


def integration_cache(
    input_dir_cid: str,
    cwd: str,
    container=INTEGRATION_CONTAINER,
    data_cache=None,
):
    """Stage ingress CID onto the Plant-facing integration cache mount.

    `cwd` is INTEGRATION_INPUT_CACHE; the Docker volume bind is
    INTEGRATION_INPUT_DATA_CACHE → /outputs. Stages into
    /outputs/staged_<ts> and returns that directory's host path for Ray.
    Raises RuntimeError on failure.
    """
    if data_cache is None:
        data_cache = os.path.join(cwd, 'outputs')
    unix_ts = int(time.time())
    stage_name = f'staged_{unix_ts}'
    container_out = f'/outputs/{stage_name}'
    host_path = os.path.join(data_cache, stage_name)
    print("Integration Cache:")
    exec_cmd = (
        f"docker exec {container} "
        f"sh -c 'ipfs get {input_dir_cid} -o {container_out} && "
        f"cd {container_out} && "
        f"rm -f api config datastore_spec gateway repo.lock version && "
        f"chmod -R 777 .'"
    )
    print(exec_cmd)
    try:
        result = _run_docker_ipfs(exec_cmd, cwd=cwd)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"Command timed out after {IPFS_GET_TIMEOUT}s fetching CID {input_dir_cid}. "
            "Ensure `ipfs daemon` is running on the host and Docker IPFS nodes are peered."
        ) from e

    if result.returncode != 0:
        raise RuntimeError(f"Command failed with error: {result.stderr}")
    if not os.path.isdir(host_path):
        raise RuntimeError(
            f"Integration cache staging succeeded in container but host path "
            f"missing: {host_path}"
        )
    return host_path


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


def _run_ray_batches(input, batch_fn, zip_with_range):
    """The Transfer Higher-Order Function (tHOF) body for a CAT process - 
    Ray Data work for a single CAT process invocation - 
    
    Read input, apply batch_fn (higher-order), return the resulting Dataset —
    the input→output transfer function of the system, with no knowledge of
    where the actuator (InfraFunction, see infrafunction.py) delivers output.

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
    return ds_out


def process_0(input):
    return _run_ray_batches(input, function_0, True)


def process_1(input):
    return _run_ray_batches(input, function_1, False)
