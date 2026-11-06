"""BOM projectors. Read envelopes; put SPDX / CDX / DCAT into CAS.

``project_*`` do not change Order, Invoice, or ``build_execution_bom``.
``attach_runtime_sbom`` is the P3 Invoice stem writer (Executor only).
``attach_ebom_stems`` is the P4 Order stem writer (mint / ``link*``).
``project_sysml_quantum`` is the P5 SysML v2 eBOM view (CAS only; no stem).
``project_data_lot`` mints a P6 data-contract spec node and cites it on DCAT.
``project_allocate_view`` is the P7 allocate join (CAS only; no stem).
"""
from __future__ import annotations

import json
import logging
import os
import re
import tomllib
from typing import Any

from cats.network.bom.documents import (
    FIXED_CREATED,
    allocate_view,
    cdx_component_from_syft_artifact,
    cdx_oci_component,
    cyclonedx_16,
    data_contract,
    dataset_spdx,
    dcat_catalog,
    software_spdx,
)
from cats.network.bom.read import (
    data_stages_from_invoice,
    fetch_key,
    from_flat_or_fetch,
    function_from_order,
    invoice_uri_from_response,
    order_from_invoice,
    require_ni,
    seed_from_invoice,
    stem_id,
    stem_uri,
    structure_as_executed_from_invoice,
    structure_from_order,
)
from cats.network.bom.syft import docker_image_digest, run_syft
from cats.network.bom.sysml import quantum_sysml
from cats.network.cas.content_ref import set_ref
from cats.network.cas.digest import is_ni_or_digest
from cats.network.cas.manifest import is_directory_manifest

logger = logging.getLogger(__name__)

MEDIA_SPDX = 'application/ld+json'
MEDIA_DCAT = 'application/ld+json'
MEDIA_SYSML = 'application/ld+json'
MEDIA_CDX = 'application/vnd.cyclonedx+json'
MEDIA_SYFT = 'application/vnd.syft+json'
_SBOM_TRUTHY = frozenset({'1', 'true', 'yes', 'on'})


def cats_sbom_enabled() -> bool:
    """``CATS_SBOM`` on when ``1`` / ``true`` / ``yes`` / ``on`` (case-insensitive)."""
    return os.environ.get('CATS_SBOM', '').strip().lower() in _SBOM_TRUTHY

_IMAGE_LINE = re.compile(r'^\s*image:\s*[\'\"]?([^\s\'\"#]+)', re.MULTILINE)
_KIND_NODE = re.compile(
    r'default\s*=\s*[\'\"](kindest/node:[^\'\"]+)[\'\"]'
)
_RAY_TAG = re.compile(
    r'variable\s+"ray_image_tag"[\s\S]*?default\s*=\s*[\'\"]([^\'\"]+)[\'\"]'
)
_SCAN_NAMES = frozenset(
    {'variables.tf', 'minio_durable_compose.yaml', 'minio_scratch_compose.yaml'}
)


def put_projection(mesh: Any, obj: dict[str, Any], *, media_type: str) -> str:
    """CAS put with sorted JSON (do not use ``ContentMesh.put_json``)."""
    payload = (json.dumps(obj, sort_keys=True) + '\n').encode('utf-8')
    return mesh.put_bytes(payload, media_type=media_type)


def make_fetch(mesh: Any):
    """JSON fetch via mesh ``cat``, resolving HTTP locators to local ``ni:``."""

    cats_home = getattr(mesh, 'CATS_HOME', None)

    def fetch(token: str) -> Any:
        key = fetch_key(token, cats_home=cats_home)
        raw = mesh.cat(key)
        return json.loads(raw)

    return fetch


def _fetch_bytes(mesh: Any, token: str) -> bytes:
    cats_home = getattr(mesh, 'CATS_HOME', None)
    key = fetch_key(token, cats_home=cats_home)
    cat_obj = getattr(mesh, 'catObj', None)
    if callable(cat_obj):
        return bytes(cat_obj(key))
    return mesh.cat(key).encode('utf-8')


def parse_uv_lock(data: bytes | str) -> list[tuple[str, str]]:
    """``(name, version)`` from a uv.lock TOML document. Invalid lock → []."""
    if isinstance(data, bytes):
        text = data.decode('utf-8')
    else:
        text = data
    try:
        doc = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        logger.info('uv.lock parse skipped: %s', exc)
        return []
    packages = doc.get('package') or []
    out: list[tuple[str, str]] = []
    if not isinstance(packages, list):
        return []
    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        name = pkg.get('name')
        version = pkg.get('version')
        if isinstance(name, str) and name.strip() and isinstance(version, str) and version.strip():
            out.append((name.strip(), version.strip()))
    return sorted(out)


