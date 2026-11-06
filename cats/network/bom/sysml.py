"""Minimal SysML v2 JSON-LD eBOM view of the Architectural Quantum.

Compiled from Order JSON. Not KerML / Cameo interchange. Factory and
Executor must not import this module.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cats.network.bom.documents import FIXED_CREATED, projection_urn
from cats.network.bom.purl import fru_purl
from cats.network.bom.read import require_ni, stem_id
from cats.network.cas.content_ref import equality_id
from cats.network.cas.digest import is_ni_or_digest

FetchJson = Callable[[str], Any]

PART_DEFS = (
    'Function',
    'Process',
    'InfraFunction',
    'Structure',
    'Plant',
    'InfraStructure',
)

PORT_DEFS = (
    ('TransportPort', 'Process', 'function'),
    ('IoPort', 'Process', 'function'),
    ('ComputePort', 'Process', 'function'),
    ('PlantPort', 'InfraFunction', 'function'),
    ('JobHandle', 'InfraFunction', 'function'),
)

PORT_ADAPTERS = (
    ('TransportPort', 'InfraStructure', 'structure'),
    ('IoPort', 'Plant', 'structure'),
    ('ComputePort', 'Plant', 'structure'),
    ('PlantPort', 'Plant', 'structure'),
    ('JobHandle', 'Plant', 'structure'),
)

USAGE_ROLES = (
    'ArchitecturalQuantum',
    'Function',
    'Process',
    'InfraFunction',
    'Structure',
    'Plant',
    'InfraStructure',
)

_SYSML_CONTEXT = {
    'sysml': 'https://www.omg.org/spec/SysML/20250201#',
    'cats': 'https://cats.dynamicalsystemsgroup.com/ns#',
    'contentId': 'cats:contentId',
    'ownedBy': 'cats:ownedBy',
    'ownedSide': 'cats:ownedSide',
    'adapterOn': 'cats:adapterOn',
    'adapterSide': 'cats:adapterSide',
    'purl': 'https://github.com/package-url/purl-spec#purl',
}


def _optional_ni(token: str | None, *, label: str) -> str | None:
    if not isinstance(token, str) or not token.strip():
        return None
    try:
        return require_ni(token, label=label)
    except ValueError:
        return None


def expected_usage_ids(
    order: dict[str, Any],
    *,
    order_id: str,
    function: dict[str, Any] | None = None,
    structure: dict[str, Any] | None = None,
    cats_home: str | None = None,
) -> dict[str, str | None]:
    """Current Order-graph ``ni:`` ids for each AQ-role usage (None if missing)."""
    function = function if isinstance(function, dict) else {}
    structure = structure if isinstance(structure, dict) else {}
    return {
        'ArchitecturalQuantum': _optional_ni(order_id, label='order_id'),
        'Function': _optional_ni(
            stem_id(order, 'function', cats_home=cats_home), label='function_id'
        ),
        'Process': _optional_ni(
            stem_id(function, 'process', cats_home=cats_home), label='process_id'
        ),
        'InfraFunction': _optional_ni(
            stem_id(function, 'infrafunction', cats_home=cats_home),
            label='infrafunction_id',
        ),
        'Structure': _optional_ni(
            stem_id(order, 'structure', cats_home=cats_home),
            label='structure_id',
        ),
        'Plant': _optional_ni(
            stem_id(structure, 'plant', cats_home=cats_home), label='plant_id'
        ),
        'InfraStructure': _optional_ni(
            stem_id(structure, 'infrastructure', cats_home=cats_home),
            label='infrastructure_id',
        ),
    }


def quantum_sysml(
    *,
    order_id: str,
    function_id: str | None = None,
    process_id: str | None = None,
    infrafunction_id: str | None = None,
    structure_id: str | None = None,
    plant_id: str | None = None,
    infrastructure_id: str | None = None,
    created: str = FIXED_CREATED,
) -> dict[str, Any]:
    """JSON-LD Package: six part defs, five INTEROP ports, AQ + role usages."""
    order_ni = require_ni(order_id, label='order_id')
    base = projection_urn('sysml', order_ni)
    ids = {
        'ArchitecturalQuantum': order_ni,
        'Function': _optional_ni(function_id, label='function_id'),
        'Process': _optional_ni(process_id, label='process_id'),
        'InfraFunction': _optional_ni(infrafunction_id, label='infrafunction_id'),
        'Structure': _optional_ni(structure_id, label='structure_id'),
        'Plant': _optional_ni(plant_id, label='plant_id'),
        'InfraStructure': _optional_ni(infrastructure_id, label='infrastructure_id'),
    }
    elements: list[dict[str, Any]] = []
    for name in PART_DEFS:
        elements.append(
            {
                '@id': f'{base}#def:{name}',
                '@type': 'sysml:PartDefinition',
                'name': name,
            }
        )
    adapters = {port: (adapter, side) for port, adapter, side in PORT_ADAPTERS}
    for name, owner, side in PORT_DEFS:
        adapter_on, adapter_side = adapters[name]
        elements.append(
            {
                '@id': f'{base}#def:{name}',
                '@type': 'sysml:PortDefinition',
                'adapterOn': adapter_on,
                'adapterSide': adapter_side,
                'name': name,
                'ownedBy': owner,
                'ownedSide': side,
            }
        )
    for name in USAGE_ROLES:
        usage: dict[str, Any] = {
            '@id': f'{base}#usage:{name}',
            '@type': 'sysml:PartUsage',
            'definition': (
                f'{base}#def:{name}' if name in PART_DEFS else f'{base}#usage:{name}'
            ),
            'name': name,
        }
        content_id = ids.get(name)
        if content_id:
            usage['contentId'] = content_id
            if name == 'Function':
                usage['purl'] = fru_purl('function', content_id)
            elif name == 'Structure':
                usage['purl'] = fru_purl('structure', content_id)
        elements.append(usage)
    elements.sort(key=lambda item: str(item.get('@id') or ''))
    return {
        '@context': dict(_SYSML_CONTEXT),
        '@id': base,
        '@type': 'sysml:Package',
        'created': created,
        'name': 'ArchitecturalQuantum',
        'ownedElement': elements,
    }


def _elements(doc: dict[str, Any]) -> list[dict[str, Any]]:
    owned = doc.get('ownedElement')
    if not isinstance(owned, list):
        return []
    return [item for item in owned if isinstance(item, dict)]


def _usages_by_name(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in _elements(doc):
        if item.get('@type') != 'sysml:PartUsage':
            continue
        name = item.get('name')
        if isinstance(name, str) and name:
            out[name] = item
    return out


def validate_sysml_quantum(
    doc: dict[str, Any],
    order: dict[str, Any],
    *,
    order_id: str,
    function: dict[str, Any] | None = None,
    structure: dict[str, Any] | None = None,
    fetch: FetchJson | None = None,
    cats_home: str | None = None,
) -> None:
    """Fail closed on missing / stale ``contentId`` or INTEROP port mismatch.

    Does not run inside Factory / Executor. A failed check does not stop
    ``execute``.
    """
    if not isinstance(doc, dict):
        raise ValueError(f'SysML document is not a JSON object: {type(doc).__name__}')
    if doc.get('@type') != 'sysml:Package':
        raise ValueError('SysML document @type must be sysml:Package')
    elements = _elements(doc)
    part_names = {
        item.get('name')
        for item in elements
        if item.get('@type') == 'sysml:PartDefinition'
    }
    missing_parts = [name for name in PART_DEFS if name not in part_names]
    if missing_parts:
        raise ValueError(f'SysML missing part defs: {missing_parts}')
    ports = {
        item.get('name'): item
        for item in elements
        if item.get('@type') == 'sysml:PortDefinition'
        and isinstance(item.get('name'), str)
    }
    for name, owner, side in PORT_DEFS:
        port = ports.get(name)
        if port is None:
            raise ValueError(f'SysML missing port def: {name}')
        if port.get('ownedBy') != owner or port.get('ownedSide') != side:
            raise ValueError(
                f'SysML port {name} owner mismatch: '
                f'expected {owner}/{side}, got '
                f'{port.get("ownedBy")}/{port.get("ownedSide")}'
            )
        adapter_on, adapter_side = next(
            (a, s) for p, a, s in PORT_ADAPTERS if p == name
        )
        if (
            port.get('adapterOn') != adapter_on
            or port.get('adapterSide') != adapter_side
        ):
            raise ValueError(
                f'SysML port {name} adapter mismatch: '
                f'expected {adapter_on}/{adapter_side}'
            )
    usages = _usages_by_name(doc)
    expected = expected_usage_ids(
        order,
        order_id=order_id,
        function=function,
        structure=structure,
        cats_home=cats_home,
    )
    for role in USAGE_ROLES:
        usage = usages.get(role)
        if usage is None:
            raise ValueError(f'SysML missing usage: {role}')
        want = expected.get(role)
        if not want:
            raise ValueError(f'SysML missing contentId for {role}')
        got = usage.get('contentId')
        if not isinstance(got, str) or not got.strip():
            raise ValueError(f'SysML missing contentId for {role}')
        if not is_ni_or_digest(got):
            raise ValueError(f'SysML {role} contentId is not ni:/digest: {got!r}')
        got_ni = equality_id(got)
        if got_ni != want:
            raise ValueError(
                f'SysML stale {role} contentId: compiled {got_ni} != order {want}'
            )
        if fetch is not None:
            fetch(got_ni)
