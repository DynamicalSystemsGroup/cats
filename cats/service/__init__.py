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
        # Set by Executor.execute() from Structure.reconcile()'s Plant
        # snapshot, before Function.execute() runs - lets InfraFunction
        # dispatch Processing onto the Plant actually deployed for this CAT
        # (see Processor.Integration() in cats/executor/function/__init__.py).
        self.RAY_DASHBOARD_ADDRESS = None
        # Set by Executor.execute() from InfraStructure's MinIO accessors,
        # alongside RAY_DASHBOARD_ADDRESS - lets InfraFunction write Ray
        # Data results to (and retrieve them from) a filesystem every Ray
        # node actually shares, instead of gathering to one node's disk.
        self.MINIO_ENDPOINT_HOST = None
        self.MINIO_ENDPOINT_POD = None
        self.MINIO_BUCKET = None
        self.MINIO_ACCESS_KEY = None
        self.MINIO_SECRET_KEY = None

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
            init_bom_filename=f"{self.OUTPUT_HOME}/bom.car",
            # Real, already-submitted Order CID - already known before any
            # BOM/Order processing happens. Threading it straight through
            # (rather than letting initBOMjson mint its own placeholder
            # Order) is what makes the locally-materialized order.json and
            # the order_cid Executor.execute() later backfills into the
            # final Invoice the exact same CID (see docs/NodeProductFlow.md#2b).
            order_cid=order_request['order_cid'],
        )
        return Factory(self, order_request), order_request

    def initBOMcar(self,
        function_cid, init_data_cid, init_bom_filename,
        structure_cid=None, structure_filepath=None, order_cid=None
    ):
        if init_bom_filename is None:
            init_bom_filename = self.meshClient.CAR_HOME

        self.init_bom_car_cid, self.init_bom_json_cid = self.meshClient.initBOMcar(
            structure_cid=structure_cid,
            structure_filepath=structure_filepath,
            function_cid=function_cid,
            init_data_cid=init_data_cid,
            init_bom_filename=init_bom_filename,
            order_cid=order_cid,
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
        # invoice_cid (and the order_cid backfill it depends on) is
        # produced by Executor.execute() itself now - Service.execute()
        # just assembles it alongside the Plant/InfraStructure snapshot
        # CIDs into the final bom/bom_cid.
        enhanced_bom, invoice_cid = executor.execute(order_request)

        bom = {
            'log_cid': enhanced_bom['log_cid'],
            # Distinct from order.structure_cid.plant_cid (the input-side
            # Terraform module CID) - this is the output-side snapshot of
            # what Plant.snapshot() actually observed after reconcile().
            'plant_snapshot_cid': self.meshClient.ipfsClient.add_json(enhanced_bom['plant']),
            # Output-side counterpart to order.structure_cid.infrastructure_cid,
            # mirroring plant_snapshot_cid above.
            'infrastructure_snapshot_cid': self.meshClient.ipfsClient.add_json(enhanced_bom['infrastructure']),
            'invoice_cid': invoice_cid
        }
        bom_response = {
            'bom': bom,
            'bom_cid': self.meshClient.ipfsClient.add_str(json.dumps(bom))
        }
        return bom_response