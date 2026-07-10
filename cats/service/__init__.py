import json, os
from pathlib import Path
import boto3 as boto3

from cats.factory import Factory
from cats.network import MeshClient
from cats.service.k8s import KubeService
from cats.utils import subproc_run, executeCMD


class Service:
    def __init__(self,
        meshClient: MeshClient,
        CATS_HOME: str
    ):
        self.meshClient: MeshClient = meshClient
        self.kubeService: KubeService = KubeService

        self.AWS_ACCESS_KEY_ID = None
        self.AWS_SECRET_ACCESS_KEY = None
        self.S3_CLIENT = None
        try:
            self.AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
            self.AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
            self.S3_CLIENT = boto3.client(
                's3',
                region_name='us-east-2',
                aws_access_key_id=self.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=self.AWS_SECRET_ACCESS_KEY
            )
        except:
            self.S3_CLIENT = None
        self.CATS_HOME = self.meshClient.CATS_HOME = CATS_HOME
        self.DATA_HOME = self.meshClient.DATA_HOME = self.CATS_HOME + '/data'
        self.JOB_HOME = self.meshClient.JOB_HOME = self.DATA_HOME + '/jobs'
        self.CACHE_HOME = self.meshClient.CACHE_HOME = self.DATA_HOME + "/cache"
        self.INPUT_HOME = self.meshClient.INPUT_HOME = self.DATA_HOME + '/input'
        self.OUTPUT_HOME = self.meshClient.OUTPUT_HOME = self.DATA_HOME + '/output'
        self.OUTPUT_DATA_HOME = self.meshClient.OUTPUT_DATA_HOME = self.OUTPUT_HOME + '/data'
        self.INPUT_STRUCTURE_HOME = self.meshClient.INPUT_STRUCTURE_HOME = self.INPUT_HOME + '/structure'
        self.INPUT_DATA_HOME = self.meshClient.INPUT_DATA_HOME = self.INPUT_HOME + '/data'
        self.INTEGRATION_INPUT_CACHE = self.meshClient.INTEGRATION_INPUT_CACHE = \
            f"{self.CACHE_HOME}/integration"
        self.INTEGRATION_INPUT_DATA_CACHE = self.meshClient.INTEGRATION_INPUT_DATA_CACHE = \
            f"{self.INTEGRATION_INPUT_CACHE}/outputs"
        self.bucket_name = self.DATA_HOME.split('/')[-1]
        self.job_directory_path = f"{self.JOB_HOME.split('/')[-1]}/"
        self.cache_directory_path = f"{self.CACHE_HOME.split('/')[-1]}/"
        self.catStore()

        self.CAT_HOME = None
        self.INGRESS_HOME = None
        self.INGRESS_DATA_HOME = None
        self.INGRESS_DATA_PATH = None
        self.INGRESS_EXIT_CODE = None
        self.INGRESS_JOB_STATUS = None
        self.INTEGRATION_HOME = None
        self.EGRESS_HOME = None
        self.EGRESS_EXIT_CODE = None
        self.EGRESS_JOB_STATUS = None

        self.init_bom_json_cid = None
        self.bom_json_cid = None
        self.init_bom_car_cid = None
        self.enhanced_init_bom = None
        self.enhanced_bom = None

        self.order_cid = None
        self.subproc_run = lambda cmd: subproc_run(cmd, cwd=self.CATS_HOME)
        self.executeCMD = executeCMD

    def catStore(self):
        Path(self.DATA_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.JOB_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.CACHE_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.INPUT_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.OUTPUT_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.INTEGRATION_INPUT_CACHE).mkdir(parents=True, exist_ok=True)
        Path(self.INTEGRATION_INPUT_DATA_CACHE).mkdir(parents=True, exist_ok=True)
        # Path(self.OUTPUT_DATA_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.INPUT_STRUCTURE_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.INPUT_DATA_HOME).mkdir(parents=True, exist_ok=True)

    def initFactory(self, order_request, ipfs_uri):
        self.initBOMcar(
            structure_cid=order_request['order']['structure_cid'],
            structure_filepath=order_request['order']['structure_filepath'],
            function_cid=order_request['order']['function_cid'],
            init_data_cid=ipfs_uri,
            init_bom_filename=f"{self.OUTPUT_HOME}/bom.car"
        )
        return Factory(self), order_request

    def initBOMcar(self,
        function_cid, init_data_cid, init_bom_filename,
        structure_cid=None, structure_filepath=None
    ):
        if init_bom_filename is None:
            init_bom_filename = self.meshClient.CAR_HOME

        self.init_bom_car_cid, self.init_bom_json_cid = self.meshClient.initBOMcar(
            structure_cid=structure_cid,
            structure_filepath=structure_filepath,
            function_cid=function_cid,
            init_data_cid=init_data_cid,
            init_bom_filename=init_bom_filename
        )
        self.enhanced_bom, init_bom = self.meshClient.getEnhancedBom(
            bom_json_cid=self.init_bom_json_cid,
            INPUT_HOME=self.INPUT_HOME,
            OUTPUT_HOME=self.OUTPUT_HOME
        )

        self.order_cid = self.enhanced_bom['invoice']['order_cid']
        self.bom_json_cid = self.init_bom_json_cid = self.enhanced_bom['bom_json_cid']
        return self.init_bom_car_cid, self.bom_json_cid

    def execute(self, catFactory, order_request):
        executor = catFactory.produce()
        enhanced_bom, _ = executor.execute()

        invoice = {}
        enhanced_bom['invoice']['order_cid'] = self.meshClient.ipfsClient.add_str(
            json.dumps(order_request['order'])
        )
        invoice['invoice_cid'] = self.meshClient.ipfsClient.add_str(
            json.dumps(enhanced_bom['invoice'])
        )
        invoice['invoice'] = enhanced_bom['invoice']

        bom = {
            'log_cid': enhanced_bom['log_cid'],
            'plant_cid': self.meshClient.ipfsClient.add_json(enhanced_bom['plant']),
            'invoice_cid': invoice['invoice_cid']
        }
        bom_response = {
            'bom': bom,
            'bom_cid': self.meshClient.ipfsClient.add_str(json.dumps(bom))
        }
        return bom_response