def _manifest_files(
    manifest: dict[str, Any],
    *,
    prefix: str,
) -> list[tuple[str, str]]:
    if not is_directory_manifest(manifest):
        return []
    files: list[tuple[str, str]] = []
    entries = manifest.get('entries') or {}
    for rel, content_id in entries.items():
        if not isinstance(rel, str) or not isinstance(content_id, str):
            continue
        if not is_ni_or_digest(content_id):
            continue
        name = f'{prefix}/{rel}' if prefix else rel
        files.append((name, content_id))
    return files


def _uv_lock_from_manifests(
    mesh: Any,
    manifests: list[dict[str, Any]],
    *,
    uv_lock: bytes | str | None,
) -> list[tuple[str, str]]:
    if uv_lock is not None:
        return parse_uv_lock(uv_lock)
    for manifest in manifests:
        if not is_directory_manifest(manifest):
            continue
        entries = manifest.get('entries') or {}
        lock_id = entries.get('uv.lock')
        if not isinstance(lock_id, str) or not lock_id.strip():
            continue
        try:
            return parse_uv_lock(_fetch_bytes(mesh, lock_id))
        except Exception as exc:
            logger.info('uv.lock fetch skipped: %s', exc)
            return []
    return []


def project_function_source(
    function: dict[str, Any],
    mesh: Any,
    *,
    function_id: str,
    uv_lock: bytes | str | None = None,
    created: str = FIXED_CREATED,
    cats_home: str | None = None,
) -> str:
    """SPDX 3 software of Function source trees (+ optional uv.lock packages)."""
    fetch = make_fetch(mesh)
    home = cats_home if cats_home is not None else getattr(mesh, 'CATS_HOME', None)
    subject = require_ni(function_id, label='function_id')
    files: list[tuple[str, str]] = []
    manifests: list[dict[str, Any]] = []
    for stem, prefix in (
        ('process_source', 'process'),
        ('infrafunction_source', 'infrafunction'),
    ):
        token = stem_uri(function, stem) or stem_id(function, stem, cats_home=home)
        if not token:
            continue
        payload = fetch(token)
        if isinstance(payload, dict):
            manifests.append(payload)
            files.extend(_manifest_files(payload, prefix=prefix))
    pypi = _uv_lock_from_manifests(mesh, manifests, uv_lock=uv_lock)
    doc = software_spdx(
        kind='function',
        subject_id=subject,
        files=files,
        pypi=pypi,
        created=created,
    )
    return put_projection(mesh, doc, media_type=MEDIA_SPDX)


def project_structure_source(
    structure: dict[str, Any],
    mesh: Any,
    *,
    structure_id: str,
    created: str = FIXED_CREATED,
    cats_home: str | None = None,
) -> str:
    """SPDX 3 software of Structure as-Code ``root`` / ``plant`` / ``infrastructure``."""
    fetch = make_fetch(mesh)
    home = cats_home if cats_home is not None else getattr(mesh, 'CATS_HOME', None)
    subject = require_ni(structure_id, label='structure_id')
    files: list[tuple[str, str]] = []
    for stem in ('root', 'plant', 'infrastructure'):
        token = stem_uri(structure, stem) or stem_id(structure, stem, cats_home=home)
        if not token:
            continue
        payload = fetch(token)
        if isinstance(payload, dict):
            files.extend(_manifest_files(payload, prefix=stem))
    doc = software_spdx(
        kind='structure',
        subject_id=subject,
        files=files,
        created=created,
    )
    return put_projection(mesh, doc, media_type=MEDIA_SPDX)


def _oci_name(ref: str) -> str:
    base = ref.split('@', 1)[0].strip()
    if base.startswith('docker.io/'):
        base = base[len('docker.io/') :]
    if ':' in base.rsplit('/', 1)[-1]:
        base = base.rsplit(':', 1)[0]
    return base


