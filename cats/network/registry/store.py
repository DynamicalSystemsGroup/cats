"""Node-local append-only BOM registry (Control-Feedback index; not the envelope store)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cats.network.cid_segment import validate_cid_segment
from cats.network.feedback import verify_execution_bom


class RegistryError(Exception):
    """Registry put / lookup failure."""


class AmbiguousBomError(RegistryError):
    """More than one BOM matches a reverse lookup key."""

    def __init__(self, key: str, bom_cids: list[str]):
        self.key = key
        self.bom_cids = list(bom_cids)
        super().__init__(
            f'ambiguous registry lookup for {key!r}: {self.bom_cids}'
        )


def build_record(
    bom: dict[str, Any],
    bom_cid: str,
    *,
    content_mesh,
    locators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify ``bom``, extract Invoice/Order fields via AddressStore, return record.

    Does not trust client-supplied index fields beyond optional locators.
    """
    bom_cid = validate_cid_segment(bom_cid, label='bom_cid')
    try:
        verify_execution_bom(bom)
    except Exception as exc:
        raise RegistryError(f'unsigned or invalid ExecutionBom: {exc}') from exc

    invoice_cid = bom.get('invoice_cid')
    if not invoice_cid:
        raise RegistryError('ExecutionBom missing invoice_cid')

    try:
        invoice = json.loads(content_mesh.cat(invoice_cid))
    except Exception as exc:
        raise RegistryError(
            f'failed to load invoice_cid {invoice_cid!r}: {exc}'
        ) from exc

    order_cid = invoice.get('order_cid')
    data_cid = invoice.get('data_cid')
    if not order_cid:
        raise RegistryError('Invoice missing order_cid')
    if not data_cid:
        raise RegistryError('Invoice missing data_cid')

    order_cid = validate_cid_segment(order_cid, label='order_cid')
    data_cid = validate_cid_segment(data_cid, label='data_cid')

    function_cid = None
    structure_cid = None
    input_data_cid = None
    try:
        order = json.loads(content_mesh.cat(order_cid))
        function_cid = order.get('function_cid')
        structure_cid = order.get('structure_cid')
        input_invoice_cid = order.get('invoice_cid')
        if input_invoice_cid:
            input_invoice = json.loads(content_mesh.cat(input_invoice_cid))
            input_data_cid = input_invoice.get('data_cid')
    except Exception:
        # Order graph may be partially unavailable; still index BOM→Order/data.
        pass

    loc = locators or {}
    return {
        'bom_cid': bom_cid,
        'invoice_cid': invoice_cid,
        'order_cid': order_cid,
        'data_cid': data_cid,
        'input_data_cid': input_data_cid,
        'node_did': bom.get('node_did'),
        'function_cid': function_cid,
        'structure_cid': structure_cid,
        'locators': {
            'bom_ldp_uri': loc.get('bom_ldp_uri'),
            'bom_solid_uri': loc.get('bom_solid_uri'),
        },
        'ingress_data_cid': invoice.get('ingress_data_cid'),
        'integration_data_cid': invoice.get('integration_data_cid'),
        'seed_cid': invoice.get('seed_cid'),
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

    def _bom_path(self, bom_cid: str) -> Path:
        return self.boms_dir / f'{validate_cid_segment(bom_cid, label="bom_cid")}.json'

    def _index_path(self, directory: Path, cid: str, *, label: str) -> Path:
        return directory / f'{validate_cid_segment(cid, label=label)}.json'

    def _read_list(self, path: Path) -> list[str]:
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, list):
            return [str(x) for x in data]
        return []

    def _append_index(self, path: Path, bom_cid: str) -> None:
        existing = self._read_list(path)
        if bom_cid in existing:
            return
        # Newest first.
        updated = [bom_cid] + existing
        path.write_text(
            json.dumps(updated, indent=2) + '\n',
            encoding='utf-8',
        )

    def put(self, record: dict[str, Any]) -> Path:
        """Idempotent on ``bom_cid``; append reverse indexes if absent."""
        bom_cid = validate_cid_segment(record['bom_cid'], label='bom_cid')
        order_cid = validate_cid_segment(record['order_cid'], label='order_cid')
        data_cid = validate_cid_segment(record['data_cid'], label='data_cid')

        path = self._bom_path(bom_cid)
        path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        self._append_index(
            self._index_path(self.by_data_dir, data_cid, label='data_cid'),
            bom_cid,
        )
        self._append_index(
            self._index_path(self.by_order_dir, order_cid, label='order_cid'),
            bom_cid,
        )
        return path

    def get(self, bom_cid: str) -> dict[str, Any] | None:
        path = self._bom_path(bom_cid)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding='utf-8'))

    def lookup_order(self, bom_cid: str) -> str | None:
        record = self.get(bom_cid)
        if record is None:
            return None
        return record.get('order_cid')

    def lookup_bom(self, data_cid: str) -> list[str]:
        path = self._index_path(self.by_data_dir, data_cid, label='data_cid')
        return self._read_list(path)

    def lookup_by_order(self, order_cid: str) -> list[str]:
        path = self._index_path(self.by_order_dir, order_cid, label='order_cid')
        return self._read_list(path)

    def list_boms(self) -> list[str]:
        """Return bom_cid keys sorted by mtime descending (newest first)."""
        entries: list[tuple[float, str]] = []
        for path in self.boms_dir.glob('*.json'):
            entries.append((path.stat().st_mtime, path.stem))
        entries.sort(key=lambda item: item[0], reverse=True)
        return [cid for _mtime, cid in entries]

    def resolve_unique_bom(self, data_cid: str) -> str:
        """Return the sole bom_cid for ``data_cid`` or raise AmbiguousBomError / RegistryError."""
        bom_cids = self.lookup_bom(data_cid)
        if not bom_cids:
            raise RegistryError(f'no BOM for data_cid={data_cid!r}')
        if len(bom_cids) > 1:
            raise AmbiguousBomError(data_cid, bom_cids)
        return bom_cids[0]

    def container_document(self, *, base_url: str | None = None) -> dict[str, Any]:
        if base_url is None:
            from cats.network.node_http import _node_base_url

            base_url = _node_base_url()
        base = base_url.rstrip('/')
        contains = [
            f'{base}/ldp/registry/boms/{cid}' for cid in self.list_boms()
        ]
        return {
            '@context': {
                'ldp': 'http://www.w3.org/ns/ldp#',
                'contains': {'@id': 'ldp:contains', '@type': '@id'},
            },
            '@id': f'{base}/ldp/registry/',
            '@type': ['ldp:BasicContainer', 'ldp:Container'],
            'contains': contains,
        }
