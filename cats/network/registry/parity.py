"""Registry index parity — Python APIs ↔ HTTP ``GET /ldp/registry/…``.

**Parity** here means the **same index facts** must agree when read two ways:

- **Python:** ``BomRegistry`` / ``LocatorIndex`` on disk under
  ``{CATS_HOME}/.cats/registry/``
- **HTTP:** Node routes ``GET /ldp/registry/boms|by-data|by-order|by-content/…``

Goal: callers (``init`` / ``link*`` / demos) can trust either path — a projected
record or reverse-index list from Python must match what the Node serves over
HTTP for the same keys. Divergence means the disk index and the HTTP facade are
out of sync (or the wrong ``CATS_HOME`` / Node).

This is **not** a check that Invoice / ExecutionBom *content* is correct — only
that the registry **query index** is consistent across access paths. The BOM
record body check compares ``project_record(registry.get(bom_id))`` to
``GET …/boms/…``; by-data / by-order / by-content compare full reverse maps and
locator URI sets for that record's ``data`` / ``order`` digests (which may list
other BOMs that share those keys).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from cats.network.cas.digest import from_ni, is_ni_or_digest
from cats.network.registry.store import (
    AmbiguousBomError,
    BomRegistry,
    RegistryError,
    project_record,
)

HttpGetJson = Callable[[str], Any]
"""``http_get_json(path) -> dict`` — path like ``/ldp/registry/boms/<key>``."""


def registry_path_key(content_id: str) -> str:
    """Path segment for ``/ldp/registry/…/<key>`` (hex for digests, else raw id)."""
    value = (content_id or '').strip()
    if is_ni_or_digest(value):
        return from_ni(value)
    return value


def _same_id(left: str, right: str) -> bool:
    if is_ni_or_digest(left) and is_ni_or_digest(right):
        return from_ni(left) == from_ni(right)
    return left.strip() == right.strip()


def _ids_contain(haystack: Iterable[str], needle: str) -> bool:
    return any(_same_id(item, needle) for item in haystack)


def assert_registry_bom_parity(
    record: dict[str, Any],
    http_bom: dict[str, Any],
    *,
    bom_id: str,
) -> None:
    """Parity: disk record projection ≡ ``GET /ldp/registry/boms/<key>``.

    Ensures ``project_record(record)`` matches the HTTP bom body and that
    ``http_bom['content_id']`` names the same BOM as ``bom_id``.
    """
    http_id = http_bom.get('content_id')
    if not isinstance(http_id, str) or not http_id.strip():
        raise AssertionError(f'HTTP bom missing content_id: {http_bom!r}')
    if not _same_id(http_id, bom_id):
        raise AssertionError(
            f'HTTP bom content_id {http_id!r} != bom_id {bom_id!r}'
        )
    projected = project_record(record)
    if projected != http_bom:
        raise AssertionError(
            'registry.get projection must match GET /ldp/registry/boms/<key>: '
            f'{projected!r} != {http_bom!r}'
        )


def assert_registry_by_data_parity(
    bom_ids: list[str],
    http_by_data: dict[str, Any],
    *,
    data_id: str,
) -> None:
    """Parity: ``lookup_bom(data)`` ≡ ``GET /ldp/registry/by-data/<key>``.

    Compares the full reverse-index list (all BOMs that share this Invoice data
    digest), not only the BOM that seeded the lookup.
    """
    if http_by_data.get('bom_ids') != bom_ids:
        raise AssertionError(
            f'by-data bom_ids {http_by_data.get("bom_ids")!r} != '
            f'lookup_bom {bom_ids!r}'
        )
    http_key = http_by_data.get('content_id')
    if isinstance(http_key, str) and http_key.strip():
        if registry_path_key(http_key) != registry_path_key(data_id) and not _same_id(
            http_key, data_id
        ):
            raise AssertionError(
                f'by-data content_id {http_key!r} != data_id {data_id!r}'
            )


def assert_registry_by_order_parity(
    bom_ids: list[str],
    http_by_order: dict[str, Any],
    *,
    order_id: str,
    bom_id: str | None = None,
) -> None:
    """Parity: ``lookup_by_order(order)`` ≡ ``GET /ldp/registry/by-order/<key>``.

    Compares the full Order→BOM reverse-index list. When ``bom_id`` is set, also
    requires that BOM appear in the list (seed BOM is findable by its Order).
    """
    if http_by_order.get('bom_ids') != bom_ids:
        raise AssertionError(
            f'by-order bom_ids {http_by_order.get("bom_ids")!r} != '
            f'lookup_by_order {bom_ids!r}'
        )
    http_key = http_by_order.get('content_id')
    if isinstance(http_key, str) and http_key.strip():
        if registry_path_key(http_key) != registry_path_key(order_id) and not _same_id(
            http_key, order_id
        ):
            raise AssertionError(
                f'by-order content_id {http_key!r} != order_id {order_id!r}'
            )
    if bom_id is not None and not _ids_contain(bom_ids, bom_id):
        raise AssertionError(
            f'bom_id {bom_id!r} not in by-order list {bom_ids!r}'
        )


def assert_locator_index_parity(
    disk_uris: list[str],
    http_by_content: dict[str, Any],
) -> None:
    """Parity: ``LocatorIndex.lookup_uris`` ≡ ``GET …/by-content/<key>`` URIs.

    Fetch addresses for a content digest must match set-wise between disk
    locator index and the HTTP by-content document (order may differ).
    """
    http_uris = [
        entry.get('uri')
        for entry in (http_by_content.get('locators') or [])
        if entry.get('uri')
    ]
    if set(disk_uris) != set(http_uris):
        raise AssertionError(
            'LocatorIndex.lookup_uris must match GET /ldp/registry/by-content/<key>: '
            f'{set(disk_uris)!r} != {set(http_uris)!r}'
        )


def assert_registry_index_parity(
    *,
    registry: BomRegistry,
    locator_index,
    bom_id: str,
    http_get_json: HttpGetJson,
    allow_ambiguous: bool = False,
) -> dict[str, Any]:
    """Assert Python ↔ HTTP registry index parity anchored at ``bom_id``.

    **Parity** = the same index facts from disk APIs and from
    ``GET /ldp/registry/…`` agree. Loads the BOM record, derives ``data`` /
    ``order``, then checks four maps:

    1. ``project_record(record)`` ↔ ``GET …/boms/<bom>``
    2. ``lookup_bom(data)`` ↔ ``GET …/by-data/<data>``
    3. ``lookup_by_order(order)`` ↔ ``GET …/by-order/<order>``
    4. ``LocatorIndex.lookup_uris(data)`` ↔ ``GET …/by-content/<data>``

    Goal: prove the Node HTTP facade mirrors on-disk ``BomRegistry`` /
    ``LocatorIndex`` for discovery used by ``init`` / ``link*``. Does **not**
    validate signed envelope or Invoice payload correctness — only index
    consistency across the two access paths.

    When more than one BOM shares the same Invoice ``data`` digest,
    ``lookup_bom(data_id)`` has length > 1 and ``resolve_unique_bom`` raises
    ``AmbiguousBomError`` (the API ``linkProcess(content_id=…)`` needs a single
    BOM). ``allow_ambiguous`` controls that case:

    - ``False`` (default, tests): ambiguity fails. Exactly one BOM for that
      data, and it must equal the passed-in ``bom_id``.
    - ``True`` (demo): ambiguity is OK. Do not fail on ``AmbiguousBomError``;
      treat ``bom_id`` as the BOM under test as long as it still appears in the
      by-data list. Python ↔ HTTP index parity still runs. Demo re-runs often
      leave multiple BOMs for the same output data.

    Returns handoff keys: ``record``, ``data_id``, ``order_id``, ``bom_ids_by_data``,
    ``unique_bom``, ``boms_for_order``, ``data_locators``, plus the HTTP bodies.
    """
    record = registry.get(bom_id)
    if record is None:
        raise RuntimeError(f'no registry record for BOM {bom_id!r}')

    data_id = record.get('data') or record.get('data_cid')
    order_id = (
        record.get('order')
        or record.get('order_cid')
        or registry.lookup_order(bom_id)
    )
    if not data_id or not order_id:
        raise RuntimeError(
            f'registry record for {bom_id!r} missing data/order: {record!r}'
        )

    bom_ids_by_data = registry.lookup_bom(data_id)
    try:
        unique_bom = registry.resolve_unique_bom(data_id)
    except (RegistryError, AmbiguousBomError):
        if not allow_ambiguous:
            raise
        unique_bom = bom_id
        if not _ids_contain(bom_ids_by_data, bom_id):
            raise AssertionError(
                f'ambiguous by-data: bom_id {bom_id!r} not in {bom_ids_by_data!r}'
            ) from None

    if not allow_ambiguous and not _same_id(unique_bom, bom_id):
        raise AssertionError(
            f'resolve_unique_bom {unique_bom!r} != bom_id {bom_id!r}'
        )
    if allow_ambiguous and not (
        _same_id(unique_bom, bom_id) or _ids_contain(bom_ids_by_data, bom_id)
    ):
        raise AssertionError(
            f'bom_id {bom_id!r} neither unique nor listed in {bom_ids_by_data!r}'
        )

    boms_for_order = registry.lookup_by_order(order_id)
    data_locators = locator_index.lookup_uris(data_id)

    bom_key = registry_path_key(bom_id)
    data_key = registry_path_key(data_id)
    order_key = registry_path_key(order_id)

    http_bom = http_get_json(f'/ldp/registry/boms/{bom_key}')
    http_by_data = http_get_json(f'/ldp/registry/by-data/{data_key}')
    http_by_order = http_get_json(f'/ldp/registry/by-order/{order_key}')
    http_by_content = http_get_json(f'/ldp/registry/by-content/{data_key}')

    assert_registry_bom_parity(record, http_bom, bom_id=bom_id)
    assert_registry_by_data_parity(
        bom_ids_by_data, http_by_data, data_id=data_id
    )
    assert_registry_by_order_parity(
        boms_for_order, http_by_order, order_id=order_id, bom_id=bom_id
    )
    assert_locator_index_parity(data_locators, http_by_content)

    return {
        'record': record,
        'data_id': data_id,
        'order_id': order_id,
        'bom_ids_by_data': bom_ids_by_data,
        'unique_bom': unique_bom,
        'boms_for_order': boms_for_order,
        'data_locators': data_locators,
        'http_bom': http_bom,
        'http_by_data': http_by_data,
        'http_by_order': http_by_order,
        'http_by_content': http_by_content,
    }
