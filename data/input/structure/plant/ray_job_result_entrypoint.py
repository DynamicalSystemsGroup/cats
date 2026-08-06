"""Ray job entrypoint: run hotF via ComputePort and write CSV shards to scratch.

Ships in `plant/` (`plant_cid`). Copied into the Ray job working_dir as
``entrypoint.py`` by ``RayPlantPort.submit_job``. Credentials stay in
object_store_scratch_config.json (written by ObjectStore; pod-reachable
scratch MinIO — not the durable Entity Relationship store).

This Plant's landing assumes Ray Dataset + ``write_csv``; another Plant
ships its own entrypoint under its ``plant_cid``. IaaS stays scratch MinIO
config / ``JobHandle`` only.

Wires Plant ``RayComputePort`` into Process ``integrated_subproc`` so
Function stays Plant-agnostic (no ``import ray`` in Process).
"""
import json
import os

import ray.cloudpickle as cloudpickle
from pyarrow.fs import S3FileSystem

from ray_compute_utils import RayComputePort

with open('subproc.pkl', 'rb') as subproc_file:
    subproc = cloudpickle.load(subproc_file)

with open('object_store_scratch_config.json', encoding='utf-8') as config_file:
    scratch_config = json.load(config_file)

object_store_fs = S3FileSystem(
    endpoint_override=scratch_config['endpoint'],
    access_key=scratch_config['access_key'],
    secret_key=scratch_config['secret_key'],
    scheme='http',
)
object_store_output_key = '{}/{}/result'.format(
    scratch_config['bucket'], scratch_config['prefix']
)

# Every node writes its own blocks directly to the shared object store, so
# this stays genuinely distributed regardless of how many nodes
# participate in producing the Dataset that ComputePort returns.
compute = RayComputePort()
try:
    num_partitions = int(os.environ.get('CATS_IO_PARTITIONS', '1') or '1')
except ValueError:
    num_partitions = 1
try:
    ds_out = subproc('input', compute, num_partitions=num_partitions)
except TypeError:
    # Legacy hotF bind without num_partitions.
    ds_out = subproc('input', compute)

if num_partitions > 1:
    # Stable part-* names so egress can CAR-wrap 1:1 (no shuffle rename).
    try:
        shards = ds_out.split(num_partitions, equal=True)
    except TypeError:
        shards = ds_out.split(num_partitions)
    for i, shard in enumerate(shards):
        part_key = '{}/part-{:05d}'.format(object_store_output_key, i)
        shard.write_csv(part_key, filesystem=object_store_fs)
else:
    ds_out.write_csv(object_store_output_key, filesystem=object_store_fs)
