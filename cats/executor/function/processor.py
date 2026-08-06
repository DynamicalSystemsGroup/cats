import importlib.util
import os
import sys

from cats.utils import wait_for_directory
from data.input.function.process.transport_port import as_transport_port

_TRANSPORT_PORT_HINT = (
    'Process transport callables must accept a `transport` argument '
    '(TransportPort: migrate / stage_for_plant). Recreate the Order with '
    'ingress/egress/integration_cache from data.input.function.process.'
)


def _call_transport_port(subproc, *, label, **kwargs):
    """Invoke a Process transport callable; clarify missing-transport TypeErrors."""
    try:
        return subproc(**kwargs)
    except TypeError as exc:
        msg = str(exc)
        if 'transport' in msg or 'unexpected keyword' in msg or 'required' in msg:
            raise TypeError(f'{label}: {_TRANSPORT_PORT_HINT} ({exc})') from exc
        raise


def _io_partitions() -> int:
    raw = os.environ.get('CATS_IO_PARTITIONS', '1').strip() or '1'
    try:
        n = int(raw)
    except ValueError as exc:
        raise ValueError(
            f'CATS_IO_PARTITIONS must be an int, got {raw!r}'
        ) from exc
    if n < 1:
        raise ValueError(f'CATS_IO_PARTITIONS must be >= 1, got {n}')
    return n


class Processor:
    def __init__(self, infraFunction):
        self.infraFunction = infraFunction
        self.invoice_data_cid = None
        self.object_store_result_uri = None
        # Durable Entity Relationship correlators (set when promote path is used).
        self.durable_er_uri = None
        self.durable_er_pointer = None

        self.ingress_input_data_cid = self.infraFunction.enhanced_bom['init_data_cid']
        self.ingress_data_cid = None
        self.integration_data_cid = None
        self.egress_data_cid = None
        self.num_partitions = _io_partitions()

    def _load_plant_utils(self):
        path = os.path.join(
            self.infraFunction.runtime.INPUT_STRUCTURE_HOME,
            'plant',
            'plant_utils.py',
        )
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        spec = importlib.util.spec_from_file_location(
            'processor_plant_utils', path
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        plant_dir = os.path.dirname(path)
        if plant_dir not in sys.path:
            sys.path.insert(0, plant_dir)
        spec.loader.exec_module(module)
        return module

    def _io_port(self, plant):
        """Plant-backed IoPort when num_partitions > 1; else None."""
        if self.num_partitions <= 1:
            return None
        utils = self._load_plant_utils()
        via_job = os.environ.get('CATS_IO_VIA_JOB', '').strip().lower() in (
            '1',
            'true',
            'yes',
            'on',
        )
        return utils.io_port_from_context(
            plant,
            self.infraFunction.runtime.contentMesh,
            via_job=via_job,
        )

    def Ingress(self, transport, *, io=None):
        # Lineage CID product; Plant input path comes from integration_cache.
        try:
            ingress_result = _call_transport_port(
                self.infraFunction.ingress_subproc,
                label='ingress',
                input_dir_cid=self.ingress_input_data_cid,
                transport=transport,
                io=io,
                num_partitions=self.num_partitions,
            )
        except TypeError:
            if self.num_partitions > 1:
                raise
            # Legacy bind without io / num_partitions kwargs.
            ingress_result = _call_transport_port(
                self.infraFunction.ingress_subproc,
                label='ingress',
                input_dir_cid=self.ingress_input_data_cid,
                transport=transport,
            )
        if not isinstance(ingress_result, tuple):
            # Older pickled ingress may still return an error string.
            raise RuntimeError(f"Ingress failed: {ingress_result}")
        self.ingress_data_cid, _ingress_data_dir = ingress_result
        return self.ingress_data_cid

    def Integration(self, object_store, plant, transport):
        self.infraFunction.runtime.INTEGRATION_HOME = \
            self.infraFunction.runtime.contentMesh.INTEGRATION_HOME + "/outputs"
        # Structure staging: process_input is the host path returned by
        # integration_cache (Plant-facing mount).
        process_input = _call_transport_port(
            self.infraFunction.integration_cache_subproc,
            label='integration_cache',
            input_dir_cid=self.ingress_data_cid,
            cwd=self.infraFunction.runtime.INTEGRATION_INPUT_CACHE,
            data_cache=self.infraFunction.runtime.INTEGRATION_INPUT_DATA_CACHE,
            transport=transport,
        )
        if not process_input or not isinstance(process_input, str):
            raise RuntimeError(
                "integration_cache must return the host staging path under "
                "INTEGRATION_INPUT_DATA_CACHE for the Plant to read."
            )
        wait_for_directory(process_input, check_interval=1)
        # InfraFunction [Actuator]: dispatches the hotF from Process
        # [Composed Function] (integrated_subproc only) onto the deployed
        # Plant, rather than running it in this (ephemeral executor) process.
        # Plant dispatch surface and object-store come from Plant.context() /
        # InfraStructure.obj_store_context(), not Runtime fields.
        # Propagate partition count for RayComputePort alignment.
        os.environ['CATS_IO_PARTITIONS'] = str(self.num_partitions)
        _output, job_handle = self.infraFunction.infrafunction_subproc(
            self.infraFunction.integrated_subproc,
            process_input,
            self.infraFunction.runtime.INTEGRATION_HOME,
            object_store=object_store,
            plant=plant,
        )
        self.object_store_result_uri = (
            object_store.result_uri(job_handle) if job_handle else None
        )
        wait_for_directory(self.infraFunction.runtime.INTEGRATION_HOME, check_interval=1)
        self.integration_data_cid, _ = \
            self.infraFunction.runtime.contentMesh.cidDir(self.infraFunction.runtime.INTEGRATION_HOME)
        return self.integration_data_cid

    def Egress(self, transport, *, io=None):
        try:
            egress_result = _call_transport_port(
                self.infraFunction.egress_subproc,
                label='egress',
                input_dir_cid=self.integration_data_cid,
                transport=transport,
                io=io,
                num_partitions=self.num_partitions,
            )
        except TypeError:
            if self.num_partitions > 1:
                raise
            egress_result = _call_transport_port(
                self.infraFunction.egress_subproc,
                label='egress',
                input_dir_cid=self.integration_data_cid,
                transport=transport,
            )
        if not isinstance(egress_result, str) or not egress_result:
            raise RuntimeError(f"Egress failed: {egress_result}")
        self.infraFunction.runtime.contentMesh.EGRESS_HOME = \
            self.egress_data_cid = self.invoice_data_cid = egress_result
        return self.egress_data_cid

    def process(self, object_store, plant, transport):
        # Narrow InfraStructure TransportContext to Function TransportPort
        # so Process cannot call ensure_peered / assert_ready.
        transport = as_transport_port(transport)
        io = self._io_port(plant)
        print("CAT Executing")
        print("CAT Ingress")
        self.ingress_data_cid = self.Ingress(transport=transport, io=io)
        print("CAT Integration")
        self.integration_data_cid = self.Integration(
            object_store=object_store,
            plant=plant,
            transport=transport,
        )
        print("CAT Egress")
        self.egress_data_cid = self.Egress(transport=transport, io=io)
        print("...")
        print(self.ingress_data_cid)
        print(self.integration_data_cid)
        print(self.egress_data_cid)
        print("CAT Executed")
        return self.ingress_data_cid, self.integration_data_cid, self.egress_data_cid
