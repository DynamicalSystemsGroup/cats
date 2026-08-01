"""Plant Ray ComputePort adapter (distributed Ray Data tHOF runner).

Ships inside `plant/` (`plant_cid`). Copied into the Ray job working_dir
beside ``entrypoint.py`` by ``RayPlantPort.submit_job`` so Process tHOFs
can call ``ComputePort.run_transfer`` without importing Ray in Function CID.

Maps Ray Data batches onto this demo's batch ABI
(``Dict[str, np.ndarray]`` — see docs/INTEROP.md §2g). Another Plant ships
its own ComputePort + entrypoint under its ``plant_cid``.

When ``num_partitions > 1``, reads stable ``part-*`` shard paths and keeps
block count aligned to ``n`` (no shuffle-heavy repartition of a single blob).
"""
from __future__ import annotations

from pathlib import Path


def _part_inputs(input_path: str, num_partitions: int) -> list[str] | None:
    """Return n shard paths if a partition layout is present; else None."""
    root = Path(input_path)
    if not root.is_dir():
        return None
    cars = sorted(root.glob('part-*.car'))
    if len(cars) == num_partitions:
        # Prefer unpacked sidecars (same stem) when present for CSV read.
        resolved: list[str] = []
        for car in cars:
            stem = car.with_suffix('')
            if stem.is_dir() or stem.is_file():
                resolved.append(str(stem))
            else:
                resolved.append(str(car))
        return resolved
    shards = sorted(
        p for p in root.glob('part-*')
        if not p.name.endswith('.car')
    )
    if len(shards) == num_partitions:
        return [str(p) for p in shards]
    return None


def _read_csv_paths(ray, paths: list[str], *, override_num_blocks: int | None = None):
    """Union CSV datasets from shard paths (dirs or files).

    When ``override_num_blocks`` is set (typically ``len(paths)``), each shard
    is read as one block so the union stays at ``n`` without repartition.
    """
    datasets = []
    read_kwargs = {}
    if override_num_blocks is not None and len(paths) == override_num_blocks:
        # One block per shard path.
        read_kwargs['override_num_blocks'] = 1
    for path in paths:
        p = Path(path)
        if p.suffix.lower() == '.car':
            # Cannot read CAR as CSV — fall back to parent tree (caller may
            # still repartition only on the non-part path).
            return ray.data.read_csv(str(p.parent))
        try:
            datasets.append(ray.data.read_csv(str(p), **read_kwargs))
        except TypeError:
            datasets.append(ray.data.read_csv(str(p)))
    if len(datasets) == 1:
        return datasets[0]
    ds = datasets[0]
    for other in datasets[1:]:
        ds = ds.union(other)
    return ds


class RayComputePort:
    """Plant-side ComputePort: Ray Data read → map_batches → Dataset.

    ``batch_fn`` follows the demo ABI (column-dict numpy batches); see
    ``compute_port`` / INTEROP §2g.
    """

    def run_transfer(
        self,
        batch_fn,
        input_path: str,
        *,
        zip_with_range: bool = False,
        num_partitions: int = 1,
    ):
        import ray

        # Job Submission already started a Ray session on this worker; attach.
        ray.init(ignore_reinit_error=True)

        n = int(num_partitions) if num_partitions else 1
        if n < 1:
            n = 1

        part_paths = _part_inputs(input_path, n) if n > 1 else None
        if part_paths is not None:
            # Exactly n shards → n blocks; do not repartition (avoids shuffle).
            ds_in = _read_csv_paths(ray, part_paths, override_num_blocks=n)
        else:
            ds_in = ray.data.read_csv(input_path)

        print(ds_in.schema())
        print()
        ds_out = ds_in.map_batches(batch_fn)
        if zip_with_range:
            ds_out = ds_out.materialize()
            ds_out = ray.data.range(ds_out.count()).zip(ds_out)
        print(ds_out.show(limit=1))
        return ds_out
