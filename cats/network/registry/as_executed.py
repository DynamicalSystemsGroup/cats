"""As-executed observation — SAE lineage bind + nest slots + Plant snapshot.

Distinct from payload ``stageLineage`` hops (``assert_stage_lineage_payload_equiv``)
and from Invoice ``content_equiv`` (mesh ≡ HTTP of ``structure_as_executed_uri``).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cats.network.registry.execution_bind import (
    _entity_agrees,
    _fetch_payload,
    _ref_token,
    _require_uri,
)
from cats.network.registry.handoff import _require_str_slots

HttpGetJson = Callable[[str], Any]

PLANT_AS_EXECUTED_KEYS = (
    'applied_structure_id',
    'kind_cluster_name',
    'kubeconfig_context',
    'ray_dashboard_address',
    'ray_release_name',
    'rebuilt',
)


def assert_structure_as_executed_slots(structure_as_executed: dict[str, Any]) -> None:
    """Assert as-executed Structure has plant + infrastructure URIs."""
    if not isinstance(structure_as_executed, dict):
        raise AssertionError(
            'structure_as_executed is not a JSON object: '
            f'{type(structure_as_executed).__name__}'
        )
    _require_str_slots(
        structure_as_executed,
        'plant_as_executed_uri',
        'infrastructure_as_executed_uri',
        label='structure_as_executed',
    )


def assert_infrastructure_as_executed_slots(
    infrastructure_as_executed: dict[str, Any],
) -> None:
    """Assert as-executed Infrastructure has ``object_store_as_executed_uri``."""
    if not isinstance(infrastructure_as_executed, dict):
        raise AssertionError(
            'infrastructure_as_executed is not a JSON object: '
            f'{type(infrastructure_as_executed).__name__}'
        )
    _require_str_slots(
        infrastructure_as_executed,
        'object_store_as_executed_uri',
        label='infrastructure_as_executed',
    )


def _sae_lineage_entity(
    bom: dict[str, Any],
    structure_as_executed_uri: str,
) -> dict[str, Any]:
    if not isinstance(bom, dict):
        raise AssertionError(f'BOM is not a JSON object: {type(bom).__name__}')
    lineage = bom.get('stageLineage') or []
    if not isinstance(lineage, list):
        raise AssertionError(
            f'stageLineage is not a list: {type(lineage).__name__}'
        )
    matches: list[dict[str, Any]] = []
    for entity in lineage:
        if not isinstance(entity, dict):
            continue
        try:
            _entity_agrees(
                entity,
                structure_as_executed_uri,
                label='structure_as_executed',
            )
        except AssertionError:
            continue
        matches.append(entity)
    if not matches:
        raise AssertionError(
            'no stageLineage entity agrees with structure_as_executed_uri '
            f'{structure_as_executed_uri!r}'
        )
    observation = [
        entity
        for entity in matches
        if not isinstance(entity.get('prov:wasDerivedFrom'), dict)
    ]
    if not observation:
        raise AssertionError(
            'structure_as_executed lineage match still has wasDerivedFrom: '
            f'{matches!r}'
        )
    return observation[-1]


def assert_structure_as_executed_bind(
    bom: dict[str, Any],
    *,
    structure_as_executed_uri: str,
    http_get_json: HttpGetJson | None = None,
    expected_structure_as_executed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assert a ``stageLineage`` observation entity ≡ Invoice SAE URI.

    Finds the lineage entity whose ``@id`` / ``contentId`` agrees with
    ``structure_as_executed_uri`` and that has no ``prov:wasDerivedFrom``.
    Optional GET of that ``@id`` (http(s)) must be a JSON object; when
    ``expected_structure_as_executed`` is set, payloads must match.
    """
    sae_uri = _require_uri(
        structure_as_executed_uri, label='structure_as_executed_uri'
    )
    if expected_structure_as_executed is not None and http_get_json is None:
        raise AssertionError(
            'expected_structure_as_executed requires http_get_json'
        )
    entity = _sae_lineage_entity(bom, sae_uri)
    if http_get_json is not None:
        _fetch_payload(
            entity,
            http_get_json=http_get_json,
            expected=expected_structure_as_executed,
            label='structure_as_executed',
        )
    return entity


def assert_plant_as_executed_snapshot(
    plant: dict[str, Any] | None,
    *,
    structure_id: str | None = None,
) -> None:
    """Assert Plant as-executed snapshot keys (+ optional Structure equality).

    ``structure_id`` is ``ref_id(order, 'structure')`` when provided; compared
    to ``applied_structure_id`` via digest token (``ni:`` vs hex OK).
    """
    if not isinstance(plant, dict):
        raise AssertionError(
            f'plant as-executed is not a JSON object: {type(plant).__name__}'
        )
    missing = [key for key in PLANT_AS_EXECUTED_KEYS if key not in plant]
    if missing:
        raise AssertionError(
            f'plant as-executed missing {missing}: {plant!r}'
        )
    if not isinstance(plant.get('rebuilt'), bool):
        raise AssertionError(
            f'plant as-executed rebuilt must be bool: {plant.get("rebuilt")!r}'
        )
    if structure_id is None:
        return
    applied = plant.get('applied_structure_id')
    if not isinstance(applied, str) or not applied.strip():
        raise AssertionError(
            f'plant as-executed missing applied_structure_id: {plant!r}'
        )
    if _ref_token(applied) != _ref_token(structure_id):
        raise AssertionError(
            'plant.applied_structure_id token '
            f'{_ref_token(applied)!r} != order.structure token '
            f'{_ref_token(structure_id)!r}'
        )
