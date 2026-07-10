import json
from datetime import datetime
from pathlib import Path
from cats.executor import Structure, Function


class Executor:
    def __init__(self,
        service
    ):
        self.service = service
        self.CAT_HOME = None

        self.structure: Structure = Structure(self.service)
        self.function: Function = Function(self.service)
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

    def execute(self, enhanced_bom=None):
        self.catStore()
        if enhanced_bom is not None:
            self.enhanced_bom = enhanced_bom

        self.invoiceCID = self.enhanced_bom['invoice_cid']
        self.orderCID = self.enhanced_bom['invoice']['order_cid']
        plant_snapshot = self.structure.reconcile(self.enhanced_bom['order'].get('structure_cid'))
        self.ingress_job_id, self.integration_s3_output, self.egress_job_id = self.function.execute()

        self.enhanced_bom['function'] = json.loads(self.service.meshClient.cat(self.enhanced_bom['order']['function_cid']))
        self.enhanced_bom['plant'] = plant_snapshot
        self.enhanced_bom['log'] = {
            'ingress_job_id': self.ingress_job_id,
            'integration_output_cid': self.integration_s3_output,
            'egress_job_id': self.egress_job_id,
            'plant_rebuilt': plant_snapshot['rebuilt']
        }
        self.enhanced_bom['invoice']['data_cid'] = self.function.invoice_data_cid
        self.enhanced_bom['log_cid'] = self.service.meshClient.ipfsClient.add_json(self.enhanced_bom['log'])

        del self.enhanced_bom['bom_json_cid']
        del self.enhanced_bom['init_data_cid']
        return self.enhanced_bom, None


class Factory:
    def __init__(self,
        service,
        order=None
    ):
        self.Executor = Executor(service=service)
        self.order = order

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





