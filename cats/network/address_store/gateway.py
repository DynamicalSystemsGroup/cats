"""IPFS HTTP gateway client — GET /ipfs/{cid} (locator only; CID is address of record)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlencode, urljoin

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

    def _url_for(self, cid: str, *, query: dict[str, str] | None = None) -> str:
        # Single path segment — reject separators that could traverse.
        if not cid or '/' in cid or '\\' in cid or '..' in cid:
            raise GatewayError(self.base_url, None, f'invalid CID path segment: {cid!r}')
        path = urljoin(f'{self.base_url}/', f'ipfs/{quote(cid, safe="")}')
        if query:
            return f'{path}?{urlencode(query)}'
        return path

    def _get(self, url: str, *, headers: dict[str, str] | None = None, stream: bool = False):
        try:
            response = self._session.get(
                url, timeout=self.timeout, headers=headers or {}, stream=stream
            )
        except requests.RequestException as exc:
            raise GatewayError(url, None, str(exc)) from exc
        if response.status_code >= 400:
            detail = response.text[:500] if not stream else f'HTTP {response.status_code}'
            raise GatewayError(url, response.status_code, detail)
        return response

    def cat_bytes(self, cid: str) -> bytes:
        url = self._url_for(cid)
        return self._get(url).content

    def dag_export(self, cid: str, filepath: str) -> None:
        """Stream trustless CAR (``?format=car``) to ``filepath``."""
        url = self._url_for(cid, query={'format': 'car'})
        headers = {'Accept': 'application/vnd.ipld.car'}
        response = self._get(url, headers=headers, stream=True)
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('wb') as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)

    def get_file(self, cid: str, dest_path: str) -> str:
        """Fetch a UnixFS **file** body to ``dest_path``.

        Rejects HTML directory listings so callers can fall back to RPC ``get``.
        """
        url = self._url_for(cid)
        response = self._get(url)
        content_type = (response.headers.get('Content-Type') or '').lower()
        body = response.content
        if 'text/html' in content_type or body.lstrip()[:32].lower().startswith(b'<html'):
            raise GatewayError(url, response.status_code, 'directory or HTML listing')
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if dest.is_dir():
                raise GatewayError(url, None, f'dest is a directory: {dest}')
            dest.unlink()
        dest.write_bytes(body)
        return str(dest)
