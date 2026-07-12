import json
from datetime import datetime
from pathlib import Path
from cats.executor import Structure, Function


class Executor:
    def __init__(self,
        service, structure, function
    ):
        self.service = service
        self.CAT_HOME = None

        self.structure: Structure = structure
        self.function: Function = function
        self.bom_json_cid: str = self.service.bom_json_cid
        self.enhanced_bom, self.bom = self.service.meshClient.getEnhancedBom(
            self.bom_json_cid, self.service.INPUT_HOME, self.service.OUTPUT_HOME
        )
        self.orderCID = None
        self.invoiceCID = None

        self.ingress_job_id = None
        self.integration_s3_output = None
        self.egress_job_id = None

    def catStore(self):
        self.CAT_HOME = self.service.CAT_HOME = self.service.meshClient.CAT_HOME = \
            f"""{self.service.JOB_HOME}/cat={datetime.utcnow().isoformat()}"""
        self.service.INGRESS_HOME = self.service.meshClient.INGRESS_HOME = f"{self.CAT_HOME}/ingress"
        self.service.INTEGRATION_HOME = self.service.meshClient.INTEGRATION_HOME = f"{self.CAT_HOME}/integration"
        self.service.EGRESS_HOME = self.service.meshClient.EGRESS_HOME = f"{self.CAT_HOME}/egress"
        self.service.EGRESS_INPUT_DATA = self.service.meshClient.EGRESS_INPUT_DATA = f"{self.service.EGRESS_HOME}/outputs"
        self.service.PROCESS_HOME = self.service.meshClient.PROCESS_HOME = f"{self.CAT_HOME}/process"

        Path(self.service.INGRESS_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.service.INTEGRATION_HOME).mkdir(parents=True, exist_ok=True)
        # Path(self.service.INTEGRATION_INPUT_CACHE).mkdir(parents=True, exist_ok=True)
        # Path(self.service.INTEGRATION_INPUT_DATA_CACHE).mkdir(parents=True, exist_ok=True)
        Path(self.service.EGRESS_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.service.EGRESS_INPUT_DATA).mkdir(parents=True, exist_ok=True)
        Path(self.service.PROCESS_HOME).mkdir(parents=True, exist_ok=True)

    def execute(self, order_request):
        self.catStore()

        self.invoiceCID = self.enhanced_bom['invoice_cid']
        self.orderCID = self.enhanced_bom['invoice']['order_cid']
        plant_snapshot = self.structure.reconcile()
        self.service.RAY_DASHBOARD_ADDRESS = plant_snapshot['ray_dashboard_address']
        self.service.MINIO_ENDPOINT_HOST = self.structure.infraStructure.minio_endpoint_host()
        self.service.MINIO_ENDPOINT_POD = self.structure.infraStructure.minio_endpoint_pod()
        self.service.MINIO_BUCKET = self.structure.infraStructure.minio_bucket()
        self.service.MINIO_ACCESS_KEY = self.structure.infraStructure.minio_access_key()
        self.service.MINIO_SECRET_KEY = self.structure.infraStructure.minio_secret_key()
        self.ingress_job_id, self.integration_s3_output, self.egress_job_id = self.function.execute()

        # function_cid -> {process_cid, infrafunction_cid}; structure_cid ->
        # {plant_cid, infrastructure_cid} - surfaced here alongside the
        # Plant snapshot so the BOM records both what Structure/Function
        # were specified (as Code) and what Plant was actually observed.
        self.enhanced_bom['function'] = json.loads(self.service.meshClient.cat(self.enhanced_bom['order']['function_cid']))
        self.enhanced_bom['structure'] = json.loads(self.service.meshClient.cat(self.enhanced_bom['order']['structure_cid']))
        self.enhanced_bom['plant'] = plant_snapshot
        self.enhanced_bom['infrastructure'] = self.structure.infraStructure.minio_snapshot()
        self.enhanced_bom['log'] = {
            'ingress_job_id': self.ingress_job_id,
            'integration_output_cid': self.integration_s3_output,
            'egress_job_id': self.egress_job_id,
            'plant_rebuilt': plant_snapshot['rebuilt']
        }
        self.enhanced_bom['invoice']['data_cid'] = self.function.invoice_data_cid
        self.enhanced_bom['log_cid'] = self.service.meshClient.ipfsClient.add_json(self.enhanced_bom['log'])

        # Invoice CID: produced here (by the Executor), not by
        # Service.execute() - so "Invoice CIDs are produced by the
        # Executor" holds at the class level. Backfilling order_cid with
        # the real, already-submitted order_request['order_cid'] directly
        # (as opposed to the placeholder order_cid getEnhancedBom() may
        # have fetched into self.enhanced_bom['order']) is what makes the
        # Invoice point at "the original CID-ed Order" (see
        # docs/NodeProductFlow.md#2b) - Service.initFactory() now threads
        # this same order_cid into the bootstrap Invoice too (see
        # MeshClient.initBOMjson), so the locally materialized order.json
        # and this final Invoice's order_cid are the exact same CID for
        # every execution, not just a re-hash that happens to match it.
        self.enhanced_bom['invoice']['order_cid'] = order_request['order_cid']
        invoice_cid = self.service.meshClient.ipfsClient.add_str(
            json.dumps(self.enhanced_bom['invoice'])
        )

        del self.enhanced_bom['bom_json_cid']
        del self.enhanced_bom['init_data_cid']
        return self.enhanced_bom, invoice_cid


class Factory:
    def __init__(self,
        service,
        order_request
    ):
        self.service = service
        self.order_request = order_request

        order = order_request['order']
        self.structure: Structure = Structure(service, order['structure_cid'])
        self.function: Function = Function(service, order['function_cid'])
        self.Executor = Executor(service, self.structure, self.function)

    def initCAT(self,
        function_cid, ipfs_uri,
        structure_cid=None, structure_filepath=None
    ):
        return self.service.initBOMcar(
            structure_cid=structure_cid,
            structure_filepath=structure_filepath,
            function_cid=function_cid,
            init_data_cid=ipfs_uri
        )

    def produce(self):
        return self.Executor





