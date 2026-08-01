"""Plant Ray IoPort adapter — partitioned CAR ingress/egress.

Ships inside ``plant/`` (``plant_cid``). Process callables depend only on
Function-owned ``IoPort``; this adapter performs partition layout I/O via
ContentMesh / AddressStore on the Executor (or inside ``ray_io_entrypoint``
when submitted as a Plant job).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

try:
    from partition_layout import (
        collect_input_files,
        list_part_cars,
        list_part_shards,
        part_car_name,
        round_robin_paths,
        split_file_bytes,
        write_shard_tree,
    )
except ImportError:  # repo import when not in job working_dir
    from data.input.structure.plant.partition_layout import (
        collect_input_files,
        list_part_cars,
        list_part_shards,
        part_car_name,
        round_robin_paths,
        split_file_bytes,
        write_shard_tree,
    )


def run_partition_ingress(mesh, input_dir_cid: str, *, num_partitions: int) -> tuple[str, str]:
    """Fetch ``input_dir_cid``, split into ``n`` CAR parts, return layout cidDir."""
    if num_partitions < 2:
        raise ValueError('partition_ingress requires num_partitions >= 2')

    with tempfile.TemporaryDirectory(prefix='cats-io-ingress-') as tmp:
        tmp_path = Path(tmp)
        fetch_root = tmp_path / 'input'
        fetch_root.mkdir()
        # Materialize CID at fetch_root (file or directory).
        mesh.get(cid=input_dir_cid, filepath='input', output=str(tmp_path))
        source = fetch_root
        if not source.exists():
            # get may write to output/filepath as file without trailing dir
            alt = tmp_path / 'input'
            source = alt

        layout_dir = tmp_path / 'layout'
        layout_dir.mkdir()
        files = collect_input_files(source)

        if len(files) == 1 and files[0].is_file() and (
            source.is_file() or files[0].parent == source or source.is_dir()
        ):
            # Single-file input → equal byte shards.
            data = files[0].read_bytes()
            shards = split_file_bytes(data, num_partitions)
            for i, shard in enumerate(shards):
                shard_path = tmp_path / f'shard-{i:05d}.bin'
                shard_path.write_bytes(shard)
                _write_part_car(mesh, shard_path, layout_dir / part_car_name(i))
        else:
            bags = round_robin_paths(files, num_partitions)
            root_for_rel = source if source.is_dir() else source.parent
            for i, bag in enumerate(bags):
                bag_dir = tmp_path / f'bag-{i:05d}'
                write_shard_tree(bag, bag_dir, source_root=root_for_rel)
                _write_part_car(mesh, bag_dir, layout_dir / part_car_name(i))

        result = mesh.cidDir(str(layout_dir))
        if isinstance(result, tuple):
            layout_cid, layout_name = result
        else:
            layout_cid, layout_name = result, layout_dir.name
        return layout_cid, layout_name


def run_partition_egress(mesh, input_dir_cid: str, *, num_partitions: int) -> str:
    """Materialize partition layout and publish partition-dir CID for Invoice.

    Prefer an existing ``part-*.car`` layout. Else CAR-wrap ``part-*`` CSV/dir
    shards 1:1. Else ``cidDir`` the whole tree (single root).
    """
    if num_partitions < 2:
        raise ValueError('partition_egress requires num_partitions >= 2')

    with tempfile.TemporaryDirectory(prefix='cats-io-egress-') as tmp:
        tmp_path = Path(tmp)
        mesh.get(cid=input_dir_cid, filepath='input', output=str(tmp_path))
        source = tmp_path / 'input'
        if source.is_dir():
            cars = list_part_cars(source)
            if len(cars) == num_partitions:
                result = mesh.cidDir(str(source))
            else:
                shards = list_part_shards(source)
                if len(shards) == num_partitions:
                    layout_dir = tmp_path / 'layout'
                    layout_dir.mkdir()
                    for i, shard in enumerate(shards):
                        _write_part_car(
                            mesh, shard, layout_dir / part_car_name(i)
                        )
                    result = mesh.cidDir(str(layout_dir))
                else:
                    result = mesh.cidDir(str(source))
        else:
            result = mesh.cidDir(str(source.parent if source.is_file() else tmp_path))
        if isinstance(result, tuple):
            return result[0]
        return result


def _write_part_car(mesh, content_path: Path, dest_car: Path) -> None:
    """Add ``content_path`` to the mesh, export CAR bytes to ``dest_car``."""
    dest_car.parent.mkdir(parents=True, exist_ok=True)
    if content_path.is_dir():
        added = mesh.ipfsClient.add(str(content_path), recursive=True)
        if isinstance(added, list):
            name = content_path.name
            entry = [x for x in added if x.get('Name') == name]
            if not entry:
                entry = [added[-1]]
            cid = entry[0]['Hash']
        else:
            cid = added['Hash']
    else:
        cid = mesh.ipfsClient.add_bytes(
            content_path.read_bytes(), filename=content_path.name
        )
    # Prefer AddressStore / ContentMesh getCar when present.
    get_car = getattr(mesh, 'getCar', None)
    if get_car is not None:
        get_car(cid, str(dest_car))
        return
    dag_export = getattr(getattr(mesh, 'addressStore', None), 'dag_export', None)
    if dag_export is not None:
        dag_export(cid, str(dest_car))
        return
    ipfs_export = getattr(mesh.ipfsClient, 'dag_export', None)
    if ipfs_export is not None:
        ipfs_export(cid, str(dest_car))
        return
    raise RuntimeError('mesh cannot dag_export / getCar for partition CAR')


class RayIoPort:
    """IoPort adapter: partitioned CAR layout via ContentMesh (+ optional Plant job)."""

    def __init__(
        self,
        mesh,
        plant_port=None,
        *,
        via_job: bool = False,
        work_root: str | None = None,
    ):
        self.mesh = mesh
        self.plant_port = plant_port
        self.via_job = bool(via_job)
        self.work_root = work_root

    def partition_ingress(
        self, input_dir_cid: str, *, num_partitions: int
    ) -> tuple[str, str]:
        if self.via_job and self.plant_port is not None:
            return self._run_job(
                'ingress', input_dir_cid, num_partitions=num_partitions
            )
        return run_partition_ingress(
            self.mesh, input_dir_cid, num_partitions=num_partitions
        )

    def partition_egress(self, input_dir_cid: str, *, num_partitions: int) -> str:
        if self.via_job and self.plant_port is not None:
            layout_cid, _ = self._run_job(
                'egress', input_dir_cid, num_partitions=num_partitions
            )
            return layout_cid
        return run_partition_egress(
            self.mesh, input_dir_cid, num_partitions=num_partitions
        )

    def _run_job(
        self, direction: str, input_dir_cid: str, *, num_partitions: int
    ) -> tuple[str, str]:
        """Submit ``ray_io_entrypoint`` and read ``io_result.json``."""
        work = self.work_root or tempfile.mkdtemp(prefix='cats-ray-io-job-')
        Path(work).mkdir(parents=True, exist_ok=True)
        args = {
            'direction': direction,
            'input_cid': input_dir_cid,
            'num_partitions': num_partitions,
        }
        args_path = Path(work) / 'io_args.json'
        args_path.write_text(json.dumps(args), encoding='utf-8')
        write_job_io_entrypoint(work)
        write_job_io_utils(work)
        job_id = self.plant_port.submit_job(
            entrypoint='python ray_io_entrypoint.py',
            working_dir=work,
        )
        self.plant_port.wait(job_id)
        result_path = Path(work) / 'io_result.json'
        if not result_path.is_file():
            raise RuntimeError(
                f'Ray I/O job {job_id} did not write io_result.json'
            )
        payload = json.loads(result_path.read_text(encoding='utf-8'))
        layout_cid = payload.get('layout_cid') or payload.get('data_cid')
        layout_name = payload.get('layout_name') or 'layout'
        if not layout_cid:
            raise RuntimeError(f'Ray I/O job result missing CID: {payload!r}')
        return layout_cid, layout_name


IO_ENTRYPOINT_FILENAME = 'ray_io_entrypoint.py'
IO_UTILS_FILENAME = 'ray_io_utils.py'
PARTITION_LAYOUT_FILENAME = 'partition_layout.py'


def write_job_io_entrypoint(job_dir: str) -> None:
    source = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), IO_ENTRYPOINT_FILENAME
    )
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    shutil.copyfile(source, os.path.join(job_dir, IO_ENTRYPOINT_FILENAME))


def write_job_io_utils(job_dir: str) -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    for name in (IO_UTILS_FILENAME, PARTITION_LAYOUT_FILENAME):
        source = os.path.join(here, name)
        if not os.path.isfile(source):
            raise FileNotFoundError(source)
        shutil.copyfile(source, os.path.join(job_dir, name))


def io_port_from_context(plant, mesh, *, via_job: bool = False) -> RayIoPort:
    """Build RayIoPort from Plant handle + ContentMesh.

    ``via_job=True`` submits ``ray_io_entrypoint`` on PlantPort; default runs
    partition ops on the Executor against ``mesh`` (Plant-owned code path).
    """
    plant_port = None
    if hasattr(plant, 'submit_job') and hasattr(plant, 'wait'):
        plant_port = plant
    elif hasattr(plant, 'job_endpoint') and plant.job_endpoint:
        # Lazy: caller may pass PlantContext; resolve RayPlantPort if needed.
        try:
            from plant_utils import plant_port_from_context

            plant_port = plant_port_from_context(plant)
        except Exception:
            plant_port = None
    return RayIoPort(mesh, plant_port=plant_port, via_job=via_job)
