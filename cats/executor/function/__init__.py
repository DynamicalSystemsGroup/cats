import json, os, pickle
from cats.utils import wait_for_directory


class Processor:
    def __init__(self, infraFunction):
        self.infraFunction = infraFunction
        self.invoice_data_cid = None
        self.object_store_result_uri = None

        self.ingress_input_data_cid = self.infraFunction.enhanced_bom['init_data_cid']
        self.ingress_data_cid = None
        self.integration_data_cid = None
        self.egress_data_cid = None

    def Ingress(self):
        # Lineage CID product; Plant input path comes from integration_cache.
        ingress_result = self.infraFunction.ingress_subproc(
            input_dir_cid=self.ingress_input_data_cid
        )
        if not isinstance(ingress_result, tuple):
            # Older pickled ingress may still return an error string.
            raise RuntimeError(f"Ingress failed: {ingress_result}")
        self.ingress_data_cid, _ingress_data_dir = ingress_result

        self.infraFunction.service.INGRESS_DATA_HOME = self.ingress_data_cid
        self.infraFunction.service.INGRESS_JOB_STATUS = "Completed"
        self.infraFunction.service.INGRESS_EXIT_CODE = "0"
        return self.ingress_data_cid

    def Integration(self, object_store, plant):
        self.infraFunction.service.INTEGRATION_HOME = \
            self.infraFunction.service.meshClient.INTEGRATION_HOME + "/outputs"
        # Structure staging: process_input is the host path returned by
        # integration_cache (Plant-facing mount), not Ingress's former
        # INGRESS_DATA_PATH side channel.
        process_input = self.infraFunction.integration_cache_subproc(
            input_dir_cid=self.infraFunction.service.INGRESS_DATA_HOME,
            cwd=self.infraFunction.service.INTEGRATION_INPUT_CACHE,
            data_cache=self.infraFunction.service.INTEGRATION_INPUT_DATA_CACHE,
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
        _output, job_prefix = self.infraFunction.infrafunction_subproc(
            self.infraFunction.integrated_subproc,
            process_input,
            self.infraFunction.service.INTEGRATION_HOME,
            object_store=object_store,
            plant=plant,
        )
        self.object_store_result_uri = (
            object_store.result_uri(job_prefix) if job_prefix else None
        )
        wait_for_directory(self.infraFunction.service.INTEGRATION_HOME, check_interval=1)
        self.integration_data_cid, _ = \
            self.infraFunction.service.meshClient.cidDir(self.infraFunction.service.INTEGRATION_HOME)
        return self.integration_data_cid

    def Egress(self):
        egress_result = self.infraFunction.egress_subproc(
            input_dir_cid=self.integration_data_cid
        )
        if not isinstance(egress_result, str) or not egress_result:
            raise RuntimeError(f"Egress failed: {egress_result}")
        self.infraFunction.service.meshClient.EGRESS_HOME = \
            self.egress_data_cid = self.invoice_data_cid = egress_result
        self.infraFunction.service.EGRESS_JOB_STATUS = "Completed"
        self.infraFunction.service.EGRESS_EXIT_CODE = "0"
        return self.egress_data_cid

    def process(self, object_store, plant):
        print("CAT Executing")
        print("CAT Ingress")
        self.ingress_data_cid = self.Ingress()
        print("CAT Integration")
        self.integration_data_cid = self.Integration(
            object_store=object_store,
            plant=plant,
        )
        print("CAT Egress")
        self.egress_data_cid = self.Egress()
        print("...")
        print(self.ingress_data_cid)
        print(self.integration_data_cid)
        print(self.egress_data_cid)
        print("CAT Executed")
        return self.ingress_data_cid, self.integration_data_cid, self.egress_data_cid


class InfraFunction:
    def __init__(self, service, function_cid):
        self.service = service
        self.enhanced_bom = self.service.enhanced_bom
        self.function_cid = function_cid
        self.function = json.loads(self.service.meshClient.cat(self.function_cid))

        # Process [REPL(aC)]: transport callables (ingress, integration_cache,
        # egress) plus the tHOF (integrated_subproc) a REPL as Code composes
        # and submits. Process is the composer, not itself a tHOF.
        self.process_cid = self.function['process_cid']
        self.process = json.loads(self.service.meshClient.cat(self.process_cid))
        self.ingress_subproc_cid = self.process['ingress_subproc_cid']
        self.integrated_subproc_cid = self.process['integrated_subproc_cid']
        self.egress_subproc_cid = self.process['egress_subproc_cid']
        self.integration_cache_subproc_cid = self.process['integration_cache_subproc_cid']

        # InfraFunction (FaaS): actuator that dispatches the tHOF
        # (integrated_subproc) onto the Plant (SaaS) - see Integration().
        self.infrafunction_cid = self.function['infrafunction_cid']
        self.infrafunction = json.loads(self.service.meshClient.cat(self.infrafunction_cid))
        self.infrafunction_subproc_cid = self.infrafunction['infrafunction_subproc_cid']

        self.ingress_subproc = pickle.loads(self.service.meshClient.catObj(self.ingress_subproc_cid))
        self.integrated_subproc = pickle.loads(self.service.meshClient.catObj(self.integrated_subproc_cid))
        self.egress_subproc = pickle.loads(self.service.meshClient.catObj(self.egress_subproc_cid))
        self.integration_cache_subproc = pickle.loads(
            self.service.meshClient.catObj(self.integration_cache_subproc_cid)
        )
        self.infrafunction_subproc = pickle.loads(
            self.service.meshClient.catObj(self.infrafunction_subproc_cid)
        )

    def compose(self):
        return Processor(self)
