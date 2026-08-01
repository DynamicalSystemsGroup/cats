"""IPFS HTTP gateway client — GET /ipfs/{cid} (locator only; CID is address of record)."""
from __future__ import annotations

from urllib.parse import quote, urljoin

import requests


class GatewayError(RuntimeError):
    """Raised when an IPFS HTTP gateway fetch fails."""

    def __init__(self, url: str, status_code: int | None, detail: str = ''):
        self.url = url
        self.status_code = status_code
        self.detail = detail
        status = status_code if status_code is not None else 'network'
        super().__init__(f'IPFS gateway GET {url} failed ({status}): {detail}')


class IpfsHttpGateway:
    """Thin sync client for ``{base}/ipfs/{cid}``."""

    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._session = requests.Session()

    def _url_for(self, cid: str) -> str:
        # Single path segment — reject separators that could traverse.
        if not cid or '/' in cid or '\\' in cid or '..' in cid:
            raise GatewayError(self.base_url, None, f'invalid CID path segment: {cid!r}')
        return urljoin(f'{self.base_url}/', f'ipfs/{quote(cid, safe="")}')

    def cat_bytes(self, cid: str) -> bytes:
        url = self._url_for(cid)
        try:
            response = self._session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise GatewayError(url, None, str(exc)) from exc
        if response.status_code >= 400:
            raise GatewayError(url, response.status_code, response.text[:500])
        return response.content
