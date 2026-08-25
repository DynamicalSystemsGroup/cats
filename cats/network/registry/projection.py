"""Assert post-execute BomRegistry / LocatorIndex handoff projection is complete."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cats.network.cas.digest import from_ni, is_ni_or_digest
from cats.network.registry.store import BomRegistry


def _same_id(left: str, right: str) -> bool:
    if is_ni_or_digest(left) and is_ni_or_digest(right):
        return from_ni(left) == from_ni(right)
    return left.strip() == right.strip()


def _ids_contain(haystack: Iterable[str], needle: str) -> bool:
    return any(_same_id(item, needle) for item in haystack)


def assert_handoff_projection_complete(
    registry: BomRegistry,
    locator_index,
    *,
    bom_id: str,
    require_stage_locators: bool = True,
    stage_ids: list[str | None] | None = None,
) -> dict[str, Any]:
    """Assert Runtime-style handoff projection for ``bom_id`` is complete.

    Checks:

    - ``registry.get(bom_id)`` exists
    - Required fields: equality ``data`` / ``order``, ``locators.bom_ldp_uri``,
      ``invoice_uri`` (record or locators)
    - Reverse indexes: ``bom_id`` in ``lookup_bom(data)`` and
      ``lookup_by_order(order)``
    - When ``require_stage_locators``: each digest in ``stage_ids`` (or, if
      omitted, ids taken from the record when present) has a non-empty
      ``LocatorIndex.lookup_uris`` entry

    Returns the registry ``record``. Does **not** GET envelope HTTP bodies
    (see ``assert_registry_claims_reachable``).
    """
    record = registry.get(bom_id)
    if record is None:
        raise AssertionError(f'no registry record for BOM {bom_id!r}')

    data_id = record.get('data') or record.get('data_cid')
    order_id = record.get('order') or record.get('order_cid')
    if not data_id or not order_id:
        raise AssertionError(
            f'registry record for {bom_id!r} missing data/order: {record!r}'
        )

    locs = record.get('locators') or {}
    bom_ldp_uri = locs.get('bom_ldp_uri')
    if not isinstance(bom_ldp_uri, str) or not bom_ldp_uri.strip():
        raise AssertionError(
            f'registry record for {bom_id!r} missing locators.bom_ldp_uri'
        )
    invoice_uri = record.get('invoice_uri') or locs.get('invoice_uri')
    if not isinstance(invoice_uri, str) or not invoice_uri.strip():
        raise AssertionError(
            f'registry record for {bom_id!r} missing invoice_uri'
        )

    by_data = registry.lookup_bom(data_id)
    if not _ids_contain(by_data, bom_id):
        raise AssertionError(
            f'bom_id {bom_id!r} not in by-data list for {data_id!r}: {by_data!r}'
        )
    by_order = registry.lookup_by_order(order_id)
    if not _ids_contain(by_order, bom_id):
        raise AssertionError(
            f'bom_id {bom_id!r} not in by-order list for {order_id!r}: '
            f'{by_order!r}'
        )

    if require_stage_locators:
        if stage_ids is None:
            stage_ids = [
                bom_id,
                data_id,
                order_id,
                record.get('invoice') or record.get('invoice_cid'),
                record.get('seed') or record.get('seed_cid'),
                record.get('ingress_data') or record.get('ingress_data_cid'),
                record.get('integration_data')
                or record.get('integration_data_cid'),
                record.get('data_stages') or record.get('data_stages_cid'),
                record.get('structure_as_executed')
                or record.get('structure_as_executed_cid'),
                record.get('log') or record.get('log_cid'),
            ]
        for stage_id in stage_ids:
            if not stage_id or not isinstance(stage_id, str):
                continue
            if not is_ni_or_digest(stage_id):
                continue
            uris = locator_index.lookup_uris(stage_id)
            if not uris:
                raise AssertionError(
                    f'LocatorIndex missing URIs for stage id {stage_id!r} '
                    f'(bom {bom_id!r})'
                )

    return record
