"""Data Product manufacturing cell (Software / Manufacturing factory).

CAT Node is a Data Product on a Data Mesh. Factory accepts a content-addressed
Order, stages materials via ContentMesh (through Runtime.initBOMcar), assembles
Function + Structure (AQ halves), and produces an ephemeral Executor.

Not Structure's Plant [SaaS] (compute generation) — see docs/PLANTs.md.
"""
from __future__ import annotations

from cats.executor import Executor, Function, Structure
from cats.network.cas import ref_id


class Factory:
    """Data Product manufacturing cell (Software/Manufacturing factory).

    Accepts a content-addressed Order, stages materials via ContentMesh,
    assembles Function+Structure (AQ halves), produces an ephemeral Executor.
    Not Structure's Plant [SaaS] (compute generation).
    """

    def __init__(self, runtime):
        self.runtime = runtime
        self.order_request = None
        self.structure = None
        self.function = None
        self.executor = None

    def accept(self, order_request, init_data_id: str) -> Factory:
        """Receive work order: stage BOM materials, then assemble."""
        order = order_request['order']
        cats_home = getattr(self.runtime, 'CATS_HOME', None)
        structure_id = ref_id(order, 'structure', cats_home=cats_home)
        function_id = ref_id(order, 'function', cats_home=cats_home)
        if not structure_id or not function_id:
            raise RuntimeError(
                'Order missing structure / function refs '
                '(structure_uri/structure_cid, function_uri/function_cid)'
            )
        self.runtime.initBOMcar(
            structure_id=structure_id,
            structure_filepath=order['structure_filepath'],
            function_id=function_id,
            init_data_id=init_data_id,
            init_bom_filename=f"{self.runtime.OUTPUT_HOME}/bom.car",
            # Real, already-submitted Order content id — threads into bootstrap
            # Invoice so order.json and Executor Invoice.order ref match
            # (see docs/NodeProductFlow.md#2b).
            order_id=order_request['order_id'],
        )
        self.order_request = order_request
        self.assemble()
        return self

    def assemble(self) -> None:
        """Compose Function + construct Structure; instantiate Executor."""
        order = self.order_request['order']
        cats_home = getattr(self.runtime, 'CATS_HOME', None)
        structure_id = ref_id(order, 'structure', cats_home=cats_home)
        function_id = ref_id(order, 'function', cats_home=cats_home)
        self.structure = Structure(self.runtime, structure_id)
        self.function = Function(self.runtime, function_id)
        self.executor = Executor(self.runtime, self.structure, self.function)

    def produce(self):
        """Yield the ephemeral Executor for this Order."""
        return self.executor
