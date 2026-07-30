"""AddressStore — CID reads via optional HTTP gateway + verify; RPC fallback."""
from __future__ import annotations

import json
import os
from typing import Any

from cats.network.address_store.cid_verify import verify_bytes_match_cid
from cats.network.address_store.gateway import GatewayError, IpfsHttpGateway


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


class AddressStore:
    """Content-addressed reads: gateway-first when configured, else Kubo RPC.

    Writes stay on ``CatsIPFSClient`` (ContentMesh ``ipfsClient``). CID remains
    the address of record; gateway URL is a locator only.
    """

    def __init__(
        self,
        ipfs_client,
        gateway_url: str | None = None,
        *,
        verify_rpc: bool | None = None,
        timeout: float = 120.0,
    ):
        self.ipfs = ipfs_client
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

    def cat_bytes(self, cid: str) -> bytes:
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
