"""AddressStore — content-addressed reads: CAS ``ni:``, ``hl:``, or HTTP URI.

Legacy IPFS CIDs (``Qm…`` / ``bafy…``) fail closed (§6s).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cats.network.cas.content_ref import is_http_uri
from cats.network.cas.digest import (
    from_ni,
    is_ni_or_digest,
    sha256_hex,
    validate_digest_segment,
)
from cats.network.cas.hashlink import from_hl, is_hl
from cats.network.cas.manifest import is_directory_manifest, materialize_tree

_CAS_PATH = re.compile(r'^/ldp/cas/([0-9a-f]{64})$')
_INVOICE_PATH = re.compile(r'^/ldp/invoices/([0-9a-fA-Za-z]+)$')
_ORDER_PATH = re.compile(r'^/ldp/orders/([0-9a-fA-Za-z]+)$')


def _legacy_cid_unsupported(content_id: str) -> RuntimeError:
    return RuntimeError(
        f'Legacy CID {content_id!r} is unsupported (§6s); remint to ni: / HTTP uri'
    )


class AddressStore:
    """Content-addressed reads (CAS / ``hl:`` / HTTP only).

    * ``hl:`` — ``from_hl`` → GET hint URI(s) → sha256 verify (fail closed);
      empty/failed hints fall through to ``ni:`` (CAS + LocatorIndex).
    * ``ni:`` / hex digests — locator index → HTTP GET → sha256 verify;
      local ``CasHttpStore`` when ``cats_home`` is set.
    * ``http(s)://`` — GET then verify when digest known (path parse / locator /
      optional ``expect_digest``).
    * Legacy CIDs — raise (§6s).
    """

    def __init__(
        self,
        ipfs_client=None,
        gateway_url: str | None = None,
        *,
        verify_rpc: bool | None = None,
        timeout: float = 120.0,
        cats_home: str | None = None,
    ):
        # ipfs_client / gateway_url / verify_rpc kept for call-site compat; unused (§6s).
        self.ipfs = ipfs_client
        self.cats_home = cats_home
        self.timeout = timeout
        self.gateway = None
        self.verify_rpc = False

    def _cas_local_bytes(self, content_id: str) -> bytes | None:
        if not self.cats_home:
            return None
        from cats.network.cas import CasHttpStore

        return CasHttpStore(self.cats_home).get(content_id)

    def _cas_locator_bytes(self, content_id: str) -> bytes | None:
        if not self.cats_home:
            return None
        from cats.network.cas import LocatorIndex

        for uri in LocatorIndex(self.cats_home).lookup_uris(content_id):
            try:
                req = Request(uri, method='GET')
                with urlopen(req, timeout=self.timeout) as resp:
                    data = resp.read()
            except Exception:
                continue
            digest = from_ni(content_id)
            if sha256_hex(data) != digest:
                raise RuntimeError(
                    f'CAS locator verify failed for {content_id!r} via {uri}'
                )
            return data
        return None

    def _local_ldp_bytes(self, uri: str) -> tuple[bytes, str | None] | None:
        """Resolve Node-local LDP paths without HTTP; return (bytes, digest_or_None)."""
        if not self.cats_home:
            return None
        parsed = urlparse(uri)
        path = parsed.path or ''
        cas_m = _CAS_PATH.match(path)
        if cas_m:
            digest = validate_digest_segment(cas_m.group(1))
            from cats.network.cas import CasHttpStore

            data = CasHttpStore(self.cats_home).get(digest)
            if data is None:
                return None
            return data, digest
        inv_m = _INVOICE_PATH.match(path)
        if inv_m:
            from cats.network.ldp.resource_store import JsonResourceStore

            key = inv_m.group(1)
            data = JsonResourceStore(self.cats_home, 'invoices').get_bytes(key)
            if data is None:
                return None
            digest = None
            try:
                digest = validate_digest_segment(key.lower())
            except ValueError:
                pass
            return data, digest
        ord_m = _ORDER_PATH.match(path)
        if ord_m:
            from cats.network.ldp.resource_store import JsonResourceStore

            key = ord_m.group(1)
            data = JsonResourceStore(self.cats_home, 'orders').get_bytes(key)
            if data is None:
                return None
            digest = None
            try:
                digest = validate_digest_segment(key.lower())
            except ValueError:
                pass
            return data, digest
        return None

    def _http_get_bytes(self, uri: str) -> bytes:
        req = Request(uri, method='GET')
        with urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def _fetch_hint_uri(self, uri: str) -> bytes:
        local = self._local_ldp_bytes(uri)
        if local is not None:
            return local[0]
        return self._http_get_bytes(uri)

    def _resolve_expect_digest(
        self, uri: str, expect_digest: str | None
    ) -> str | None:
        if expect_digest:
            if is_ni_or_digest(expect_digest):
                return from_ni(expect_digest)
            return validate_digest_segment(expect_digest)
        cas_m = _CAS_PATH.match(urlparse(uri).path or '')
        if cas_m:
            return validate_digest_segment(cas_m.group(1))
        if self.cats_home:
            from cats.network.cas import LocatorIndex

            content_id = LocatorIndex(self.cats_home).find_content_id_for_uri(uri)
            if content_id and is_ni_or_digest(content_id):
                return from_ni(content_id)
        return None

    def cat_bytes(self, content_id: str, *, expect_digest: str | None = None) -> bytes:
        if is_hl(content_id):
            ni, uris = from_hl(content_id.strip())
            digest = from_ni(ni)
            for uri in uris:
                if not is_http_uri(uri):
                    continue
                try:
                    data = self._fetch_hint_uri(uri)
                except Exception:
                    continue
                if sha256_hex(data) != digest:
                    raise RuntimeError(
                        f'hl: sha256 mismatch for {content_id!r} via {uri}'
                    )
                return data
            # No usable hint (or all GETs failed) — same path as bare ni:.
            content_id = ni

        if is_http_uri(content_id):
            local = self._local_ldp_bytes(content_id)
            if local is not None:
                data, path_digest = local
            else:
                data = self._http_get_bytes(content_id)
                path_digest = None
            digest = self._resolve_expect_digest(content_id, expect_digest) or path_digest
            if digest is not None and sha256_hex(data) != digest:
                raise RuntimeError(
                    f'URI sha256 mismatch for {content_id!r} (expected {digest})'
                )
            return data

        if is_ni_or_digest(content_id):
            data = self._cas_local_bytes(content_id)
            if data is None:
                data = self._cas_locator_bytes(content_id)
            if data is None:
                raise FileNotFoundError(f'CAS content not found: {content_id}')
            digest = from_ni(content_id)
            if sha256_hex(data) != digest:
                raise RuntimeError(f'CAS sha256 mismatch for {content_id!r}')
            return data

        raise _legacy_cid_unsupported(content_id)

    def cat(self, content_id: str, *, expect_digest: str | None = None) -> str:
        return self.cat_bytes(content_id, expect_digest=expect_digest).decode('utf-8')

    def cat_obj(self, content_id: str, *, expect_digest: str | None = None) -> Any:
        """JSON-decode ``cat`` bytes (helper; ContentMesh.catObj returns raw bytes)."""
        return json.loads(self.cat(content_id, expect_digest=expect_digest))

    def dag_export(self, cid: str, filepath: str) -> None:
        """Retired (§6s). Legacy CID CAR export is unsupported."""
        raise _legacy_cid_unsupported(cid)

    def get(self, content_id: str, dest_path: str, *, expect_digest: str | None = None) -> str:
        """Materialize content at ``dest_path``.

        CAS directory manifests expand to a tree; single CAS blobs write a file;
        HTTP URIs fetch then write/verify. Legacy CIDs fail closed (§6s).
        """
        if is_http_uri(content_id) or is_ni_or_digest(content_id) or is_hl(content_id):
            raw = self.cat_bytes(content_id, expect_digest=expect_digest)
            try:
                obj = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                obj = None
            if is_directory_manifest(obj):
                manifest_id = expect_digest or content_id
                if is_hl(content_id):
                    manifest_id, _ = from_hl(content_id.strip())
                if is_http_uri(content_id) and self.cats_home:
                    from cats.network.cas import LocatorIndex

                    found = LocatorIndex(self.cats_home).find_content_id_for_uri(content_id)
                    if found:
                        manifest_id = found
                os.makedirs(dest_path, exist_ok=True)
                return materialize_tree(self.cat_bytes, manifest_id, dest_path)
            parent = os.path.dirname(dest_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(dest_path, 'wb') as handle:
                handle.write(raw)
            return dest_path

        raise _legacy_cid_unsupported(content_id)