def collect_image_refs(
    mesh: Any,
    structure: dict[str, Any] | None,
    *,
    cats_home: str | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    """Image refs from as-Code compose/tf files plus optional ``extra``."""
    seen: set[str] = set()
    out: list[str] = []

    def add(ref: str) -> None:
        token = ref.strip()
        if token and token not in seen:
            seen.add(token)
            out.append(token)

    for ref in extra or []:
        add(ref)
    if not isinstance(structure, dict):
        return out
    fetch = make_fetch(mesh)
    home = cats_home if cats_home is not None else getattr(mesh, 'CATS_HOME', None)
    for stem in ('plant', 'infrastructure', 'root'):
        token = stem_uri(structure, stem) or stem_id(structure, stem, cats_home=home)
        if not token:
            continue
        try:
            manifest = fetch(token)
        except Exception as exc:
            logger.info('image-ref manifest skip for %s: %s', stem, exc)
            continue
        if not is_directory_manifest(manifest):
            continue
        for rel, file_id in (manifest.get('entries') or {}).items():
            name = str(rel).rsplit('/', 1)[-1]
            if name not in _SCAN_NAMES and not str(rel).endswith(('.yaml', '.yml', '.tf')):
                continue
            if not isinstance(file_id, str):
                continue
            try:
                text = _fetch_bytes(mesh, file_id).decode('utf-8')
            except Exception as exc:
                logger.info('image-ref file skip %s: %s', rel, exc)
                continue
            for match in _IMAGE_LINE.finditer(text):
                add(match.group(1))
            for match in _KIND_NODE.finditer(text):
                add(match.group(1))
            ray = _RAY_TAG.search(text)
            if ray:
                add(f'rayproject/ray:{ray.group(1)}')
    return out


def project_structure_runtime(
    structure_as_executed: dict[str, Any] | None,
    mesh: Any,
    *,
    structure_as_executed_id: str,
    structure: dict[str, Any] | None = None,
    image_refs: list[str] | None = None,
    syft_bin: str | None = None,
    created: str = FIXED_CREATED,
    cats_home: str | None = None,
) -> dict[str, Any]:
    """Syft JSON (optional) then CycloneDX 1.6 of Structure runtime images.

    Always emits CDX. Syft missing / failing is skip + log. Wall time is in
    the return dict only — not in CAS bytes.
    """
    _ = structure_as_executed  # SAE snapshot has no OCI digests today.
    subject = require_ni(
        structure_as_executed_id, label='structure_as_executed_id'
    )
    refs = collect_image_refs(
        mesh, structure, cats_home=cats_home, extra=image_refs
    )
    components: list[dict[str, Any]] = []
    syft_docs: list[dict[str, Any]] = []
    elapsed_total = 0.0
    syft_ran = False
    for ref in refs:
        digest = docker_image_digest(ref)
        if digest:
            components.append(cdx_oci_component(_oci_name(ref), digest))
        doc, elapsed = run_syft(ref, syft_bin=syft_bin)
        if elapsed is not None:
            elapsed_total += elapsed
            syft_ran = True
        if doc is None:
            continue
        syft_docs.append(doc)
        for artifact in doc.get('artifacts') or []:
            component = cdx_component_from_syft_artifact(artifact)
            if component is not None:
                components.append(component)
    syft_id = None
    if syft_docs:
        original = syft_docs[0] if len(syft_docs) == 1 else {'documents': syft_docs}
        syft_id = put_projection(mesh, original, media_type=MEDIA_SYFT)
    cdx = cyclonedx_16(
        subject_id=subject, components=components, created=created
    )
    cdx_id = put_projection(mesh, cdx, media_type=MEDIA_CDX)
    out: dict[str, Any] = {'runtime_cdx': cdx_id, 'runtime_syft': syft_id}
    if syft_ran:
        out['syft_elapsed'] = elapsed_total
    return out


def _stage_lots(
    invoice: dict[str, Any],
    mesh: Any,
    *,
    cats_home: str | None = None,
) -> list[tuple[str, str, str | None]]:
    fetch = make_fetch(mesh)
    home = cats_home if cats_home is not None else getattr(mesh, 'CATS_HOME', None)
    lots: list[tuple[str, str, str | None]] = []
    stages = data_stages_from_invoice(invoice, fetch, cats_home=home) or {}
    for stem in ('egressed_data', 'integrated_data', 'ingressed_data'):
        token = stem_id(stages, stem, cats_home=home)
        if not token or not is_ni_or_digest(token):
            continue
        lots.append((stem, token, stem_uri(stages, stem)))
    seed = seed_from_invoice(invoice, fetch, cats_home=home)
    seed_id = stem_id(invoice, 'seed', cats_home=home)
    if seed is not None and seed_id and is_ni_or_digest(seed_id):
        lots.append(('seed', seed_id, stem_uri(invoice, 'seed')))
    return lots


def _input_lot_subject(
    invoice: dict[str, Any],
    mesh: Any,
    *,
    invoice_id: str,
    cats_home: str | None = None,
) -> str:
    """Input-lot ``ni:`` from Order's input Invoice ``data``; else Invoice ``ni:``."""
    fallback = require_ni(invoice_id, label='invoice_id')
    fetch = make_fetch(mesh)
    home = cats_home if cats_home is not None else getattr(mesh, 'CATS_HOME', None)
    order = order_from_invoice(invoice, fetch, cats_home=home)
    if not isinstance(order, dict):
        return fallback
    input_invoice = from_flat_or_fetch(order, 'invoice', fetch, cats_home=home)
    if not isinstance(input_invoice, dict):
        return fallback
    data_id = stem_id(input_invoice, 'data', cats_home=home)
    if not data_id or not is_ni_or_digest(data_id):
        return fallback
    return require_ni(data_id, label='data_id')


def project_data_lot(
    invoice: dict[str, Any],
    mesh: Any,
    *,
    invoice_id: str,
    created: str = FIXED_CREATED,
    cats_home: str | None = None,
) -> dict[str, str]:
    """DCAT 3 Catalog + SPDX 3 dataset of Invoice stages / seed.

    Always mints a thin data-contract spec node keyed by the Order input-lot
    ``ni:`` (Invoice ``ni:`` fallback) and cites its ``@id`` on the DCAT
    catalog (``dct:conformsTo``). Does not mint an envelope stem.
    """
    catalog_subject = require_ni(invoice_id, label='invoice_id')
    contract_subject = _input_lot_subject(
        invoice, mesh, invoice_id=invoice_id, cats_home=cats_home
    )
    lots = _stage_lots(invoice, mesh, cats_home=cats_home)
    contract = data_contract(subject_id=contract_subject, created=created)
    contract_id = put_projection(mesh, contract, media_type=MEDIA_DCAT)
    dcat = dcat_catalog(
        subject_id=catalog_subject,
        datasets=lots,
        created=created,
        conforms_to=contract['@id'],
    )
    spdx = dataset_spdx(subject_id=catalog_subject, datasets=lots, created=created)
    return {
        'data_contract': contract_id,
        'data_dcat': put_projection(mesh, dcat, media_type=MEDIA_DCAT),
        'data_spdx': put_projection(mesh, spdx, media_type=MEDIA_SPDX),
    }


def project_input_data(
    mesh: Any,
    *,
    data_id: str,
    data_uri: str | None = None,
    created: str = FIXED_CREATED,
    conforms_to: str | None = None,
) -> dict[str, str]:
    """DCAT 3 + SPDX 3 dataset of one Order input lot (no Invoice stages).

    Default DCAT has no ``dct:conformsTo`` (P4 remint hashes stay put).
    Pass ``conforms_to`` only to prove nest keys survive a cite.
    """
    subject = require_ni(data_id, label='data_id')
    uri = data_uri.strip() if isinstance(data_uri, str) and data_uri.strip() else None
    lots = [('input_data', subject, uri)]
    dcat = dcat_catalog(
        subject_id=subject,
        datasets=lots,
        created=created,
        conforms_to=conforms_to,
    )
    spdx = dataset_spdx(subject_id=subject, datasets=lots, created=created)
    return {
        'data_dcat': put_projection(mesh, dcat, media_type=MEDIA_DCAT),
        'data_spdx': put_projection(mesh, spdx, media_type=MEDIA_SPDX),
    }


def project_sysml_quantum(
    order: dict[str, Any],
    mesh: Any,
    *,
    order_id: str,
    function: dict[str, Any] | None = None,
    structure: dict[str, Any] | None = None,
    created: str = FIXED_CREATED,
    cats_home: str | None = None,
) -> str:
    """SysML v2 JSON-LD of the Order Quantum (CAS only; does not mint a stem)."""
    fetch = make_fetch(mesh)
    home = cats_home if cats_home is not None else getattr(mesh, 'CATS_HOME', None)
    fn = (
        function
        if isinstance(function, dict)
        else (function_from_order(order, fetch, cats_home=home) or {})
    )
    st = (
        structure
        if isinstance(structure, dict)
        else (structure_from_order(order, fetch, cats_home=home) or {})
    )
    doc = quantum_sysml(
        order_id=order_id,
        function_id=stem_id(order, 'function', cats_home=home),
        process_id=stem_id(fn, 'process', cats_home=home),
        infrafunction_id=stem_id(fn, 'infrafunction', cats_home=home),
        structure_id=stem_id(order, 'structure', cats_home=home),
        plant_id=stem_id(st, 'plant', cats_home=home),
        infrastructure_id=stem_id(st, 'infrastructure', cats_home=home),
        created=created,
    )
    return put_projection(mesh, doc, media_type=MEDIA_SYSML)


def project_allocate_view(
    sysml_doc: dict[str, Any],
    contract_doc: dict[str, Any],
    mesh: Any,
    *,
    created: str = FIXED_CREATED,
) -> str:
    """Allocate-view JSON-LD (CAS only; does not mint a stem or mutate SysML)."""
    doc = allocate_view(
        sysml_doc=sysml_doc, contract_doc=contract_doc, created=created
    )
    return put_projection(mesh, doc, media_type=MEDIA_DCAT)


def put_input_data_sbom_nest(mesh: Any, lots: dict[str, Any]) -> str:
    """CAS JSON nest citing DCAT + SPDX dataset (refs only)."""
    dcat_id = lots.get('data_dcat')
    spdx_id = lots.get('data_spdx')
    if not isinstance(dcat_id, str) or not dcat_id.strip():
        raise ValueError('data_dcat is required for input_data_sbom nest')
    if not isinstance(spdx_id, str) or not spdx_id.strip():
        raise ValueError('data_spdx is required for input_data_sbom nest')
    nest: dict[str, Any] = {}
    set_ref(nest, 'dcat', dcat_id)
    set_ref(nest, 'spdx', spdx_id)
    return mesh.put_json(nest)


EBOM_STEMS = ('function_sbom', 'structure_sbom', 'input_data_sbom')


def strip_ebom_stems(order: dict[str, Any]) -> None:
    """Drop eBOM sbom ``*_uri`` / leftover ``*_cid`` (do not silent-carry)."""
    if not isinstance(order, dict):
        return
    for stem in EBOM_STEMS:
        order.pop(f'{stem}_uri', None)
        order.pop(f'{stem}_cid', None)


def attach_ebom_stems(
    order: dict[str, Any],
    mesh: Any,
    *,
    function: dict[str, Any] | None,
    function_id: str,
    structure: dict[str, Any] | None,
    structure_id: str,
    data_id: str,
    data_uri: str | None = None,
    uv_lock: bytes | str | None = None,
) -> dict[str, str] | None:
    """P4: ``set_ref`` Order eBOM stems when ``CATS_SBOM`` is on.

    Returns the three ``ni:`` ids or ``None`` when the flag is off. Does not
    embed SPDX / DCAT bytes on the Order.
    """
    if not cats_sbom_enabled():
        return None
    function_spdx = project_function_source(
        function or {}, mesh, function_id=function_id, uv_lock=uv_lock
    )
    structure_spdx = project_structure_source(
        structure or {}, mesh, structure_id=structure_id
    )
    conforms_to = None
    if is_ni_or_digest(data_id):
        contract = data_contract(subject_id=require_ni(data_id, label='data_id'))
        put_projection(mesh, contract, media_type=MEDIA_DCAT)
        conforms_to = contract['@id']
    lots = project_input_data(
        mesh,
        data_id=data_id,
        data_uri=data_uri,
        conforms_to=conforms_to,
    )
    nest_id = put_input_data_sbom_nest(mesh, lots)
    set_ref(order, 'function_sbom', function_spdx)
    set_ref(order, 'structure_sbom', structure_spdx)
    set_ref(order, 'input_data_sbom', nest_id)
    return {
        'function_sbom': function_spdx,
        'structure_sbom': structure_spdx,
        'input_data_sbom': nest_id,
    }


def project_bom(
    cat_response: dict[str, Any],
    mesh: Any,
    *,
    record: dict[str, Any] | None = None,
    uv_lock: bytes | str | None = None,
    image_refs: list[str] | None = None,
    syft_bin: str | None = None,
    created: str = FIXED_CREATED,
) -> dict[str, Any]:
    """Project P2 documents plus the P6 data-contract spec node.

    Returns ``ni:`` ids (and optional ``syft_elapsed``). Does not mutate
    ``cat_response`` / Order / Invoice.
    """
    cats_home = getattr(mesh, 'CATS_HOME', None)
    fetch = make_fetch(mesh)
    invoice_uri = invoice_uri_from_response(cat_response, record)
    if not invoice_uri:
        raise ValueError('signed bom.invoice_uri / registry invoice locator required')
    invoice = fetch(invoice_uri)
    if not isinstance(invoice, dict):
        raise ValueError('Invoice is not a JSON object')
    invoice_id = fetch_key(invoice_uri, cats_home=cats_home)
    if not is_ni_or_digest(str(invoice_id)):
        # Prefer digest from the locator path; fall back to mesh-resolved id.
        invoice_id = require_ni(str(invoice_id), label='invoice_id')
    else:
        invoice_id = require_ni(str(invoice_id), label='invoice_id')

    order = order_from_invoice(invoice, fetch, cats_home=cats_home)
    if not isinstance(order, dict):
        raise ValueError('Order missing on Invoice')
    function = function_from_order(order, fetch, cats_home=cats_home) or {}
    structure = structure_from_order(order, fetch, cats_home=cats_home) or {}
    sae = structure_as_executed_from_invoice(invoice, fetch, cats_home=cats_home)

    function_id = stem_id(order, 'function', cats_home=cats_home)
    structure_id = stem_id(order, 'structure', cats_home=cats_home)
    sae_id = stem_id(invoice, 'structure_as_executed', cats_home=cats_home)
    if not function_id:
        raise ValueError('Order missing function_uri')
    if not structure_id:
        raise ValueError('Order missing structure_uri')
    if not sae_id:
        raise ValueError('Invoice missing structure_as_executed_uri')

    function_spdx = project_function_source(
        function,
        mesh,
        function_id=function_id,
        uv_lock=uv_lock,
        created=created,
        cats_home=cats_home,
    )
    structure_spdx = project_structure_source(
        structure,
        mesh,
        structure_id=structure_id,
        created=created,
        cats_home=cats_home,
    )
    runtime = project_structure_runtime(
        sae,
        mesh,
        structure_as_executed_id=sae_id,
        structure=structure,
        image_refs=image_refs,
        syft_bin=syft_bin,
        created=created,
        cats_home=cats_home,
    )
    lots = project_data_lot(
        invoice,
        mesh,
        invoice_id=invoice_id,
        created=created,
        cats_home=cats_home,
    )
    result: dict[str, Any] = {
        'function_spdx': function_spdx,
        'structure_spdx': structure_spdx,
        'runtime_cdx': runtime['runtime_cdx'],
        'runtime_syft': runtime.get('runtime_syft'),
        'data_contract': lots['data_contract'],
        'data_dcat': lots['data_dcat'],
        'data_spdx': lots['data_spdx'],
    }
    if 'syft_elapsed' in runtime:
        result['syft_elapsed'] = runtime['syft_elapsed']
    return result


def put_runtime_sbom_nest(mesh: Any, runtime: dict[str, Any]) -> str:
    """CAS JSON nest citing CycloneDX and optional Syft (refs only)."""
    cdx_id = runtime.get('runtime_cdx')
    if not isinstance(cdx_id, str) or not cdx_id.strip():
        raise ValueError('runtime_cdx is required for runtime_sbom nest')
    nest: dict[str, Any] = {}
    set_ref(nest, 'cyclonedx', cdx_id)
    syft_id = runtime.get('runtime_syft')
    if isinstance(syft_id, str) and syft_id.strip():
        set_ref(nest, 'syft', syft_id)
    return mesh.put_json(nest)


def attach_runtime_sbom(
    invoice: dict[str, Any],
    mesh: Any,
    *,
    structure_as_executed: dict[str, Any] | None,
    structure_as_executed_id: str,
    structure: dict[str, Any] | None = None,
    image_refs: list[str] | None = None,
    syft_bin: str | None = None,
) -> str | None:
    """P3: ``set_ref(invoice, 'runtime_sbom', nest)`` when ``CATS_SBOM`` is on.

    Returns the nest ``ni:`` or ``None`` when the flag is off. Does not embed
    SPDX / CDX / Syft bytes on the Invoice.
    """
    if not cats_sbom_enabled():
        return None
    runtime = project_structure_runtime(
        structure_as_executed,
        mesh,
        structure_as_executed_id=structure_as_executed_id,
        structure=structure,
        image_refs=image_refs,
        syft_bin=syft_bin,
    )
    nest_id = put_runtime_sbom_nest(mesh, runtime)
    set_ref(invoice, 'runtime_sbom', nest_id)
    return nest_id
