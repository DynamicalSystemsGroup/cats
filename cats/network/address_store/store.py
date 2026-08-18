"""AddressStore — content-addressed reads: CAS ``ni:`` or legacy CID+Kubo."""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any
from urllib.request import Request, urlopen

from cats.network.address_store.cid_verify import verify_bytes_match_cid
from cats.network.address_store.gateway import GatewayError, IpfsHttpGateway
from cats.network.address_store.unixfs_extract import (
    UnixfsExtractError,
    extract_unixfs_from_car,
)
from cats.network.cas.digest import (
    from_ni,
    is_ni_or_digest,
    sha256_hex,
)
from cats.network.cas.manifest import is_directory_manifest, materialize_tree


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


class AddressStore:
    """Content-addressed reads.

    * ``ni:`` / hex digests — locator index → HTTP GET → sha256 verify;
      local ``CasHttpStore`` when ``cats_home`` is set.
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

    def cat_bytes(self, cid: str) -> bytes:
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

    def cat(self, cid: str) -> str:
        return self.cat_bytes(cid).decode('utf-8')

    def cat_obj(self, cid: str) -> Any:
        """JSON-decode ``cat`` bytes (helper; ContentMesh.catObj returns raw bytes)."""
        return json.loads(self.cat(cid))

    def dag_export(self, cid: str, filepath: str) -> None:
        """Export DAG as CAR: gateway ``?format=car`` first, else Kubo RPC.

        Not used for CAS ``ni:`` blobs (fetch via ``cat_bytes`` / ``get``).
        """
        if is_ni_or_digest(cid):
            raise ValueError(f'dag_export is for legacy CIDs only, got {cid!r}')
        if self.gateway is not None:
            try:
                self.gateway.dag_export(cid, filepath)
                return
            except GatewayError:
                pass
        self.ipfs.dag_export(cid, filepath)

    def get(self, cid: str, dest_path: str) -> str:
        """Materialize content at ``dest_path``.

        CAS directory manifests expand to a tree; single CAS blobs write a file;
        legacy CIDs use gateway / Kubo as before.
        """
        if is_ni_or_digest(cid):
            raw = self.cat_bytes(cid)
            try:
                obj = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                obj = None
            if is_directory_manifest(obj):
                os.makedirs(dest_path, exist_ok=True)
                return materialize_tree(self.cat_bytes, cid, dest_path)
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
