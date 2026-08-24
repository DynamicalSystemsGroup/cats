import json
import logging
from pathlib import Path

from cats.factory import Factory
from cats.network import ContentMesh
from cats.network.feedback import build_execution_bom, sign_execution_bom
from cats.network.identity import node_did as resolve_node_did
from cats.network.ldp import BomLdpStore, bom_ldp_uri
from cats.network.ldp.ldn import announce_bom
from cats.network.ldp.solid_client import SolidBomPublisher, solid_configured
from cats.network.registry import BomRegistry, build_record
from cats.utils import subproc_run, executeCMD

logger = logging.getLogger(__name__)


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

        self.init_bom_json_id = None
        self.bom_json_id = None
        self.init_bom_car_id = None
        self.enhanced_init_bom = None
        self.enhanced_bom = None

        self.order_id = None
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
        function_id, init_data_id, init_bom_filename,
        structure_id=None, structure_filepath=None, order_id=None
    ):
        if init_bom_filename is None:
            init_bom_filename = self.contentMesh.CAR_HOME

        self.init_bom_car_id, self.init_bom_json_id = self.contentMesh.initBOMcar(
            structure_id=structure_id,
            structure_filepath=structure_filepath,
            function_id=function_id,
            init_data_id=init_data_id,
            init_bom_filename=init_bom_filename,
            order_id=order_id,
        )
        self.enhanced_bom, init_bom = self.contentMesh.getEnhancedBom(
            bom_json_id=self.init_bom_json_id,
            INPUT_HOME=self.INPUT_HOME,
            OUTPUT_HOME=self.OUTPUT_HOME
        )

        from cats.network.cas import ref_id

        self.order_id = ref_id(
            self.enhanced_bom['invoice'], 'order', cats_home=self.CATS_HOME
        )
        self.bom_json_id = self.init_bom_json_id = self.enhanced_bom['bom_json_id']
        return self.init_bom_car_id, self.bom_json_id

    def execute(self, catFactory, order_request):
        executor = catFactory.produce()
        # invoice content id (and structure_as_executed nesting / order
        # backfill) is produced by Executor.execute() — Runtime.execute()
        # wraps invoice + log + node_did, signs (Phase 1b), then
        # mints bom over the signed object.
        enhanced_bom, invoice_id = executor.execute(order_request)

        from cats.network.cas import ref_id, ref_uri, resolve_invoice_data_stages

        # Structure as-executed nesting is on the Invoice (Executor-minted).
        # Stage refs feed signed PROV wasDerivedFrom edges (intra-run lineage).
        invoice = enhanced_bom.get('invoice') or {}
        order = enhanced_bom.get('order') or {}
        order_id = (
            ref_id(invoice, 'order', cats_home=self.CATS_HOME)
            or order_request.get('order_id')
            or ref_id(order, 'order', cats_home=self.CATS_HOME)
        )
        input_data_id = None
        input_invoice_locator = ref_uri(order, 'invoice') or ref_id(
            order, 'invoice', cats_home=self.CATS_HOME
        )
        if input_invoice_locator:
            try:
                input_invoice = json.loads(
                    self.contentMesh.cat(input_invoice_locator)
                )
                input_data_id = ref_id(
                    input_invoice, 'data', cats_home=self.CATS_HOME
                )
            except Exception:
                input_data_id = None

        stages = resolve_invoice_data_stages(
            invoice,
            content_mesh=self.contentMesh,
            cats_home=self.CATS_HOME,
        )
        log_id = ref_id(enhanced_bom, 'log', cats_home=self.CATS_HOME)
        bom = build_execution_bom(
            log_id=log_id,
            invoice_id=invoice_id,
            node_did=resolve_node_did(cats_home=self.CATS_HOME),
            order_id=order_id,
            input_data_id=input_data_id,
            ingress_data_id=stages['ingress_data_id'],
            integration_data_id=stages['integration_data_id'],
            data_id=stages['egress_data_id']
            or ref_id(invoice, 'data', cats_home=self.CATS_HOME),
            structure_as_executed_id=ref_id(
                invoice, 'structure_as_executed', cats_home=self.CATS_HOME
            ),
            invoice_uri=enhanced_bom.get('invoice_uri') or invoice.get('invoice_uri'),
            log_uri=enhanced_bom.get('log_uri') or ref_uri(enhanced_bom, 'log'),
            order_uri=ref_uri(invoice, 'order'),
            ingress_data_uri=stages['ingress_data_uri'],
            integration_data_uri=stages['integration_data_uri'],
            data_uri=stages['egress_data_uri'] or ref_uri(invoice, 'data'),
            structure_as_executed_uri=ref_uri(invoice, 'structure_as_executed'),
        )
        bom = sign_execution_bom(bom, cats_home=self.CATS_HOME)
        # CAS-over-HTTP: mint signed BOM bytes as ni: (Kubo write not used).
        bom_id = self.contentMesh.put_json(bom)
        # Phase 2a control plane: local Node LDP cache + optional Solid dual-write.
        BomLdpStore(self.CATS_HOME).put(bom_id, bom)
        # Phase 2b: ensure Order LDP resource exists for order_uri discovery.
        if order_id:
            try:
                order_obj = json.loads(self.contentMesh.cat(order_id))
                from cats.network.cas import LocatorIndex
                from cats.network.ldp import OrderLdpStore, order_ldp_uri

                OrderLdpStore(self.CATS_HOME).put(order_id, order_obj)
                order_uri = order_ldp_uri(order_id)
                LocatorIndex(self.CATS_HOME).put(
                    order_id, uri=order_uri, media_type='application/json'
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning('Order LDP publish skipped for %s: %s', order_id, exc)
                order_uri = None
        else:
            order_uri = None
        bom_response = {
            'bom': bom,
            'content_id': bom_id,
            'bom_ldp_uri': bom_ldp_uri(bom_id),
            'bom_solid_uri': None,
            'invoice_uri': enhanced_bom.get('invoice_uri'),
            'order_uri': order_uri,
        }
        if solid_configured():
            # Fail Runtime when Solid is configured and PUT fails (dual-write
            # consistency). LDN announce is best-effort and never fails execute.
            bom_solid_uri = SolidBomPublisher().publish(bom_id, bom)
            bom_response['bom_solid_uri'] = bom_solid_uri

        # §6f: emit BOM hl: when digest + best locator exist.
        from urllib.parse import urlparse

        from cats.network.cas.digest import is_ni_or_digest
        from cats.network.cas.hashlink import to_hl
        from cats.network.node_http import _node_base_url

        hint = bom_response.get('bom_solid_uri') or bom_response.get('bom_ldp_uri')
        if is_ni_or_digest(bom_id) and hint:
            bom_response['hl'] = to_hl(bom_id, hint)
            host = urlparse(_node_base_url()).hostname or ''
            if (
                host in ('127.0.0.1', 'localhost', '::1')
                and not bom_response.get('bom_solid_uri')
            ):
                logger.warning(
                    'CAT_NODE_HOST=%s is loopback; bom_ldp_uri in hl: is not '
                    'mesh-reachable — set CAT_NODE_HOST to a peer-reachable '
                    'address or rely on Solid bom_solid_uri',
                    host,
                )

        if solid_configured():
            try:
                announce_bom(
                    None,
                    bom_id,
                    bom_response['bom_solid_uri'],
                    hl=bom_response.get('hl'),
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    'LDN announce unexpected error for %s: %s',
                    bom_id,
                    exc,
                )
        # Control-Feedback registry index (before 2b): fail closed on put error.
        from cats.network.cas import LocatorIndex

        loc_index = LocatorIndex(self.CATS_HOME)
        for stage_id in (
            invoice_id,
            order_id,
            stages['egress_data_id'],
            stages['ingress_data_id'],
            stages['integration_data_id'],
            stages['data_stages_id'],
            ref_id(invoice, 'seed', cats_home=self.CATS_HOME),
            ref_id(invoice, 'structure_as_executed', cats_home=self.CATS_HOME),
            log_id,
            bom_id,
        ):
            if not stage_id:
                continue
            if is_ni_or_digest(stage_id):
                loc_index.put_cas_node_locator(stage_id)

        BomRegistry(self.CATS_HOME).put(
            build_record(
                bom,
                content_id=bom_id,
                content_mesh=self.contentMesh,
                locators={
                    'bom_ldp_uri': bom_response['bom_ldp_uri'],
                    'bom_solid_uri': bom_response['bom_solid_uri'],
                    'invoice_uri': bom_response.get('invoice_uri'),
                    'order_uri': bom_response.get('order_uri'),
                },
            )
        )
        return bom_response
