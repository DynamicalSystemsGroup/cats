"""Ray job entrypoint: run tHOF via ComputePort and write CSV shards to scratch.

Ships in `infrastructure/` (`infrastructure_cid`). Copied into the Ray
job working_dir as `entrypoint.py` by ObjectStore.write_job_scratch.
Credentials stay in object_store_config.json (pod-reachable MinIO endpoint).

Wires Structure ``RayComputePort`` into Process ``integrated_subproc`` so
Function stays Plant-agnostic (no ``import ray`` in process.py).
"""
import json

import ray.cloudpickle as cloudpickle
from pyarrow.fs import S3FileSystem

from ray_compute_utils import RayComputePort

with open('subproc.pkl', 'rb') as subproc_file:
    subproc = cloudpickle.load(subproc_file)

with open('object_store_config.json', encoding='utf-8') as config_file:
    object_store_config = json.load(config_file)

object_store_fs = S3FileSystem(
    endpoint_override=object_store_config['endpoint'],
    access_key=object_store_config['access_key'],
    secret_key=object_store_config['secret_key'],
    scheme='http',
)
object_store_output_key = '{}/{}/result'.format(
    object_store_config['bucket'], object_store_config['prefix']
)

# Every node writes its own blocks directly to the shared object store, so
# this stays genuinely distributed regardless of how many nodes
# participate in producing the Dataset that ComputePort returns.
compute = RayComputePort()
ds_out = subproc('input', compute)
ds_out.write_csv(object_store_output_key, filesystem=object_store_fs)
