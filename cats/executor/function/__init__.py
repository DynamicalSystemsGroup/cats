"""Function half of the Architectural Quantum (FaaS + Process/InfraFunction)."""
from cats.executor.function.infrafunction import InfraFunction
from cats.executor.function.processor import Processor


class Function:
    def __init__(self, runtime, function_cid):
        self.runtime = runtime
        self.CAT_HOME = None
        self.infraFunction: InfraFunction = InfraFunction(
            runtime=self.runtime, function_cid=function_cid
        )
        self.processor: Processor = self.infraFunction.compose()
        self.ingress_data_cid = None
        self.integration_data_cid = None
        self.egress_data_cid = None
        self.invoice_data_cid = None

    def execute(self, object_store, plant, transport):
        self.ingress_data_cid, self.integration_data_cid, self.egress_data_cid = \
            self.processor.process(
                object_store=object_store,
                plant=plant,
                transport=transport,
            )
        self.invoice_data_cid = self.processor.invoice_data_cid
        return self.ingress_data_cid, self.integration_data_cid, self.egress_data_cid


__all__ = ['Function', 'InfraFunction', 'Processor']
