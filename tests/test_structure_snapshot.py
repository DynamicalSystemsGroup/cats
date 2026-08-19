"""Unit tests for InfraStructure.snapshot as-executed pairing shape."""
from types import SimpleNamespace

from cats.executor.structure import InfraStructure


def test_infrastructure_snapshot_returns_object_store_uri_ref():
    snap = InfraStructure.snapshot(
        SimpleNamespace(),
        object_store_as_executed_id='QmObjectStoreAsExecuted',
    )
    assert snap == {
        'object_store_as_executed_uri': 'QmObjectStoreAsExecuted',
    }
