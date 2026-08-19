"""Function half of the Architectural Quantum (FaaS + Process/InfraFunction)."""
from cats.executor.function.infrafunction import InfraFunction
from cats.executor.function.processor import Processor


class Function:
    def __init__(self, runtime, function_id):
        self.runtime = runtime
        self.CAT_HOME = None
        self.infraFunction: InfraFunction = InfraFunction(
            runtime=self.runtime, function_id=function_id
        )
        self.processor: Processor = self.infraFunction.compose()
        self.ingress_data_id = None
        self.integration_data_id = None
        self.egress_data_id = None
        self.invoice_data_id = None

    def execute(self, object_store, plant, transport):
        self.ingress_data_id, self.integration_data_id, self.egress_data_id = \
            self.processor.process(
                object_store=object_store,
                plant=plant,
                transport=transport,
            )
        self.invoice_data_id = self.processor.invoice_data_id
        return self.ingress_data_id, self.integration_data_id, self.egress_data_id


__all__ = ['Function', 'InfraFunction', 'Processor']
