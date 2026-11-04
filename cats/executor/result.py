"""Job result outside ``CATS_HOME``.

``python -m cats.executor.once`` writes this after ``run_order``. The Flask
peer does not. Deleting ``CATS_HOME`` leaves Invoice bytes and their content
ids so a later Order can cite them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cats.network.cas.content_ref import content_id_from_uri, ref_id, ref_uri
from cats.network.cas.digest import content_id_fs_key, from_ni, is_ni_or_digest, to_ni
from cats.network.cas.store import CasHttpStore


def resolve_result_dir(
    cats_home: str,
    result_dir: str | None = None,
) -> Path:
    """``CAT_RESULT_DIR``, else a sibling of ``CATS_HOME``. Never inside it."""
    raw = (result_dir or os.environ.get('CAT_RESULT_DIR') or '').strip()
    if not raw:
        raw = str(Path(cats_home).resolve().parent / 'cat-result')
    path = Path(raw).expanduser().resolve()
    home = Path(cats_home).resolve()
    if path == home or home in path.parents:
        raise RuntimeError(
            f'CAT_RESULT_DIR {path} must not be under CATS_HOME {home}'
        )
    return path


def _equality_id(value: str | None, *, cats_home: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if is_ni_or_digest(raw):
        return to_ni(from_ni(raw))
    return content_id_from_uri(raw, cats_home=cats_home)


def _copy_blob(store: CasHttpStore, dest_cas: Path, content_id: str) -> str:
    blob = store.get(content_id)
    if blob is None:
        raise RuntimeError(f'CAS content not found: {content_id}')
    key = content_id_fs_key(content_id)
    dest_cas.mkdir(parents=True, exist_ok=True)
    (dest_cas / key).write_bytes(blob)
    return key


def _ref_content_id(obj: dict, stem: str, *, cats_home: str) -> str | None:
    uri = ref_uri(obj, stem)
    return _equality_id(uri, cats_home=cats_home) or ref_id(
        obj, stem, cats_home=cats_home
    )


def _note(found: list[str], content_id: str | None) -> None:
    if content_id and content_id not in found:
        found.append(content_id)


def _note_entity(found: list[str], entity: Any, *, cats_home: str) -> None:
    if not isinstance(entity, dict):
        return
    content_id = entity.get('contentId')
    if isinstance(content_id, str) and content_id.strip():
        resolved = _equality_id(content_id, cats_home=cats_home)
        if not resolved:
            raise RuntimeError(f'CAS content not found: {content_id}')
        _note(found, resolved)
    else:
        at_id = entity.get('@id')
        if isinstance(at_id, str):
            _note(found, _equality_id(at_id, cats_home=cats_home))
    derived = entity.get('prov:wasDerivedFrom')
    if isinstance(derived, dict):
        _note_entity(found, derived, cats_home=cats_home)
    elif isinstance(derived, list):
        for item in derived:
            _note_entity(found, item, cats_home=cats_home)


def _cited_content_ids(
    bom_response: dict[str, Any],
    bom: dict,
    invoice: dict,
    invoice_id: str,
    *,
    cats_home: str,
) -> list[str]:
    """BOM bytes plus Invoice and BOM citations. Not the registry."""
    bom_id = bom_response.get('content_id')
    if not isinstance(bom_id, str) or not bom_id.strip():
        raise RuntimeError('bom_response is missing content_id')
    found = [invoice_id]
    _note(found, _equality_id(bom_id, cats_home=cats_home) or bom_id.strip())
    for stem in ('data', 'order', 'log'):
        _note(found, _ref_content_id(bom, stem, cats_home=cats_home))
    for stem in ('data', 'data_stages', 'order', 'structure_as_executed'):
        _note(found, _ref_content_id(invoice, stem, cats_home=cats_home))
    lineage = bom.get('stageLineage')
    if isinstance(lineage, list):
        for entity in lineage:
            _note_entity(found, entity, cats_home=cats_home)
    return found


def write_job_result(
    bom_response: dict[str, Any],
    *,
    cats_home: str,
    result_dir: str | None = None,
) -> Path:
    """Write ``invoice.json``, ``bom.json``, ``result.json``, and cited blobs.

    Copies the signed BOM bytes and the Invoice, ``data``, ``data_stages``,
    Order, ``log``, stage-lineage, and ``structure_as_executed`` blobs when
    those ids are cited. A cited id with no blob raises. Does not copy
    ``.cats/registry/``.
    """
    bom = bom_response.get('bom')
    if not isinstance(bom, dict):
        raise RuntimeError('bom_response is missing signed bom')
    dest = resolve_result_dir(cats_home, result_dir)
    dest.mkdir(parents=True, exist_ok=True)
    store = CasHttpStore(cats_home)

    invoice_uri = ref_uri(bom, 'invoice')
    invoice_id = _ref_content_id(bom, 'invoice', cats_home=cats_home)
    if not invoice_id:
        raise RuntimeError('signed BOM missing invoice_uri')
    invoice_blob = store.get(invoice_id)
    if invoice_blob is None:
        raise RuntimeError(f'CAS content not found: {invoice_id}')
    invoice = json.loads(invoice_blob.decode('utf-8'))
    if not isinstance(invoice, dict):
        raise RuntimeError(f'Invoice {invoice_id} is not a JSON object')

    data_uri = ref_uri(bom, 'data') or ref_uri(invoice, 'data')
    order_uri = ref_uri(bom, 'order') or ref_uri(invoice, 'order')

    cas_dir = dest / 'cas'
    for content_id in _cited_content_ids(
        bom_response,
        bom,
        invoice,
        invoice_id,
        cats_home=cats_home,
    ):
        _copy_blob(store, cas_dir, content_id)

    (dest / 'invoice.json').write_text(
        json.dumps(invoice, indent=2) + '\n',
        encoding='utf-8',
    )
    (dest / 'bom.json').write_text(
        json.dumps(bom, indent=2) + '\n',
        encoding='utf-8',
    )
    result = {
        'content_id': bom_response.get('content_id'),
        'invoice_content_id': invoice_id,
        'invoice_uri': invoice_uri,
        'data_uri': data_uri,
        'order_uri': order_uri,
    }
    (dest / 'result.json').write_text(
        json.dumps(result, indent=2) + '\n',
        encoding='utf-8',
    )
    return dest
