import os, subprocess, time, ray
from typing import Dict

import numpy as np

from cats.network.ipfs_docker import (
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


def _run_ray_batches(input, batch_fn, zip_with_range):
    """Ray Data work for a single CAT process invocation - the transfer
    function itself: read the input, transform it, return the resulting
    Dataset. Purely "physical properties of the system" - no knowledge of
    where the actuator (InfraFunction, see data/input/function/infrafunction.py)
    ultimately delivers this output.

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
