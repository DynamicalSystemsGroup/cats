import json
import uuid
from datetime import datetime
from pathlib import Path

from cats.executor.function import Function
from cats.executor.structure import Structure


class Executor:
    def __init__(self,
        runtime, structure, function
    ):
        self.runtime = runtime
        self.CAT_HOME = None

        self.structure: Structure = structure
        self.function: Function = function
        self.bom_json_cid: str = self.runtime.bom_json_cid
        self.enhanced_bom, self.bom = self.runtime.contentMesh.getEnhancedBom(
            self.bom_json_cid, self.runtime.INPUT_HOME, self.runtime.OUTPUT_HOME
        )
        self.orderCID = None
        self.invoiceCID = None

        self.ingress_data_cid = None
        self.integration_data_cid = None
        self.egress_data_cid = None

    def catStore(self):
        self.CAT_HOME = self.runtime.CAT_HOME = self.runtime.contentMesh.CAT_HOME = \
            f"""{self.runtime.JOB_HOME}/cat={datetime.utcnow().isoformat()}"""
        self.runtime.INGRESS_HOME = self.runtime.contentMesh.INGRESS_HOME = f"{self.CAT_HOME}/ingress"
        self.runtime.INTEGRATION_HOME = self.runtime.contentMesh.INTEGRATION_HOME = f"{self.CAT_HOME}/integration"
        self.runtime.EGRESS_HOME = self.runtime.contentMesh.EGRESS_HOME = f"{self.CAT_HOME}/egress"
        self.runtime.EGRESS_INPUT_DATA = self.runtime.contentMesh.EGRESS_INPUT_DATA = f"{self.runtime.EGRESS_HOME}/outputs"
        self.runtime.PROCESS_HOME = self.runtime.contentMesh.PROCESS_HOME = f"{self.CAT_HOME}/process"

        Path(self.runtime.INGRESS_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.runtime.INTEGRATION_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.runtime.EGRESS_HOME).mkdir(parents=True, exist_ok=True)
        Path(self.runtime.EGRESS_INPUT_DATA).mkdir(parents=True, exist_ok=True)
        Path(self.runtime.PROCESS_HOME).mkdir(parents=True, exist_ok=True)

    def execute(self, order_request):
        self.catStore()

        self.invoiceCID = self.enhanced_bom['invoice_cid']
        self.orderCID = self.enhanced_bom['invoice']['order_cid']
        plant_snapshot = self.structure.reconcile()
        object_store = self.structure.infraStructure.obj_store_context()
        plant = self.structure.plant.plant_port()
        transport = self.structure.infraStructure.transport_context()
        self.ingress_data_cid, self.integration_data_cid, self.egress_data_cid = \
            self.function.execute(
                object_store=object_store,
                plant=plant,
                transport=transport,
            )

        # function_cid / structure_cid: as-Code; structure_as_executed_cid on
        # the Invoice records what Plant / InfraStructure actually ran.
        self.enhanced_bom['function'] = json.loads(self.runtime.contentMesh.cat(self.enhanced_bom['order']['function_cid']))
        self.enhanced_bom['structure'] = json.loads(self.runtime.contentMesh.cat(self.enhanced_bom['order']['structure_cid']))
        mesh = self.runtime.contentMesh
        from cats.network.cas import content_uri, set_cid_uri

        object_store_as_executed_cid = mesh.put_json(object_store.snapshot())
        infrastructure_as_executed_cid = mesh.put_json(
            self.structure.infraStructure.snapshot(
                object_store_as_executed_cid=object_store_as_executed_cid,
            )
        )
        plant_as_executed_cid = mesh.put_json(plant_snapshot)
        structure_as_executed = {
            'plant_as_executed_cid': plant_as_executed_cid,
            'infrastructure_as_executed_cid': infrastructure_as_executed_cid,
        }
        set_cid_uri(structure_as_executed, 'plant_as_executed_cid', plant_as_executed_cid)
        set_cid_uri(
            structure_as_executed,
            'infrastructure_as_executed_cid',
            infrastructure_as_executed_cid,
        )
        structure_as_executed_cid = mesh.put_json(structure_as_executed)
        self.enhanced_bom['log'] = {
            'ingress_data_cid': self.ingress_data_cid,
            'integration_data_cid': self.integration_data_cid,
            'egress_data_cid': self.egress_data_cid,
            'plant_rebuilt': plant_snapshot['rebuilt'],
            # Non-secret object-store scratch URI for Structure-lifetime
            # correlation; durable retrieval remains integration_data_cid (IPFS).
            'object_store_result_uri': self.function.processor.object_store_result_uri,
            # Durable Entity Relationship correlators (None until promote is used).
            'durable_er_uri': self.function.processor.durable_er_uri,
            'durable_er_pointer': self.function.processor.durable_er_pointer,
        }
        set_cid_uri(self.enhanced_bom['log'], 'ingress_data_cid', self.ingress_data_cid)
        set_cid_uri(
            self.enhanced_bom['log'], 'integration_data_cid', self.integration_data_cid
        )
        set_cid_uri(self.enhanced_bom['log'], 'egress_data_cid', self.egress_data_cid)
        # Invoice feedback (Seed deferred / #187): stage CIDs on Invoice until
        # Seed holds the Process replay dictionary.
        invoice = self.enhanced_bom['invoice']
        set_cid_uri(invoice, 'data_cid', self.function.invoice_data_cid)
        set_cid_uri(invoice, 'ingress_data_cid', self.ingress_data_cid)
        set_cid_uri(invoice, 'integration_data_cid', self.integration_data_cid)
        set_cid_uri(invoice, 'structure_as_executed_cid', structure_as_executed_cid)
        self.enhanced_bom['log_cid'] = mesh.put_json(self.enhanced_bom['log'])
        log_uri = content_uri(self.enhanced_bom['log_cid'])
        if log_uri:
            self.enhanced_bom['log_uri'] = log_uri

        # Process replay dictionary (CFL §4B / #187). num_partitions is the
        # observed I/O + hotF alignment `n` this run used (Processor's
        # env-selected value today; Seed becomes the control-plane home once
        # Executor reads `n` from it - see populate_invoice_seed_field plan).
        # rng_seed: Process/NumPy-usable int (np.random.default_rng); also
        # Ray Data seed=-acceptable via a Plant ComputePort adapter, should a
        # stochastic step ever forward it - Process itself must not import Ray.
        n = getattr(self.function.processor, 'num_partitions', 1)
        seed_hex = uuid.uuid4().hex
        seed = {
            'seed': seed_hex,
            'rng_seed': int(seed_hex[:8], 16) & 0x7FFFFFFF,
            'num_partitions': int(n),
        }
        seed_cid = mesh.put_json(seed)
        set_cid_uri(invoice, 'seed_cid', seed_cid)

        # Invoice CID: produced here (by the Executor), not by
        # Runtime.execute() - so "Invoice CIDs are produced by the
        # Executor" holds at the class level. Backfilling order_cid with
        # the real, already-submitted order_request['order_cid'] directly
        # (as opposed to the placeholder order_cid getEnhancedBom() may
        # have fetched into self.enhanced_bom['order']) is what makes the
        # Invoice point at "the original CID-ed Order" (see
        # docs/NodeProductFlow.md#2b). Factory.accept threads this same
        # order_cid into the bootstrap Invoice via Runtime.initBOMcar /
        # ContentMesh.initBOMjson, so the locally materialized order.json
        # and this final Invoice's order_cid are the exact same CID for
        # every execution, not just a re-hash that happens to match it.
        order_cid = order_request['order_cid']
        set_cid_uri(invoice, 'order_cid', order_cid)
        invoice_cid = mesh.put_json(invoice)
        # Phase 2b: publish Invoice LDP resource (URI address of record).
        from cats.network.cas import LocatorIndex
        from cats.network.ldp import InvoiceLdpStore, invoice_ldp_uri

        InvoiceLdpStore(self.runtime.CATS_HOME).put(invoice_cid, invoice)
        inv_uri = invoice_ldp_uri(invoice_cid)
        LocatorIndex(self.runtime.CATS_HOME).put(
            invoice_cid, uri=inv_uri, media_type='application/json'
        )
        self.enhanced_bom['invoice_uri'] = inv_uri

        del self.enhanced_bom['bom_json_cid']
        del self.enhanced_bom['init_data_cid']
        return self.enhanced_bom, invoice_cid
