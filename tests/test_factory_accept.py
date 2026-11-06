"""Unit tests for the CAT Assembler (accept → assemble → produce)."""
from types import SimpleNamespace

from cats.assembler import Assembler


def test_assembler_accept_stages_bom_then_assembles(monkeypatch):
    runtime = SimpleNamespace(OUTPUT_HOME='/tmp/cats-out')
    init_calls = []

    def _init_bom_car(**kwargs):
        init_calls.append(kwargs)

    runtime.initBOMcar = _init_bom_car

    fake_structure = object()
    fake_function = object()
    fake_executor = object()

    monkeypatch.setattr(
        'cats.assembler.assembler.Structure',
        lambda svc, cid: fake_structure,
    )
    monkeypatch.setattr(
        'cats.assembler.assembler.Function',
        lambda svc, cid: fake_function,
    )
    monkeypatch.setattr(
        'cats.assembler.assembler.Executor',
        lambda svc, structure, function: fake_executor,
    )

    order_request = {
        'order_id': 'QmOrder',
        'order': {
            'structure_cid': 'QmStruct',
            'structure_filepath': 'structure',
            'function_cid': 'QmFn',
        },
    }

    assembler = Assembler(runtime).accept(order_request, 'QmInitData')

    assert len(init_calls) == 1
    assert init_calls[0]['structure_id'] == 'QmStruct'
    assert init_calls[0]['function_id'] == 'QmFn'
    assert init_calls[0]['init_data_id'] == 'QmInitData'
    assert init_calls[0]['order_id'] == 'QmOrder'
    assert assembler.structure is fake_structure
    assert assembler.function is fake_function
    assert assembler.executor is fake_executor
    assert assembler.produce() is fake_executor
