"""Node-local append-only BOM registry (Control-Feedback index; not the envelope store)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cats.network.cas.content_ref import ref_id, ref_uri
from cats.network.cas.digest import content_id_fs_key, is_ni_or_digest, to_ni, from_ni
from cats.network.cas.invoice_stages import resolve_invoice_data_stages
from cats.network.feedback import verify_execution_bom


class RegistryError(Exception):
    """Registry put / lookup failure."""


class AmbiguousBomError(RegistryError):
    """More than one BOM matches a reverse lookup key."""

    def __init__(self, key: str, bom_ids: list[str]):
        self.key = key
        self.bom_ids = list(bom_ids)
        # Compat alias for callers/tests still reading .bom_cids
        self.bom_cids = self.bom_ids
        super().__init__(
            f'ambiguous registry lookup for {key!r}: {self.bom_ids}'
        )


def _normalize_content_id(value: str, *, label: str) -> str:
    """Return canonical id (ni: for digests, CID otherwise) and validate fs key."""
    content_id_fs_key(value, label=label)
    if is_ni_or_digest(value):
        return to_ni(from_ni(value))
    return value.strip()


def _record_bom_id(record: dict[str, Any]) -> str | None:
    """BOM equality id from a stored record (new ``content_id`` or legacy ``bom_cid``)."""
    value = record.get('content_id') or record.get('bom_cid')
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _record_order_id(record: dict[str, Any]) -> str | None:
    value = record.get('order') or record.get('order_cid')
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _record_data_id(record: dict[str, Any]) -> str | None:
    value = record.get('data') or record.get('data_cid')
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def project_record(record: dict[str, Any]) -> dict[str, Any]:
    """HTTP/JSON projection: ``content_id`` + ``*_uri`` (no ``*_cid`` keys)."""
    bom_id = _record_bom_id(record)
    order_id = _record_order_id(record)
    data_id = _record_data_id(record)
    loc = record.get('locators') or {}
    out: dict[str, Any] = {
        'content_id': bom_id,
        'invoice_uri': record.get('invoice_uri') or loc.get('invoice_uri'),
        'order_uri': record.get('order_uri') or loc.get('order_uri'),
        'data_uri': record.get('data_uri'),
        'node_did': record.get('node_did'),
        'locators': {
            'bom_ldp_uri': loc.get('bom_ldp_uri'),
            'bom_solid_uri': loc.get('bom_solid_uri'),
            'invoice_uri': loc.get('invoice_uri') or record.get('invoice_uri'),
            'order_uri': loc.get('order_uri') or record.get('order_uri'),
        },
    }
    # Equality ids without *_cid names (for clients that need ni: without fetch).
    if order_id:
        out['order'] = order_id
    if data_id:
        out['data'] = data_id
    if record.get('input_data') or record.get('input_data_cid'):
        out['input_data'] = record.get('input_data') or record.get('input_data_cid')
    if record.get('function') or record.get('function_cid'):
        out['function'] = record.get('function') or record.get('function_cid')
    if record.get('structure') or record.get('structure_cid'):
        out['structure'] = record.get('structure') or record.get('structure_cid')
    if record.get('ingress_data_uri'):
        out['ingress_data_uri'] = record['ingress_data_uri']
    elif record.get('ingress_data') or record.get('ingress_data_cid'):
        out['ingress_data'] = record.get('ingress_data') or record.get(
            'ingress_data_cid'
        )
    if record.get('integration_data_uri'):
        out['integration_data_uri'] = record['integration_data_uri']
    elif record.get('integration_data') or record.get('integration_data_cid'):
        out['integration_data'] = record.get('integration_data') or record.get(
            'integration_data_cid'
        )
    if record.get('data_stages_uri'):
        out['data_stages_uri'] = record['data_stages_uri']
    elif record.get('data_stages'):
        out['data_stages'] = record['data_stages']
    if record.get('seed_uri'):
        out['seed_uri'] = record['seed_uri']
    elif record.get('seed') or record.get('seed_cid'):
        out['seed'] = record.get('seed') or record.get('seed_cid')
    # Drop None values for a cleaner projection.
    return {k: v for k, v in out.items() if v is not None}


def build_record(
    bom: dict[str, Any],
    content_id: str,
    *,
    content_mesh,
    locators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify ``bom``, extract Invoice/Order fields via AddressStore, return record.

    Does not trust client-supplied index fields beyond optional locators.
    New records use ``content_id`` + ``*_uri`` (+ equality ``order`` / ``data``);
    ``*_cid`` keys are not written.
    """
    bom_id = _normalize_content_id(content_id, label='content_id')
    cats_home = getattr(content_mesh, 'CATS_HOME', None)
    try:
        verify_execution_bom(bom)
    except Exception as exc:
        raise RegistryError(f'unsigned or invalid ExecutionBom: {exc}') from exc

    invoice_id = ref_id(bom, 'invoice', cats_home=cats_home)
    invoice_locator = ref_uri(bom, 'invoice') or invoice_id
    if not invoice_locator:
        raise RegistryError('ExecutionBom missing invoice_uri / invoice_cid')

    try:
        invoice = json.loads(content_mesh.cat(invoice_locator))
    except Exception as exc:
        raise RegistryError(
            f'failed to load invoice {invoice_locator!r}: {exc}'
        ) from exc

    order_id = ref_id(invoice, 'order', cats_home=cats_home)
    data_id = ref_id(invoice, 'data', cats_home=cats_home)
    if not order_id:
        raise RegistryError('Invoice missing order_uri / order_cid')
    if not data_id:
        raise RegistryError('Invoice missing data_uri / data_cid')

    order_id = _normalize_content_id(order_id, label='order')
    data_id = _normalize_content_id(data_id, label='data')
    if invoice_id:
        invoice_id = _normalize_content_id(invoice_id, label='invoice')

    function_id = None
    structure_id = None
    input_data_id = None
    try:
        order_locator = ref_uri(invoice, 'order') or order_id
        order = json.loads(content_mesh.cat(order_locator))
        function_id = ref_id(order, 'function', cats_home=cats_home)
        structure_id = ref_id(order, 'structure', cats_home=cats_home)
        input_invoice_locator = ref_uri(order, 'invoice') or ref_id(
            order, 'invoice', cats_home=cats_home
        )
        if input_invoice_locator:
            input_invoice = json.loads(content_mesh.cat(input_invoice_locator))
            input_data_id = ref_id(input_invoice, 'data', cats_home=cats_home)
    except Exception:
        # Order graph may be partially unavailable; still index BOM→Order/data.
        pass

    loc = locators or {}
    invoice_uri = (
        loc.get('invoice_uri')
        or ref_uri(bom, 'invoice')
        or invoice.get('invoice_uri')
        or bom.get('invoice_uri')
    )
    order_uri = loc.get('order_uri') or ref_uri(invoice, 'order')
    data_uri = ref_uri(invoice, 'data')
    stages = resolve_invoice_data_stages(
        invoice, content_mesh=content_mesh, cats_home=cats_home
    )

    return {
        'content_id': bom_id,
        'invoice_uri': invoice_uri,
        'order': order_id,
        'order_uri': order_uri,
        'data': data_id,
        'data_uri': data_uri,
        'input_data': input_data_id,
        'node_did': bom.get('node_did'),
        'function': function_id,
        'structure': structure_id,
        'locators': {
            'bom_ldp_uri': loc.get('bom_ldp_uri'),
            'bom_solid_uri': loc.get('bom_solid_uri'),
            'invoice_uri': loc.get('invoice_uri') or invoice_uri,
            'order_uri': loc.get('order_uri') or order_uri,
            **(
                {'data_stages_uri': stages['data_stages_uri']}
                if stages.get('data_stages_uri')
                else {}
            ),
        },
        'ingress_data': stages.get('ingress_data_id'),
        'ingress_data_uri': stages.get('ingress_data_uri'),
        'integration_data': stages.get('integration_data_id'),
        'integration_data_uri': stages.get('integration_data_uri'),
        'data_stages': stages.get('data_stages_id'),
        'data_stages_uri': stages.get('data_stages_uri'),
        'seed': ref_id(invoice, 'seed', cats_home=cats_home),
        'seed_uri': ref_uri(invoice, 'seed'),
    }


