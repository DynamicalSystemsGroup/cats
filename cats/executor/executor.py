import json
import uuid
from datetime import datetime
from pathlib import Path

from cats.executor.function import Function
from cats.executor.structure import Structure
from cats.network.cas import content_uri, ref_id, ref_uri, set_ref


class Executor:
    def __init__(self,
        runtime, structure, function
    ):
        self.runtime = runtime
        self.CAT_HOME = None

        self.structure: Structure = structure
        self.function: Function = function
        self.bom_json_id: str = self.runtime.bom_json_id
        self.enhanced_bom, self.bom = self.runtime.contentMesh.getEnhancedBom(
            self.bom_json_id, self.runtime.INPUT_HOME, self.runtime.OUTPUT_HOME
        )
        self.orderCID = None
        self.invoiceCID = None

        self.ingress_data_id = None
        self.integration_data_id = None
        self.egress_data_id = None

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

        cats_home = self.runtime.CATS_HOME
        self.invoiceCID = ref_id(
            self.enhanced_bom, 'invoice', cats_home=cats_home
        )
        self.orderCID = ref_id(
            self.enhanced_bom['invoice'], 'order', cats_home=cats_home
        )
        plant_snapshot = self.structure.reconcile()
        object_store = self.structure.infraStructure.obj_store_context()
        plant = self.structure.plant.plant_port()
        transport = self.structure.infraStructure.transport_context()
        self.ingress_data_id, self.integration_data_id, self.egress_data_id = \
            self.function.execute(
                object_store=object_store,
                plant=plant,
                transport=transport,
            )

        # function / structure: as-Code; structure_as_executed on the Invoice
        # records what Plant / InfraStructure actually ran.
        mesh = self.runtime.contentMesh
        function_locator = ref_uri(self.enhanced_bom['order'], 'function') or ref_id(
            self.enhanced_bom['order'], 'function', cats_home=cats_home
        )
        structure_locator = ref_uri(self.enhanced_bom['order'], 'structure') or ref_id(
            self.enhanced_bom['order'], 'structure', cats_home=cats_home
        )
        self.enhanced_bom['function'] = json.loads(mesh.cat(function_locator))
        self.enhanced_bom['structure'] = json.loads(mesh.cat(structure_locator))

        object_store_as_executed_id = mesh.put_json(object_store.snapshot())
        infrastructure_as_executed_id = mesh.put_json(
            self.structure.infraStructure.snapshot(
                object_store_as_executed_id=object_store_as_executed_id,
            )
        )
        plant_as_executed_id = mesh.put_json(plant_snapshot)
        structure_as_executed = {}
        set_ref(structure_as_executed, 'plant_as_executed', plant_as_executed_id)
        set_ref(
            structure_as_executed,
            'infrastructure_as_executed',
            infrastructure_as_executed_id,
        )
        structure_as_executed_id = mesh.put_json(structure_as_executed)
        self.enhanced_bom['log'] = {
            'plant_rebuilt': plant_snapshot['rebuilt'],
            # Non-secret object-store scratch URI for Structure-lifetime
            # correlation; durable retrieval remains integration_data (CAS).
            'object_store_result_uri': self.function.processor.object_store_result_uri,
            # Durable Entity Relationship correlators (None until promote is used).
            'durable_er_uri': self.function.processor.durable_er_uri,
            'durable_er_pointer': self.function.processor.durable_er_pointer,
        }
        set_ref(self.enhanced_bom['log'], 'ingress_data', self.ingress_data_id)
        set_ref(
            self.enhanced_bom['log'], 'integration_data', self.integration_data_id
        )
        set_ref(self.enhanced_bom['log'], 'egress_data', self.egress_data_id)
        # Invoice feedback (Seed deferred / #187): stage refs on Invoice until
        # Seed holds the Process replay dictionary.
        invoice = self.enhanced_bom['invoice']
        set_ref(invoice, 'data', self.function.invoice_data_id)
        set_ref(invoice, 'ingress_data', self.ingress_data_id)
        set_ref(invoice, 'integration_data', self.integration_data_id)
        set_ref(invoice, 'structure_as_executed', structure_as_executed_id)
        log_id = mesh.put_json(self.enhanced_bom['log'])
        set_ref(self.enhanced_bom, 'log', log_id)
        # Prefer explicit content_uri when available (set_ref already sets
        # log_uri; refresh if CAS LDP URI is resolvable).
        log_uri = content_uri(log_id)
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
        seed_id = mesh.put_json(seed)
        set_ref(invoice, 'seed', seed_id)

        # Invoice content id: produced here (by the Executor), not by
        # Runtime.execute() - so "Invoice CIDs are produced by the
        # Executor" holds at the class level. Backfilling order with
        # the real, already-submitted order_request['order_id'] directly
        # (as opposed to the placeholder order ref getEnhancedBom() may
        # have fetched into self.enhanced_bom['order']) is what makes the
        # Invoice point at "the original CID-ed Order" (see
        # docs/NodeProductFlow.md#2b). Factory.accept threads this same
        # order id into the bootstrap Invoice via Runtime.initBOMcar /
        # ContentMesh.initBOMjson, so the locally materialized order.json
        # and this final Invoice's order ref are the exact same id for
        # every execution, not just a re-hash that happens to match it.
        order_id = order_request['order_id']
        set_ref(invoice, 'order', order_id)
        invoice_id = mesh.put_json(invoice)
        # Phase 2b: publish Invoice LDP resource (URI address of record).
        from cats.network.cas import LocatorIndex
        from cats.network.ldp import InvoiceLdpStore, invoice_ldp_uri

        InvoiceLdpStore(self.runtime.CATS_HOME).put(invoice_id, invoice)
        inv_uri = invoice_ldp_uri(invoice_id)
        LocatorIndex(self.runtime.CATS_HOME).put(
            invoice_id, uri=inv_uri, media_type='application/json'
        )
        self.enhanced_bom['invoice_uri'] = inv_uri

        del self.enhanced_bom['bom_json_id']
        self.enhanced_bom.pop('init_data_cid', None)
        self.enhanced_bom.pop('init_data_uri', None)
        return self.enhanced_bom, invoice_id
