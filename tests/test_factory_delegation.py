"""Factory delegates accept and produce to the Assembler. Stations stay unused."""
from types import SimpleNamespace

from cats.factory import Composition, Factory, Release


def test_factory_accept_delegates_and_stations_stay_unused(monkeypatch):
    runtime = SimpleNamespace()
    calls = []

    class FakeAssembler:
        def __init__(self, host):
            assert host is runtime
            self.executor = None

        def accept(self, order_request, init_data_id):
            calls.append(('accept', order_request, init_data_id))
            self.executor = 'ephemeral-executor'
            return self

        def produce(self):
            calls.append('produce')
            return self.executor

    monkeypatch.setattr('cats.factory.factory.Assembler', FakeAssembler)

    factory = Factory(runtime)
    assert isinstance(factory.composition, Composition)
    assert isinstance(factory.release, Release)
    assert factory.composition.__dict__ == {}
    assert factory.release.__dict__ == {}

    order_request = {'order_id': 'QmOrder'}
    returned = factory.accept(order_request, 'QmInitData')

    assert returned is factory
    assert calls == [('accept', order_request, 'QmInitData')]
    assert factory.produce() == 'ephemeral-executor'
    assert calls == [('accept', order_request, 'QmInitData'), 'produce']
    assert factory.composition.__dict__ == {}
    assert factory.release.__dict__ == {}
