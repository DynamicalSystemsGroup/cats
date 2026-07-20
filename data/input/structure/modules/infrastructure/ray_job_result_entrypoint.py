"""Ray job entrypoint: run tHOF and write CSV shards to object-store scratch.

Ships in `modules/infrastructure` (`infrastructure_cid`). Copied into the Ray
job working_dir as `entrypoint.py` by ObjectStore.write_ray_job_scratch.
Credentials stay in object_store_config.json (pod-reachable MinIO endpoint).
"""
import json

import ray.cloudpickle as cloudpickle
from pyarrow.fs import S3FileSystem

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
# participate in producing the Dataset that `subproc` (Process) returns.
ds_out = subproc('input')
ds_out.write_csv(object_store_output_key, filesystem=object_store_fs)
