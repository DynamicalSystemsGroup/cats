import json
from pathlib import Path

from cats.factory import Factory
from cats.network import ContentMesh
from cats.network.feedback import build_execution_bom
from cats.network.identity import node_uri as resolve_node_uri
from cats.utils import subproc_run, executeCMD


class Runtime:
    """Data Product process-lifetime ambient: layout, ContentMesh, Order entry.

    Long-lived Node substrate under the peer edge (`cats.node`). Owns host paths
    and ContentMesh; delegates manufacturing to Factory and wraps the BOM
    envelope. Not the peer, not Factory, not the per-Order Executor.
    """

    def __init__(self,
        contentMesh: ContentMesh,
        CATS_HOME: str
    ):
        self.contentMesh: ContentMesh = contentMesh

        self.CATS_HOME = self.contentMesh.CATS_HOME = CATS_HOME
        self.DATA_HOME = self.contentMesh.DATA_HOME = self.CATS_HOME + '/data'
        self.JOB_HOME = self.contentMesh.JOB_HOME = self.DATA_HOME + '/jobs'
        self.CACHE_HOME = self.contentMesh.CACHE_HOME = self.DATA_HOME + "/cache"
        self.INPUT_HOME = self.contentMesh.INPUT_HOME = self.DATA_HOME + '/input'
        self.OUTPUT_HOME = self.contentMesh.OUTPUT_HOME = self.DATA_HOME + '/output'
        self.OUTPUT_DATA_HOME = self.contentMesh.OUTPUT_DATA_HOME = self.OUTPUT_HOME + '/data'
        self.INPUT_STRUCTURE_HOME = self.contentMesh.INPUT_STRUCTURE_HOME = self.INPUT_HOME + '/structure'
        self.INPUT_DATA_HOME = self.contentMesh.INPUT_DATA_HOME = self.INPUT_HOME + '/data'
        self.INTEGRATION_INPUT_CACHE = self.contentMesh.INTEGRATION_INPUT_CACHE = \
            f"{self.CACHE_HOME}/integration"
        self.INTEGRATION_INPUT_DATA_CACHE = self.contentMesh.INTEGRATION_INPUT_DATA_CACHE = \
            f"{self.INTEGRATION_INPUT_CACHE}/outputs"
        self.catStore()

        self.CAT_HOME = None
        self.INGRESS_HOME = None
        self.INTEGRATION_HOME = None
        self.EGRESS_HOME = None

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
        """Runtime entry: delegate Order intake to Factory manufacturing cell."""
        factory = Factory(self).accept(order_request, ipfs_uri)
        return factory, order_request

    def initBOMcar(self,
        function_cid, init_data_cid, init_bom_filename,
        structure_cid=None, structure_filepath=None, order_cid=None
    ):
        if init_bom_filename is None:
            init_bom_filename = self.contentMesh.CAR_HOME

        self.init_bom_car_cid, self.init_bom_json_cid = self.contentMesh.initBOMcar(
            structure_cid=structure_cid,
            structure_filepath=structure_filepath,
            function_cid=function_cid,
            init_data_cid=init_data_cid,
            init_bom_filename=init_bom_filename,
            order_cid=order_cid,
        )
        self.enhanced_bom, init_bom = self.contentMesh.getEnhancedBom(
            bom_json_cid=self.init_bom_json_cid,
            INPUT_HOME=self.INPUT_HOME,
            OUTPUT_HOME=self.OUTPUT_HOME
        )

        self.order_cid = self.enhanced_bom['invoice']['order_cid']
        self.bom_json_cid = self.init_bom_json_cid = self.enhanced_bom['bom_json_cid']
        return self.init_bom_car_cid, self.bom_json_cid

    def execute(self, catFactory, order_request):
        executor = catFactory.produce()
        # invoice_cid (and structure_as_executed nesting / order_cid
        # backfill) is produced by Executor.execute() — Runtime.execute()
        # only wraps invoice_cid + log_cid + node_uri into bom/bom_cid.
        enhanced_bom, invoice_cid = executor.execute(order_request)

        # Structure as-executed nesting is on the Invoice (Executor-minted).
        bom = build_execution_bom(
            log_cid=enhanced_bom['log_cid'],
            invoice_cid=invoice_cid,
            node_uri=resolve_node_uri(),
        )
        bom_response = {
            'bom': bom,
            'bom_cid': self.contentMesh.ipfsClient.add_str(json.dumps(bom)),
        }
        return bom_response