class BomRegistry:
    """Append-only JSON index under ``{CATS_HOME}/.cats/registry/``."""

    def __init__(self, cats_home: str):
        self.cats_home = cats_home
        self.root = Path(cats_home) / '.cats' / 'registry'
        self.boms_dir = self.root / 'boms'
        self.by_data_dir = self.root / 'by-data'
        self.by_order_dir = self.root / 'by-order'
        for path in (self.boms_dir, self.by_data_dir, self.by_order_dir):
            path.mkdir(parents=True, exist_ok=True)

    def _bom_path(self, content_id: str) -> Path:
        key = content_id_fs_key(content_id, label='content_id')
        return self.boms_dir / f'{key}.json'

    def _index_path(self, directory: Path, cid: str, *, label: str) -> Path:
        key = content_id_fs_key(cid, label=label)
        return directory / f'{key}.json'

    def _read_list(self, path: Path) -> list[str]:
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, list):
            return [str(x) for x in data]
        return []

    def _append_index(self, path: Path, bom_id: str) -> None:
        existing = self._read_list(path)
        if bom_id in existing:
            return
        # Newest first.
        updated = [bom_id] + existing
        path.write_text(
            json.dumps(updated, indent=2) + '\n',
            encoding='utf-8',
        )

    def put(self, record: dict[str, Any]) -> Path:
        """Idempotent on BOM ``content_id``; append reverse indexes if absent."""
        bom_id = _normalize_content_id(
            _record_bom_id(record) or '', label='content_id'
        )
        order_id = _normalize_content_id(
            _record_order_id(record) or '', label='order'
        )
        data_id = _normalize_content_id(
            _record_data_id(record) or '', label='data'
        )

        path = self._bom_path(bom_id)
        stored = dict(record)
        # Canonical §6d shape — drop legacy *_cid keys if a caller passed them.
        for legacy in (
            'bom_cid',
            'invoice_cid',
            'order_cid',
            'data_cid',
            'input_data_cid',
            'function_cid',
            'structure_cid',
            'ingress_data_cid',
            'integration_data_cid',
            'seed_cid',
        ):
            stored.pop(legacy, None)
        stored['content_id'] = bom_id
        stored['order'] = order_id
        stored['data'] = data_id
        path.write_text(
            json.dumps(stored, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        self._append_index(
            self._index_path(self.by_data_dir, data_id, label='data'),
            bom_id,
        )
        self._append_index(
            self._index_path(self.by_order_dir, order_id, label='order'),
            bom_id,
        )
        return path

    def get(self, content_id: str) -> dict[str, Any] | None:
        path = self._bom_path(content_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding='utf-8'))

    def lookup_order(self, content_id: str) -> str | None:
        record = self.get(content_id)
        if record is None:
            return None
        return _record_order_id(record)

    def lookup_bom(self, data_id: str) -> list[str]:
        path = self._index_path(self.by_data_dir, data_id, label='data')
        return self._read_list(path)

    def lookup_by_order(self, order_id: str) -> list[str]:
        path = self._index_path(self.by_order_dir, order_id, label='order')
        return self._read_list(path)

    def list_boms(self) -> list[str]:
        """Return BOM content ids sorted by mtime descending (newest first)."""
        entries: list[tuple[float, str]] = []
        for path in self.boms_dir.glob('*.json'):
            entries.append((path.stat().st_mtime, path.stem))
        entries.sort(key=lambda item: item[0], reverse=True)
        out: list[str] = []
        for _mtime, stem in entries:
            record = json.loads(
                (self.boms_dir / f'{stem}.json').read_text(encoding='utf-8')
            )
            out.append(_record_bom_id(record) or stem)
        return out

    def resolve_unique_bom(self, data_id: str) -> str:
        """Return the sole BOM id for ``data`` or raise AmbiguousBomError / RegistryError."""
        bom_ids = self.lookup_bom(data_id)
        if not bom_ids:
            raise RegistryError(f'no BOM for data={data_id!r}')
        if len(bom_ids) > 1:
            raise AmbiguousBomError(data_id, bom_ids)
        return bom_ids[0]

    def container_document(self, *, base_url: str | None = None) -> dict[str, Any]:
        if base_url is None:
            from cats.network.node_http import _node_base_url

            base_url = _node_base_url()
        base = base_url.rstrip('/')
        contains = []
        for cid in self.list_boms():
            key = content_id_fs_key(cid, label='content_id')
            contains.append(f'{base}/ldp/registry/boms/{key}')
        return {
            '@context': {
                'ldp': 'http://www.w3.org/ns/ldp#',
                'contains': {'@id': 'ldp:contains', '@type': '@id'},
            },
            '@id': f'{base}/ldp/registry/',
            '@type': ['ldp:BasicContainer', 'ldp:Container'],
            'contains': contains,
        }
