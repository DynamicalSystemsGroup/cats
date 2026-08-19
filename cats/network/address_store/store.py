"""AddressStore — content-addressed reads: CAS ``ni:``, ``hl:``, HTTP URI, or legacy CID."""
from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cats.network.address_store.cid_verify import verify_bytes_match_cid
from cats.network.address_store.gateway import GatewayError, IpfsHttpGateway
from cats.network.address_store.unixfs_extract import (
    UnixfsExtractError,
    extract_unixfs_from_car,
)
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


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


class AddressStore:
    """Content-addressed reads.

    * ``hl:`` — ``from_hl`` → GET hint URI(s) → sha256 verify (fail closed);
      empty/failed hints fall through to ``ni:`` (CAS + LocatorIndex).
    * ``ni:`` / hex digests — locator index → HTTP GET → sha256 verify;
      local ``CasHttpStore`` when ``cats_home`` is set.
    * ``http(s)://`` — GET then verify when digest known (path parse / locator /
      optional ``expect_digest``).
    * Legacy CIDs — gateway-first when configured, else Kubo RPC.
    """

    def __init__(
        self,
        ipfs_client,
        gateway_url: str | None = None,
        *,
        verify_rpc: bool | None = None,
        timeout: float = 120.0,
        cats_home: str | None = None,
    ):
        self.ipfs = ipfs_client
        self.cats_home = cats_home
        self.timeout = timeout
        if gateway_url is None:
            gateway_url = os.environ.get('IPFS_GATEWAY_URL') or None
        if gateway_url:
            gateway_url = gateway_url.strip() or None
        self.gateway = (
            IpfsHttpGateway(gateway_url, timeout=timeout) if gateway_url else None
        )
        if verify_rpc is None:
            verify_rpc = _env_flag('CATS_CID_VERIFY', default=False)
        self.verify_rpc = bool(verify_rpc)

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

    def cat_bytes(self, cid: str, *, expect_digest: str | None = None) -> bytes:
        if is_hl(cid):
            ni, uris = from_hl(cid.strip())
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
                        f'hl: sha256 mismatch for {cid!r} via {uri}'
                    )
                return data
            # No usable hint (or all GETs failed) — same path as bare ni:.
            cid = ni

        if is_http_uri(cid):
            local = self._local_ldp_bytes(cid)
            if local is not None:
                data, path_digest = local
            else:
                data = self._http_get_bytes(cid)
                path_digest = None
            digest = self._resolve_expect_digest(cid, expect_digest) or path_digest
            if digest is not None and sha256_hex(data) != digest:
                raise RuntimeError(
                    f'URI sha256 mismatch for {cid!r} (expected {digest})'
                )
            return data

        if is_ni_or_digest(cid):
            data = self._cas_local_bytes(cid)
            if data is None:
                data = self._cas_locator_bytes(cid)
            if data is None:
                raise FileNotFoundError(f'CAS content not found: {cid}')
            digest = from_ni(cid)
            if sha256_hex(data) != digest:
                raise RuntimeError(f'CAS sha256 mismatch for {cid!r}')
            return data

        data: bytes | None = None
        from_gateway = False
        if self.gateway is not None:
            try:
                data = self.gateway.cat_bytes(cid)
                from_gateway = True
            except GatewayError:
                data = None
        if data is None:
            data = self.ipfs.cat_bytes(cid)
        if from_gateway or self.verify_rpc:
            verify_bytes_match_cid(self.ipfs, cid, data)
        return data

    def cat(self, cid: str, *, expect_digest: str | None = None) -> str:
        return self.cat_bytes(cid, expect_digest=expect_digest).decode('utf-8')

    def cat_obj(self, cid: str, *, expect_digest: str | None = None) -> Any:
        """JSON-decode ``cat`` bytes (helper; ContentMesh.catObj returns raw bytes)."""
        return json.loads(self.cat(cid, expect_digest=expect_digest))

    def dag_export(self, cid: str, filepath: str) -> None:
        """Export DAG as CAR: gateway ``?format=car`` first, else Kubo RPC.

        Not used for CAS ``ni:`` blobs (fetch via ``cat_bytes`` / ``get``).
        """
        if is_http_uri(cid) or is_ni_or_digest(cid) or is_hl(cid):
            raise ValueError(f'dag_export is for legacy CIDs only, got {cid!r}')
        if self.gateway is not None:
            try:
                self.gateway.dag_export(cid, filepath)
                return
            except GatewayError:
                pass
        self.ipfs.dag_export(cid, filepath)

    def get(self, cid: str, dest_path: str, *, expect_digest: str | None = None) -> str:
        """Materialize content at ``dest_path``.

        CAS directory manifests expand to a tree; single CAS blobs write a file;
        HTTP URIs fetch then write/verify; legacy CIDs use gateway / Kubo.
        """
        if is_http_uri(cid) or is_ni_or_digest(cid) or is_hl(cid):
            raw = self.cat_bytes(cid, expect_digest=expect_digest)
            try:
                obj = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                obj = None
            if is_directory_manifest(obj):
                manifest_id = expect_digest or cid
                if is_hl(cid):
                    manifest_id, _ = from_hl(cid.strip())
                if is_http_uri(cid) and self.cats_home:
                    from cats.network.cas import LocatorIndex

                    found = LocatorIndex(self.cats_home).find_content_id_for_uri(cid)
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

        if self.gateway is not None:
            try:
                return self.gateway.get_file(cid, dest_path)
            except GatewayError:
                pass
            try:
                with tempfile.TemporaryDirectory(prefix='cats-car-get-') as tmp:
                    car_path = os.path.join(tmp, 'dag.car')
                    self.gateway.dag_export(cid, car_path)
                    return extract_unixfs_from_car(
                        car_path,
                        cid,
                        dest_path,
                        ipfs_client=self.ipfs,
                    )
            except (GatewayError, UnixfsExtractError, OSError, ValueError):
                pass
        return self.ipfs.get(cid, dest_path)
