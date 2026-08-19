"""Structure half of the Architectural Quantum (PaaS + Plant/InfraStructure)."""
from cats.executor.structure._tf import (
    modules_installed,
    read_applied_structure_id,
    write_applied_structure_id,
)
from cats.executor.structure.infrastructure import InfraStructure
from cats.executor.structure.plant import Plant


class Structure:
    def __init__(self, runtime, structure_id):
        self.runtime = runtime
        self.bom_json_id = self.runtime.bom_json_id
        self.infraStructure: InfraStructure = InfraStructure(
            runtime=self.runtime, structure_id=structure_id
        )
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
        rebuild when the incoming (content-addressed) structure_id
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
        structure_id = self.infraStructure.structure_id
        structure_home = self.infraStructure.INPUT_STRUCTURE_HOME
        applied_id = read_applied_structure_id(structure_home)
        if structure_id and applied_id == structure_id:
            print(f'Structure {structure_id} already applied; reconciling in place.')
            self.deploy()
        else:
            self.redeploy()
        if structure_id:
            write_applied_structure_id(structure_home, structure_id)
        return self.plant.snapshot()


__all__ = [
    'Structure',
    'InfraStructure',
    'Plant',
    'modules_installed',
    'read_applied_structure_id',
    'write_applied_structure_id',
]
