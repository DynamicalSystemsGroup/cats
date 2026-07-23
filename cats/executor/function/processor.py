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


class Processor:
    def __init__(self, infraFunction):
        self.infraFunction = infraFunction
        self.invoice_data_cid = None
        self.object_store_result_uri = None

        self.ingress_input_data_cid = self.infraFunction.enhanced_bom['init_data_cid']
        self.ingress_data_cid = None
        self.integration_data_cid = None
        self.egress_data_cid = None

    def Ingress(self, transport):
        # Lineage CID product; Plant input path comes from integration_cache.
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
        self.infraFunction.service.INTEGRATION_HOME = \
            self.infraFunction.service.contentMesh.INTEGRATION_HOME + "/outputs"
        # Structure staging: process_input is the host path returned by
        # integration_cache (Plant-facing mount).
        process_input = _call_transport_port(
            self.infraFunction.integration_cache_subproc,
            label='integration_cache',
            input_dir_cid=self.ingress_data_cid,
            cwd=self.infraFunction.service.INTEGRATION_INPUT_CACHE,
            data_cache=self.infraFunction.service.INTEGRATION_INPUT_DATA_CACHE,
            transport=transport,
        )
        if not process_input or not isinstance(process_input, str):
            raise RuntimeError(
                "integration_cache must return the host staging path under "
                "INTEGRATION_INPUT_DATA_CACHE for the Plant to read."
            )
        wait_for_directory(process_input, check_interval=1)
        # InfraFunction actuator: dispatches the tHOF from Process [REPL(aC)]
        # (integrated_subproc only) onto the deployed Plant, rather than
        # running it in this (ephemeral executor) process. Plant dispatch
        # surface and object-store come from Plant.context() /
        # InfraStructure.obj_store_context(), not Service fields.
        _output, job_handle = self.infraFunction.infrafunction_subproc(
            self.infraFunction.integrated_subproc,
            process_input,
            self.infraFunction.service.INTEGRATION_HOME,
            object_store=object_store,
            plant=plant,
        )
        self.object_store_result_uri = (
            object_store.result_uri(job_handle) if job_handle else None
        )
        wait_for_directory(self.infraFunction.service.INTEGRATION_HOME, check_interval=1)
        self.integration_data_cid, _ = \
            self.infraFunction.service.contentMesh.cidDir(self.infraFunction.service.INTEGRATION_HOME)
        return self.integration_data_cid

    def Egress(self, transport):
        egress_result = _call_transport_port(
            self.infraFunction.egress_subproc,
            label='egress',
            input_dir_cid=self.integration_data_cid,
            transport=transport,
        )
        if not isinstance(egress_result, str) or not egress_result:
            raise RuntimeError(f"Egress failed: {egress_result}")
        self.infraFunction.service.contentMesh.EGRESS_HOME = \
            self.egress_data_cid = self.invoice_data_cid = egress_result
        return self.egress_data_cid

    def process(self, object_store, plant, transport):
        # Narrow InfraStructure TransportContext to Function TransportPort
        # so Process cannot call ensure_peered / assert_ready.
        transport = as_transport_port(transport)
        print("CAT Executing")
        print("CAT Ingress")
        self.ingress_data_cid = self.Ingress(transport=transport)
        print("CAT Integration")
        self.integration_data_cid = self.Integration(
            object_store=object_store,
            plant=plant,
            transport=transport,
        )
        print("CAT Egress")
        self.egress_data_cid = self.Egress(transport=transport)
        print("...")
        print(self.ingress_data_cid)
        print(self.integration_data_cid)
        print(self.egress_data_cid)
        print("CAT Executed")
        return self.ingress_data_cid, self.integration_data_cid, self.egress_data_cid
