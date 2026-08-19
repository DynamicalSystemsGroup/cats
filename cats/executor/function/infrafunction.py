import json

from cats.executor.function.processor import Processor
from cats.network.cas import ref_id, ref_uri


class InfraFunction:
    def __init__(self, runtime, function_id):
        self.runtime = runtime
        self.enhanced_bom = self.runtime.enhanced_bom
        self.function_id = function_id
        self.function = json.loads(self.runtime.contentMesh.cat(self.function_id))
        cats_home = getattr(self.runtime, 'CATS_HOME', None)

        # Process [Composed Function]: transport callables (ingress,
        # integration_cache, egress) plus the hotF (integrated_subproc).
        # Process is the composition, not the REPLaC UI and not itself a hotF.
        self.process_id = ref_id(self.function, 'process', cats_home=cats_home)
        process_locator = ref_uri(self.function, 'process') or self.process_id
        self.process = json.loads(self.runtime.contentMesh.cat(process_locator))
        self.ingress_subproc_id = ref_id(
            self.process, 'ingress_subproc', cats_home=cats_home
        )
        self.integrated_subproc_id = ref_id(
            self.process, 'integrated_subproc', cats_home=cats_home
        )
        self.egress_subproc_id = ref_id(
            self.process, 'egress_subproc', cats_home=cats_home
        )
        self.integration_cache_subproc_id = ref_id(
            self.process, 'integration_cache_subproc', cats_home=cats_home
        )

        # InfraFunction [Actuator]: dispatches the hotF (integrated_subproc)
        # onto the Plant (SaaS) - see Integration().
        self.infrafunction_id = ref_id(
            self.function, 'infrafunction', cats_home=cats_home
        )
        infrafunction_locator = (
            ref_uri(self.function, 'infrafunction') or self.infrafunction_id
        )
        self.infrafunction = json.loads(
            self.runtime.contentMesh.cat(infrafunction_locator)
        )
        self.infrafunction_subproc_id = ref_id(
            self.infrafunction, 'infrafunction_subproc', cats_home=cats_home
        )

        process_source_id = ref_id(
            self.function, 'process_source', cats_home=cats_home
        )
        infrafunction_source_id = ref_id(
            self.function, 'infrafunction_source', cats_home=cats_home
        )
        if not process_source_id or not infrafunction_source_id:
            raise RuntimeError(
                'function is missing process_source / infrafunction_source '
                'refs; recreate the Order with create_order_request after '
                'hybrid Function source ids.'
            )
        mesh = self.runtime.contentMesh
        self.ingress_subproc = mesh.resolve_subproc(
            self.ingress_subproc_id, expected_source_id=process_source_id
        )
        self.integrated_subproc = mesh.resolve_subproc(
            self.integrated_subproc_id, expected_source_id=process_source_id
        )
        self.egress_subproc = mesh.resolve_subproc(
            self.egress_subproc_id, expected_source_id=process_source_id
        )
        self.integration_cache_subproc = mesh.resolve_subproc(
            self.integration_cache_subproc_id,
            expected_source_id=process_source_id,
        )
        self.infrafunction_subproc = mesh.resolve_subproc(
            self.infrafunction_subproc_id,
            expected_source_id=infrafunction_source_id,
        )

    def compose(self):
        return Processor(self)
