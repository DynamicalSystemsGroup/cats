"""Hand-rolled SPDX 3 / CycloneDX 1.6 / DCAT 3 builders. No envelope I/O.

Document ``@id`` is a subject URN — never an ExecutionBom ``content_id``.
Timestamps default to a fixed UTC instant so re-runs are byte-stable.
"""
from __future__ import annotations

import uuid
from typing import Any

from cats.network.bom.purl import fru_purl
from cats.network.cas.content_ref import equality_id, is_http_uri
from cats.network.cas.digest import from_ni, is_ni_or_digest

FIXED_CREATED = '1970-01-01T00:00:00Z'
_SPDX_CONTEXT = 'https://spdx.org/rdf/3.0.1/spdx-context.jsonld'
_CDX_UUID_NS = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')


def projection_urn(kind: str, subject_ni: str) -> str:
    """Stable document id: ``urn:cats:projection:{kind}:{subject_ni}``."""
    return f'urn:cats:projection:{kind}:{subject_ni}'


def _ni(content_id: str) -> str:
    if is_http_uri(content_id) or not is_ni_or_digest(content_id):
        raise ValueError(f'expected ni: or hex, got {content_id!r}')
    return equality_id(content_id)


def _hex(content_id: str) -> str:
    return from_ni(_ni(content_id))


def _hash(content_id: str) -> dict[str, str]:
    return {
        '@type': 'Hash',
        'algorithm': 'sha256',
        'hashValue': _hex(content_id),
    }


def _creation_info(created: str) -> dict[str, Any]:
    return {
        '@type': 'CreationInfo',
        'created': created,
        'createdBy': ['urn:cats:projector:p2'],
        'specVersion': '3.0.1',
    }


def software_spdx(
    *,
    kind: str,
    subject_id: str,
    files: list[tuple[str, str]],
    pypi: list[tuple[str, str]] | None = None,
    created: str = FIXED_CREATED,
) -> dict[str, Any]:
    """SPDX 3 software JSON-LD of a Function or Structure as-Code tree."""
    subject = _ni(subject_id)
    role = 'function' if kind == 'function' else 'structure'
    root_purl = fru_purl(role, subject)
    root_id = f'{projection_urn(kind, subject)}#root'
    elements: list[dict[str, Any]] = [
        {
            '@id': root_id,
            '@type': 'software_Package',
            'name': role,
            'software_packageUrl': root_purl,
            'verifiedUsing': [_hash(subject)],
        }
    ]
    for rel, file_id in sorted(files, key=lambda item: item[0]):
        file_ni = _ni(file_id)
        elements.append(
            {
                '@id': f'{projection_urn(kind, subject)}#file:{rel}',
                '@type': 'software_File',
                'name': rel,
                'verifiedUsing': [_hash(file_ni)],
            }
        )
    for name, version in sorted(pypi or [], key=lambda item: (item[0], item[1])):
        elements.append(
            {
                '@id': f'{projection_urn(kind, subject)}#pypi:{name}@{version}',
                '@type': 'software_Package',
                'name': name,
                'software_packageUrl': fru_purl('pypi', name=name, version=version),
            }
        )
    elements.sort(key=lambda item: str(item.get('@id') or ''))
    return {
        '@context': _SPDX_CONTEXT,
        '@id': projection_urn(kind, subject),
        '@type': 'software_Sbom',
        'creationInfo': _creation_info(created),
        'element': elements,
        'profileConformance': ['core', 'software'],
        'rootElement': [root_id],
    }


def dataset_spdx(
    *,
    subject_id: str,
    datasets: list[tuple[str, str, str | None]],
    created: str = FIXED_CREATED,
) -> dict[str, Any]:
    """SPDX 3 dataset profile of Invoice stages / seed (no stage-byte expansion)."""
    subject = _ni(subject_id)
    elements: list[dict[str, Any]] = []
    root_ids: list[str] = []
    for name, content_id, uri in sorted(datasets, key=lambda item: item[0]):
        lot = _ni(content_id)
        elem_id = uri if (isinstance(uri, str) and uri.strip()) else (
            f'{projection_urn("dataset", subject)}#{name}'
        )
        root_ids.append(elem_id)
        elements.append(
            {
                '@id': elem_id,
                '@type': 'dataset_Dataset',
                'name': name,
                'software_packageUrl': fru_purl('dataset', lot),
                'verifiedUsing': [_hash(lot)],
            }
        )
    elements.sort(key=lambda item: str(item.get('@id') or ''))
    return {
        '@context': _SPDX_CONTEXT,
        '@id': projection_urn('dataset', subject),
        '@type': 'software_Sbom',
        'creationInfo': _creation_info(created),
        'element': elements,
        'profileConformance': ['core', 'dataset'],
        'rootElement': sorted(root_ids),
    }


