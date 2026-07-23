import json

from cats.executor.function.processor import Processor


class InfraFunction:
    def __init__(self, service, function_cid):
        self.service = service
        self.enhanced_bom = self.service.enhanced_bom
        self.function_cid = function_cid
        self.function = json.loads(self.service.contentMesh.cat(self.function_cid))

        # Process [Composed Function]: transport callables (ingress,
        # integration_cache, egress) plus the tHOF (integrated_subproc).
        # Process is the composition, not the REPLaC UI and not itself a tHOF.
        self.process_cid = self.function['process_cid']
        self.process = json.loads(self.service.contentMesh.cat(self.process_cid))
        self.ingress_subproc_cid = self.process['ingress_subproc_cid']
        self.integrated_subproc_cid = self.process['integrated_subproc_cid']
        self.egress_subproc_cid = self.process['egress_subproc_cid']
        self.integration_cache_subproc_cid = self.process['integration_cache_subproc_cid']

        # InfraFunction [Actuator]: dispatches the tHOF (integrated_subproc)
        # onto the Plant (SaaS) - see Integration().
        self.infrafunction_cid = self.function['infrafunction_cid']
        self.infrafunction = json.loads(self.service.contentMesh.cat(self.infrafunction_cid))
        self.infrafunction_subproc_cid = self.infrafunction['infrafunction_subproc_cid']

        process_source_cid = self.function.get('process_source_cid')
        infrafunction_source_cid = self.function.get('infrafunction_source_cid')
        if not process_source_cid or not infrafunction_source_cid:
            raise RuntimeError(
                'function_cid is missing process_source_cid / '
                'infrafunction_source_cid; recreate the Order with '
                'create_order_request after hybrid Function source CIDs.'
            )
        mesh = self.service.contentMesh
        self.ingress_subproc = mesh.resolve_subproc(
            self.ingress_subproc_cid, expected_source_cid=process_source_cid
        )
        self.integrated_subproc = mesh.resolve_subproc(
            self.integrated_subproc_cid, expected_source_cid=process_source_cid
        )
        self.egress_subproc = mesh.resolve_subproc(
            self.egress_subproc_cid, expected_source_cid=process_source_cid
        )
        self.integration_cache_subproc = mesh.resolve_subproc(
            self.integration_cache_subproc_cid,
            expected_source_cid=process_source_cid,
        )
        self.infrafunction_subproc = mesh.resolve_subproc(
            self.infrafunction_subproc_cid,
            expected_source_cid=infrafunction_source_cid,
        )

    def compose(self):
        return Processor(self)
