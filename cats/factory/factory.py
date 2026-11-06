"""CAT Factory: the agent line that operates the CAT Assembler.

Composition (eBOM) and Release (mBOM) are named stations. They do not read a
SysML project or a GitHub Issue, and they do not call create_order_request
or link*. accept and produce delegate to the Assembler, which produces one
ephemeral Executor.

This class is the skeleton of the AI software factory. It is not a Wikipedia
software factory, and it is not the manufacturing cell.
"""
from __future__ import annotations

from cats.assembler import Assembler


class Composition:
    """eBOM station. A named type only."""


class Release:
    """mBOM station. A named type only."""


class Factory:
    """Agent line that operates the CAT Assembler.

    Holds Composition and Release. accept delegates to Assembler.accept.
    produce returns that Assembler's ephemeral Executor.
    """

    def __init__(self, runtime):
        self.runtime = runtime
        self.composition = Composition()
        self.release = Release()
        self.assembler = Assembler(runtime)

    def accept(self, order_request, init_data_id: str) -> Factory:
        """Operate the Assembler: stage the Order and assemble."""
        self.assembler.accept(order_request, init_data_id)
        return self

    def produce(self):
        """Return the Assembler's ephemeral Executor for this Order."""
        return self.assembler.produce()
