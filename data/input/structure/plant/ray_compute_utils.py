"""Plant Ray ComputePort adapter (distributed Ray Data tHOF runner).

Ships inside `plant/` (`plant_cid`). Copied into the Ray job working_dir
beside ``entrypoint.py`` by ``RayPlantPort.submit_job`` so Process tHOFs
can call ``ComputePort.run_transfer`` without importing Ray in Function CID.

Maps Ray Data batches onto this demo's batch ABI
(``Dict[str, np.ndarray]`` — see docs/INTEROP.md §2g). Another Plant ships
its own ComputePort + entrypoint under its ``plant_cid``.
"""
from __future__ import annotations


class RayComputePort:
    """Plant-side ComputePort: Ray Data read → map_batches → Dataset.

    ``batch_fn`` follows the demo ABI (column-dict numpy batches); see
    ``compute_port`` / INTEROP §2g.
    """
    def run_transfer(self, batch_fn, input_path: str, *, zip_with_range: bool = False):
        import ray

        # Job Submission already started a Ray session on this worker; attach.
        ray.init(ignore_reinit_error=True)
        ds_in = ray.data.read_csv(input_path)
        print(ds_in.schema())
        print()
        ds_out = ds_in.map_batches(batch_fn)
        if zip_with_range:
            ds_out = ds_out.materialize()
            ds_out = ray.data.range(ds_out.count()).zip(ds_out)
        print(ds_out.show(limit=1))
        return ds_out
