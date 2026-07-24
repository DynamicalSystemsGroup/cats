"""Data Product manufacturing cell (Software / Manufacturing factory).

CAT Node is a Data Product on a Data Mesh. Factory accepts a content-addressed
Order, stages materials via ContentMesh (through Service.initBOMcar), assembles
Function + Structure (AQ halves), and produces an ephemeral Executor.

Not Structure's Plant [SaaS] (compute generation) — see docs/PLANTs.md.
"""
from __future__ import annotations

from cats.executor import Executor, Function, Structure


class Factory:
    """Data Product manufacturing cell (Software/Manufacturing factory).

    Accepts a content-addressed Order, stages materials via ContentMesh,
    assembles Function+Structure (AQ halves), produces an ephemeral Executor.
    Not Structure's Plant [SaaS] (compute generation).
    """

    def __init__(self, service):
        self.service = service
        self.order_request = None
        self.structure = None
        self.function = None
        self.executor = None

    def accept(self, order_request, init_data_cid: str) -> Factory:
        """Receive work order: stage BOM materials, then assemble."""
        order = order_request['order']
        self.service.initBOMcar(
            structure_cid=order['structure_cid'],
            structure_filepath=order['structure_filepath'],
            function_cid=order['function_cid'],
            init_data_cid=init_data_cid,
            init_bom_filename=f"{self.service.OUTPUT_HOME}/bom.car",
            # Real, already-submitted Order CID — threads into bootstrap
            # Invoice so order.json and Executor Invoice.order_cid match
            # (see docs/NodeProductFlow.md#2b).
            order_cid=order_request['order_cid'],
        )
        self.order_request = order_request
        self.assemble()
        return self

    def assemble(self) -> None:
        """Compose Function + construct Structure; instantiate Executor."""
        order = self.order_request['order']
        self.structure = Structure(self.service, order['structure_cid'])
        self.function = Function(self.service, order['function_cid'])
        self.executor = Executor(self.service, self.structure, self.function)

    def produce(self):
        """Yield the ephemeral Executor for this Order."""
        return self.executor
