from cats.executor.function import InfraFunction, Processor
from cats.executor.structure import (
    InfraStructure,
    Plant,
    read_applied_structure_cid,
    write_applied_structure_cid,
)


class Structure:
    def __init__(self, service, structure_cid):
        self.service = service
        self.bom_json_cid = self.service.bom_json_cid
        self.infraStructure: InfraStructure = InfraStructure(service=self.service, structure_cid=structure_cid)
        self.plant: Plant = self.infraStructure.compose()

    def redeploy(self):
        print()
        print()
        print('Re-Deploy Structure!')
        # `destroy` needs providers already installed to even load their
        # schemas, same as `apply`/`plan` - so `initialize` must run first,
        # not just before `apply` below.
        self.infraStructure.initialize()
        self.infraStructure.destroy()
        self.infraStructure.apply()
        self.plant.rebuilt = True

    def deploy(self):
        print()
        print()
        print('Deploy Structure!')
        self.infraStructure.initialize()
        self.infraStructure.apply()
        self.plant.rebuilt = False

    def reconcile(self):
        """Materialize this CAT's Structure, skipping the destructive
        rebuild when the incoming (content-addressed) structure_cid
        matches what's already applied.

        Structure is content-addressed like everything else in CATs.
        Destroying and rebuilding the Plant (kind cluster + Helm
        releases) for a Structure whose content hasn't changed is the
        same redundant recomputation content-addressing is meant to
        avoid elsewhere in CATs; `apply()` alone is Terraform's own
        declarative reconciliation, and it's a fast no-op when nothing
        changed.

        Returns a snapshot of the resulting Plant (see `Plant.snapshot()`),
        so callers can record what this Structure actually produced
        alongside Function's output in the CAT's BOM.
        """
        structure_cid = self.infraStructure.structure_cid
        structure_home = self.infraStructure.INPUT_STRUCTURE_HOME
        applied_cid = read_applied_structure_cid(structure_home)
        if structure_cid and applied_cid == structure_cid:
            print(f'Structure {structure_cid} already applied; reconciling in place.')
            self.deploy()
        else:
            self.redeploy()
        if structure_cid:
            write_applied_structure_cid(structure_home, structure_cid)
        return self.plant.snapshot()


class Function:
    def __init__(self, service, function_cid):
        self.service = service
        self.CAT_HOME = None
        self.infraFunction: InfraFunction = InfraFunction(service=self.service, function_cid=function_cid)
        self.processor: Processor = self.infraFunction.compose()
        self.ingress_job_id = None
        self.integration_output = None
        self.egress_job_id = None
        self.invoice_data_cid = None

    def execute(self):
        self.ingress_job_id, self.integration_output, self.egress_job_id = self.processor.process()
        self.invoice_data_cid = self.processor.invoice_data_cid
        return self.ingress_job_id, self.integration_output, self.egress_job_id