_ODCS_CONTEXT = {
    'odcs': 'https://bitol-io.github.io/open-data-contract-standard#',
    'dct': 'http://purl.org/dc/terms/',
    'cats': 'https://cats.dynamicalsystemsgroup.com/ns#',
}

CONTRACT_CLAUSES = (
    ('egress', 'Process.egress', 'schema'),
    ('freshness', 'freshness', 'sla'),
    ('privacy', 'privacy', 'risk'),
)


def data_contract(
    *,
    subject_id: str,
    created: str = FIXED_CREATED,
) -> dict[str, Any]:
    """Thin ODCS-shaped spec node. Not Bitol YAML; Factory does not read this."""
    subject = _ni(subject_id)
    doc_id = projection_urn('odcs', subject)
    clauses = [
        {
            '@id': f'{doc_id}#{name}',
            'dct:title': name,
            'cats:allocatesTo': allocates_to,
            'cats:kind': kind,
            'cats:enforced': False,
        }
        for name, allocates_to, kind in CONTRACT_CLAUSES
    ]
    return {
        '@context': _ODCS_CONTEXT,
        '@id': doc_id,
        '@type': 'odcs:DataContract',
        'dct:title': 'cats-data-lot',
        'odcs:version': '1.0.0',
        'odcs:status': 'draft',
        'cats:subject': subject,
        'cats:clauses': clauses,
        'cats:createdBy': 'urn:cats:projector:p6',
        'dct:issued': created,
    }


_ALLOCATE_CONTEXT = {
    'dct': 'http://purl.org/dc/terms/',
    'cats': 'https://cats.dynamicalsystemsgroup.com/ns#',
}


def _sysml_usage_id(sysml_doc: dict[str, Any], name: str) -> str | None:
    owned = sysml_doc.get('ownedElement')
    if not isinstance(owned, list):
        return None
    for item in owned:
        if not isinstance(item, dict):
            continue
        if item.get('@type') != 'sysml:PartUsage':
            continue
        if item.get('name') == name:
            ident = item.get('@id')
            return ident if isinstance(ident, str) and ident.strip() else None
    return None


def _order_ni_from_sysml(sysml_doc: dict[str, Any]) -> str:
    owned = sysml_doc.get('ownedElement')
    if isinstance(owned, list):
        for item in owned:
            if not isinstance(item, dict):
                continue
            if item.get('name') != 'ArchitecturalQuantum':
                continue
            content_id = item.get('contentId')
            if isinstance(content_id, str) and content_id.strip():
                return _ni(content_id)
    doc_id = sysml_doc.get('@id')
    prefix = 'urn:cats:projection:sysml:'
    if isinstance(doc_id, str) and doc_id.startswith(prefix):
        return _ni(doc_id[len(prefix) :])
    raise ValueError('sysml_doc missing ArchitecturalQuantum contentId')


def allocate_view(
    *,
    sysml_doc: dict[str, Any],
    contract_doc: dict[str, Any],
    created: str = FIXED_CREATED,
) -> dict[str, Any]:
    """Clause → P5 usage / concern, plus inverse. Does not mutate SysML."""
    if not isinstance(sysml_doc, dict):
        raise ValueError('sysml_doc is required')
    if not isinstance(contract_doc, dict):
        raise ValueError('contract_doc is required')
    order_ni = _order_ni_from_sysml(sysml_doc)
    doc_id = projection_urn('allocate', order_ni)
    sysml_id = sysml_doc.get('@id')
    if not isinstance(sysml_id, str) or not sysml_id.strip():
        sysml_id = projection_urn('sysml', order_ni)
    process_usage = _sysml_usage_id(sysml_doc, 'Process') or f'{sysml_id}#usage:Process'
    contract_id = contract_doc.get('@id')
    if not isinstance(contract_id, str) or not contract_id.strip():
        raise ValueError('contract_doc missing @id')
    by_title = {
        clause.get('dct:title'): clause
        for clause in (contract_doc.get('cats:clauses') or [])
        if isinstance(clause, dict)
    }
    edges: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    for name, _allocates_to, kind in CONTRACT_CLAUSES:
        clause = by_title.get(name) or {}
        clause_id = clause.get('@id') or f'{contract_id}#{name}'
        target = process_usage if name == 'egress' else f'urn:cats:concern:{name}'
        edges.append(
            {
                '@id': clause_id,
                'cats:allocatesTo': target,
                'cats:kind': kind,
                'cats:enforced': False,
            }
        )
        targets.append(
            {
                '@id': target,
                'cats:allocatedFrom': clause_id,
                'cats:clause': clause_id,
            }
        )
    return {
        '@context': dict(_ALLOCATE_CONTEXT),
        '@id': doc_id,
        '@type': 'cats:AllocateView',
        'cats:subject': order_ni,
        'cats:contract': contract_id,
        'cats:createdBy': 'urn:cats:projector:p7',
        'cats:edges': edges,
        'cats:targets': targets,
        'dct:issued': created,
    }


