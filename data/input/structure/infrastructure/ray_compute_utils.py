"""InfraStructure Ray ComputePort adapter (distributed Ray Data tHOF runner).

Ships inside `infrastructure/` (`infrastructure_cid`). Copied into the
Ray job working_dir beside ``entrypoint.py`` so Process tHOFs can call
``ComputePort.run_transfer`` without importing Ray in Function CID.
"""
from __future__ import annotations


class RayComputePort:
    """Plant-side ComputePort: Ray Data read → map_batches → Dataset."""

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
