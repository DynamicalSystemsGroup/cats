import importlib.util
import os
import sys

from cats.executor.structure._tf import (
    _terraform_output,
    read_applied_structure_id,
)


class Plant:
    """Composed, read-only accessor over the deployed Plant (`module.plant`
    in main.tf): the kind cluster + Helm releases that constitute the
    dynamically scaled execution environment InfraStructure provisions and
    maintains. Always obtained via `InfraStructure.compose()`, mirroring
    how `InfraFunction.compose()` produces a `Processor`."""

    def __init__(self, infraStructure):
        self.infraStructure = infraStructure
        # Set by Structure.deploy()/redeploy() after each reconcile(), so
        # snapshot() can record whether this reconciliation reused the
        # existing Plant or destroyed and rebuilt it.
        self.rebuilt = None

    def _load_plant_utils(self):
        """Load Order-submitted plant context utils."""
        path = os.path.join(
            self.infraStructure.INPUT_STRUCTURE_HOME,
            'plant',
            'plant_utils.py',
        )
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        spec = importlib.util.spec_from_file_location(
            'plant_plant_utils', path
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        # Required before exec_module so @dataclass can resolve cls.__module__.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def context(self):
        """Resolve PlantContext from terraform outputs via Order-submitted
        plant utils (directory model). Observation + Ray dashboard URL;
        dispatch uses ``plant_port()`` → PlantPort."""
        utils = self._load_plant_utils()
        structure_home = self.infraStructure.INPUT_STRUCTURE_HOME
        runtime = self.infraStructure.runtime

        def get_output(name):
            return _terraform_output(runtime, structure_home, name)

        return utils.PlantContext.from_terraform_outputs(get_output)

    def plant_port(self):
        """Resolve Function-owned PlantPort (RayPlantPort for this Plant)."""
        utils = self._load_plant_utils()
        return utils.plant_port_from_context(self.context())

    def snapshot(self):
        """Plain dict describing what this Plant currently is, for
        recording into the CAT's BOM alongside Function's output (see
        Executor.execute() in cats/executor/executor.py)."""
        return self.context().snapshot(
            rebuilt=self.rebuilt,
            applied_structure_id=read_applied_structure_id(
                self.infraStructure.INPUT_STRUCTURE_HOME
            ),
        )