def dcat_catalog(
    *,
    subject_id: str,
    datasets: list[tuple[str, str, str | None]],
    created: str = FIXED_CREATED,
    conforms_to: str | None = None,
) -> dict[str, Any]:
    """DCAT 3 Catalog: ``@id`` = stage ``*_uri``; checksum = ``contentId``.

    ``conforms_to`` is a contract document ``@id`` (URN), not a CAS ``ni:``.
    """
    subject = _ni(subject_id)
    entries: list[dict[str, Any]] = []
    for name, content_id, uri in sorted(datasets, key=lambda item: item[0]):
        lot = _ni(content_id)
        dataset_id = uri if (isinstance(uri, str) and uri.strip()) else (
            f'{projection_urn("dcat", subject)}#{name}'
        )
        entry: dict[str, Any] = {
            '@id': dataset_id,
            '@type': 'dcat:Dataset',
            'dct:identifier': lot,
            'dct:title': name,
            'spdx:checksum': {
                'spdx:algorithm': 'checksumAlgorithm_sha256',
                'spdx:checksumValue': _hex(lot),
            },
        }
        if isinstance(uri, str) and uri.strip():
            entry['dcat:distribution'] = [
                {
                    '@type': 'dcat:Distribution',
                    'dcat:downloadURL': uri.strip(),
                    'dcat:mediaType': 'application/json',
                }
            ]
        entries.append(entry)
    catalog: dict[str, Any] = {
        '@context': {
            'dcat': 'http://www.w3.org/ns/dcat#',
            'dct': 'http://purl.org/dc/terms/',
            'spdx': 'http://spdx.org/rdf/terms#',
        },
        '@id': projection_urn('dcat', subject),
        '@type': 'dcat:Catalog',
        'dcat:dataset': entries,
        'dct:issued': created,
    }
    if isinstance(conforms_to, str) and conforms_to.strip():
        catalog['dct:conformsTo'] = conforms_to.strip()
    return catalog


def cyclonedx_16(
    *,
    subject_id: str,
    components: list[dict[str, Any]],
    created: str = FIXED_CREATED,
) -> dict[str, Any]:
    """CycloneDX 1.6 JSON of Structure runtime (images / Syft artifacts)."""
    subject = _ni(subject_id)
    serial = f'urn:uuid:{uuid.uuid5(_CDX_UUID_NS, subject)}'
    ordered = sorted(
        components,
        key=lambda item: (
            str(item.get('purl') or ''),
            str(item.get('name') or ''),
            str(item.get('version') or ''),
        ),
    )
    return {
        'bomFormat': 'CycloneDX',
        'specVersion': '1.6',
        'serialNumber': serial,
        'version': 1,
        'metadata': {
            'timestamp': created,
            'component': {
                'type': 'platform',
                'name': 'structure_as_executed',
                'purl': fru_purl('structure', subject),
            },
        },
        'components': ordered,
    }


def cdx_oci_component(name: str, digest_hex: str) -> dict[str, Any]:
    """Container component with ``pkg:oci/…@sha256:`` (digest required)."""
    hex_digest = digest_hex.strip().lower()
    if hex_digest.startswith('sha256:'):
        hex_digest = hex_digest[len('sha256:') :]
    purl = fru_purl('oci', hex_digest, name=name)
    return {
        'name': name,
        'purl': purl,
        'type': 'container',
        'version': f'sha256:{hex_digest}',
    }


def cdx_component_from_syft_artifact(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """Library component from a Syft JSON artifact (purl required)."""
    if not isinstance(artifact, dict):
        return None
    purl = artifact.get('purl')
    if not isinstance(purl, str) or not purl.strip():
        return None
    return {
        'name': str(artifact.get('name') or purl).strip(),
        'purl': purl.strip(),
        'type': 'library',
        'version': str(artifact.get('version') or ''),
    }
