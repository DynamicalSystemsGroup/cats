"""Directory-manifest content-address equivalence (CAS trees).

Distinct from registry ``content_equiv`` (mesh.cat ≡ HTTP of envelope slots)
and from provenance DataFrame endpoint checks.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

HttpGetJson = Callable[[str], Any]


def _entries_fingerprints(obj: Any) -> list[Any]:
    """Normalize manifest ``entries`` (or fall back to the object) for compare."""
    items = obj if isinstance(obj, list) else [obj]
    out: list[Any] = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get('entries'), dict):
            out.append(dict(sorted(item['entries'].items())))
        else:
            out.append(item)
    return out


def assert_directory_manifest_equiv(
    uri_a: str,
    uri_b: str,
    *,
    http_get_json: HttpGetJson,
) -> None:
    """Assert two CAS URIs content-address-match.

    Passes when URIs are identical **or** fetched directory-manifest ``entries``
    (or full JSON payloads) are equal. Raises ``AssertionError`` otherwise.
    """
    if not isinstance(uri_a, str) or not uri_a.strip():
        raise AssertionError(f'missing uri_a: {uri_a!r}')
    if not isinstance(uri_b, str) or not uri_b.strip():
        raise AssertionError(f'missing uri_b: {uri_b!r}')
    uri_a = uri_a.strip()
    uri_b = uri_b.strip()
    if uri_a == uri_b:
        return
    body_a = http_get_json(uri_a)
    body_b = http_get_json(uri_b)
    if _entries_fingerprints(body_a) == _entries_fingerprints(body_b):
        return
    raise AssertionError(
        f'directory-manifest content mismatch: {uri_a!r} != {uri_b!r}'
    )


def assert_stage_lineage_payload_equiv(
    bom: dict[str, Any],
    *,
    http_get_json: HttpGetJson,
) -> None:
    """Assert BOM ``stageLineage`` payload hops content-address-match.

    For each entity with ``prov:wasDerivedFrom``:

    - Stage 0 (ingress ← input): entity ``@id`` ≡ derived-from ``@id``.
    - Later stages: derived-from ``@id`` ≡ previous payload stage ``@id``
      (PROV pointer coherence; does **not** require transform output ≡ input).

    Skips entities without ``wasDerivedFrom`` (e.g. ``structure_as_executed``).
    """
    if not isinstance(bom, dict):
        raise AssertionError(f'BOM is not a JSON object: {type(bom).__name__}')
    lineage = bom.get('stageLineage') or []
    if not isinstance(lineage, list):
        raise AssertionError(
            f'stageLineage is not a list: {type(lineage).__name__}'
        )

    prev_uri: str | None = None
    payload_index = 0
    for index, entity in enumerate(lineage):
        if not isinstance(entity, dict):
            continue
        derived = entity.get('prov:wasDerivedFrom')
        if not isinstance(derived, dict):
            continue
        derived_uri = derived.get('@id')
        entity_uri = entity.get('@id')
        if not isinstance(derived_uri, str) or not derived_uri.strip():
            raise AssertionError(
                f'stageLineage[{index}] missing wasDerivedFrom @id: {entity!r}'
            )
        if not isinstance(entity_uri, str) or not entity_uri.strip():
            raise AssertionError(
                f'stageLineage[{index}] missing @id: {entity!r}'
            )
        derived_uri = derived_uri.strip()
        entity_uri = entity_uri.strip()

        if payload_index == 0:
            assert_directory_manifest_equiv(
                entity_uri, derived_uri, http_get_json=http_get_json
            )
        elif prev_uri is not None:
            assert_directory_manifest_equiv(
                derived_uri, prev_uri, http_get_json=http_get_json
            )

        prev_uri = entity_uri
        payload_index += 1
