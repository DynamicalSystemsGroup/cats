import json, os, pickle
from cats.utils import wait_for_directory


class Processor:
    def __init__(self, infraFunction):
        self.infraFunction = infraFunction
        self.invoice_data_cid = None

        self.ingress_input_data_cid = self.infraFunction.enhanced_bom['init_data_cid']
        self.ingress_data_cid = None
        self.integration_data_cid = None
        self.egress_data_cid = None

    def Ingress(self):
        ingress_result = self.infraFunction.ingress_subproc(
            input_dir_cid=self.ingress_input_data_cid
        )
        if not isinstance(ingress_result, tuple):
            # ingress_subproc failed and returned its error message as a
            # plain string instead of the expected (cid, data_dir) tuple.
            # Raise it here, with the real reason, rather than leaving
            # INGRESS_DATA_PATH unset for Integration() to fail on later
            # with a generic "unset" error that hides the actual cause.
            raise RuntimeError(f"Ingress failed: {ingress_result}")
        self.ingress_data_cid, ingress_data_dir = ingress_result

        self.infraFunction.service.INGRESS_DATA_HOME = self.ingress_data_cid
        self.infraFunction.service.INGRESS_DATA_PATH = os.path.join(
            self.infraFunction.service.INTEGRATION_INPUT_DATA_CACHE,
            ingress_data_dir,
        )

        self.infraFunction.service.INGRESS_JOB_STATUS = "Completed"
        self.infraFunction.service.INGRESS_EXIT_CODE = "0"
        return self.ingress_data_cid

    def Integration(self):
        self.infraFunction.service.INTEGRATION_HOME = \
            self.infraFunction.service.meshClient.INTEGRATION_HOME + "/outputs"
        # Path(self.infraFunction.service.INTEGRATION_INPUT_CACHE).mkdir(parents=True, exist_ok=True)
        # Path(self.infraFunction.service.INTEGRATION_INPUT_DATA_CACHE).mkdir(parents=True, exist_ok=True)
        self.infraFunction.integration_cache_subproc(
            input_dir_cid=self.infraFunction.service.INGRESS_DATA_HOME,
            cwd=self.infraFunction.service.INTEGRATION_INPUT_CACHE
            # cwd=self.infraFunction.service.INTEGRATION_INPUT_DATA_CACHE
            # v_output_dir=self.infraFunction.service.INTEGRATION_INPUT_DATA_CACHE
        )
        process_input = self.infraFunction.service.INGRESS_DATA_PATH
        if not process_input:
            raise RuntimeError(
                "INGRESS_DATA_PATH is unset; ingress must return (cid, data_dir) "
                "so Ray reads only this run's ingress folder."
            )
        wait_for_directory(process_input, check_interval=1)
        # InfraFunction orchestrating Plant: dispatches Process
        # (integrated_subproc) as a Ray job on the deployed Plant's Ray
        # cluster via the Job Submission API, rather than running it in
        # this (ephemeral executor) process.
        self.infraFunction.infrafunction_subproc(
            self.infraFunction.integrated_subproc,
            process_input,
            self.infraFunction.service.INTEGRATION_HOME,
            dashboard_address=self.infraFunction.service.RAY_DASHBOARD_ADDRESS,
            minio_endpoint_pod=self.infraFunction.service.MINIO_ENDPOINT_POD,
            minio_endpoint_host=self.infraFunction.service.MINIO_ENDPOINT_HOST,
            minio_bucket=self.infraFunction.service.MINIO_BUCKET,
            minio_access_key=self.infraFunction.service.MINIO_ACCESS_KEY,
            minio_secret_key=self.infraFunction.service.MINIO_SECRET_KEY,
        )
        wait_for_directory(self.infraFunction.service.INTEGRATION_HOME, check_interval=1)
        self.integration_data_cid, _ = \
            self.infraFunction.service.meshClient.cidDir(self.infraFunction.service.INTEGRATION_HOME)
        # print(self.infraFunction.service.INGRESS_DATA_HOME)
        # print(self.infraFunction.service.INTEGRATION_INPUT_DATA_CACHE)
        # print(self.infraFunction.service.INTEGRATION_HOME)
        # print(self.integration_data_cid)
        # exit()
        return self.integration_data_cid

    def Egress(self):
        self.infraFunction.service.meshClient.EGRESS_HOME = \
            self.egress_data_cid = self.invoice_data_cid = \
            self.infraFunction.egress_subproc(
                input_dir_cid=self.integration_data_cid
            )
        self.infraFunction.service.EGRESS_JOB_STATUS = "Completed"
        self.infraFunction.service.EGRESS_EXIT_CODE = "0"
        return self.egress_data_cid

    def process(self):
        print("CAT Executing")
        print("CAT Ingress")
        self.ingress_data_cid = self.Ingress()
        print("CAT Integration")
        self.integration_data_cid = self.Integration()
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

        # Process (FaaS): the Functional Data Processors.
        self.process_cid = self.function['process_cid']
        self.process = json.loads(self.service.meshClient.cat(self.process_cid))
        self.ingress_subproc_cid = self.process['ingress_subproc_cid']
        self.integrated_subproc_cid = self.process['integrated_subproc_cid']
        self.egress_subproc_cid = self.process['egress_subproc_cid']
        self.integration_cache_subproc_cid = self.process['integration_cache_subproc_cid']

        # InfraFunction (FaaS): the orchestrator that dispatches Process
        # onto the Plant (SaaS) - see Processor.Integration().
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
