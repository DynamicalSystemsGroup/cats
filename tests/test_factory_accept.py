"""Unit tests for Factory manufacturing-cell API (accept → assemble → produce)."""
from types import SimpleNamespace

from cats.factory import Factory


def test_factory_accept_stages_bom_then_assembles(monkeypatch):
    runtime = SimpleNamespace(OUTPUT_HOME='/tmp/cats-out')
    init_calls = []

    def _init_bom_car(**kwargs):
        init_calls.append(kwargs)

    runtime.initBOMcar = _init_bom_car

    fake_structure = object()
    fake_function = object()
    fake_executor = object()

    monkeypatch.setattr(
        'cats.factory.factory.Structure',
        lambda svc, cid: fake_structure,
    )
    monkeypatch.setattr(
        'cats.factory.factory.Function',
        lambda svc, cid: fake_function,
    )
    monkeypatch.setattr(
        'cats.factory.factory.Executor',
        lambda svc, structure, function: fake_executor,
    )

    order_request = {
        'order_cid': 'QmOrder',
        'order': {
            'structure_cid': 'QmStruct',
            'structure_filepath': 'structure',
            'function_cid': 'QmFn',
        },
    }

    factory = Factory(runtime).accept(order_request, 'QmInitData')

    assert len(init_calls) == 1
    assert init_calls[0]['structure_cid'] == 'QmStruct'
    assert init_calls[0]['function_cid'] == 'QmFn'
    assert init_calls[0]['init_data_cid'] == 'QmInitData'
    assert init_calls[0]['order_cid'] == 'QmOrder'
    assert factory.structure is fake_structure
    assert factory.function is fake_function
    assert factory.executor is fake_executor
    assert factory.produce() is fake_executor
