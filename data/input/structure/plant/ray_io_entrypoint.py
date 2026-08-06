"""Plant job entrypoint for partitioned CAR ingress / egress.

Ships in ``plant/`` (``plant_cid``). Copied into the Ray job working_dir by
``RayIoPort`` when ``via_job=True``. Reads ``io_args.json``, runs the same
partition helpers as Executor-local ``RayIoPort``, writes ``io_result.json``.

Note: cluster jobs need ContentMesh / gateway credentials in the working_dir
(future); default Executor path uses ``via_job=False`` against host mesh.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ray_io_utils import run_partition_egress, run_partition_ingress


class _MeshFromEnv:
    """Minimal mesh stub: requires CATS_IO_MESH_PICKLE or fails loud."""

    def __init__(self):
        raise RuntimeError(
            'ray_io_entrypoint via_job requires a pre-staged mesh bridge; '
            'use Executor-local RayIoPort (via_job=False) or inject mesh.'
        )


def main() -> None:
    args_path = Path('io_args.json')
    if not args_path.is_file():
        raise FileNotFoundError('io_args.json')
    args = json.loads(args_path.read_text(encoding='utf-8'))
    direction = args['direction']
    input_cid = args['input_cid']
    num_partitions = int(args['num_partitions'])

    mesh_factory = os.environ.get('CATS_IO_MESH_FACTORY')
    if mesh_factory:
        # Optional escape hatch for cluster wiring (import path:callable).
        mod_name, _, attr = mesh_factory.partition(':')
        import importlib

        mesh = getattr(importlib.import_module(mod_name), attr)()
    else:
        mesh = _MeshFromEnv()

    if direction == 'ingress':
        layout_cid, layout_name = run_partition_ingress(
            mesh, input_cid, num_partitions=num_partitions
        )
        payload = {'layout_cid': layout_cid, 'layout_name': layout_name}
    elif direction == 'egress':
        data_cid = run_partition_egress(
            mesh, input_cid, num_partitions=num_partitions
        )
        payload = {'data_cid': data_cid, 'layout_cid': data_cid}
    else:
        raise ValueError(f'unknown I/O direction: {direction!r}')

    Path('io_result.json').write_text(json.dumps(payload), encoding='utf-8')


if __name__ == '__main__':
    main()
