"""Thin sync Kubo HTTP RPC client behind CatsIPFSClient.

Talks to the host daemon at http://{host}:{port}/api/v0/* with plain
`requests` POSTs — no ipfshttpclient / http+ip4 multiaddr stack.
"""
from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import Any

import requests


class KuboRpcError(RuntimeError):
    """Raised when a Kubo RPC call fails."""

    def __init__(self, endpoint: str, status_code: int, body: str):
        self.endpoint = endpoint
        self.status_code = status_code
        self.body = body
        super().__init__(f'Kubo RPC {endpoint} failed ({status_code}): {body}')


class KuboRpcClient:
    """Minimal sync Kubo RPC (/api/v0) client used by CatsIPFSClient."""

    def __init__(self, host: str = '127.0.0.1', port: int = 5001, timeout: float = 120.0):
        self.base_url = f'http://{host}:{port}/api/v0'
        self.timeout = timeout
        self._session = requests.Session()

    def _post(
        self,
        endpoint: str,
        *,
        params: dict | None = None,
        files=None,
        data=None,
        stream: bool = False,
    ) -> requests.Response:
        url = f'{self.base_url}/{endpoint.lstrip("/")}'
        response = self._session.post(
            url,
            params=params or {},
            files=files,
            data=data,
            timeout=self.timeout,
            stream=stream,
        )
        if response.status_code >= 400:
            raise KuboRpcError(endpoint, response.status_code, response.text[:500])
        return response

    def id(self) -> dict:
        return self._post('id').json()

    def add_bytes(self, data: bytes, *, filename: str = 'blob', **_kwargs) -> str:
        response = self._post(
            'add',
            params={'pin': 'true'},
            files={'file': (filename, data, 'application/octet-stream')},
        )
        return response.json()['Hash']

    def add_str(self, string: str, **kwargs) -> str:
        return self.add_bytes(string.encode('utf-8'), filename='blob', **kwargs)

    def add_json(self, obj: Any, **kwargs) -> str:
        return self.add_str(json.dumps(obj), **kwargs)

    def add(self, filepath: str, *, recursive: bool = False, **_kwargs):
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(filepath)

        if path.is_file() and not recursive:
            response = self._post(
                'add',
                params={'pin': 'true'},
                files={'file': (path.name, path.read_bytes(), 'application/octet-stream')},
            )
            return response.json()

        if not path.is_dir():
            # Single file with recursive=True — same as file add.
            response = self._post(
                'add',
                params={'pin': 'true', 'recursive': 'true'},
                files={'file': (path.name, path.read_bytes(), 'application/octet-stream')},
            )
            return response.json()

        return self._add_directory(path)

    def _add_directory(self, directory: Path) -> list[dict]:
        """Multipart recursive add matching `ipfs add -r` / cidDir expectations."""
        base = directory.parent
        parts = []
        for dirpath, _dirnames, filenames in os.walk(directory):
            rel_dir = os.path.relpath(dirpath, base)
            parts.append(('file', (rel_dir, b'', 'application/x-directory')))
            for filename in filenames:
                full = Path(dirpath) / filename
                rel = os.path.relpath(full, base)
                parts.append(
                    ('file', (rel, full.read_bytes(), 'application/octet-stream'))
                )

        response = self._post(
            'add',
            params={
                'recursive': 'true',
                'pin': 'true',
                'wrap-with-directory': 'false',
            },
            files=parts,
        )
        entries = []
        for line in response.text.splitlines():
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
        return entries


def connect(host: str = '127.0.0.1', port: int = 5001, validate: bool = False):
    client = KuboRpcClient(host=host, port=port)
    if validate:
        client.id()
    return CatsIPFSClient(client)


class CatsIPFSClient:
    """CATs-facing IPFS helpers over KuboRpcClient (replaces ipfshttpclient)."""

    def __init__(self, client: KuboRpcClient):
        self._client = client

    def id(self) -> dict:
        return self._client.id()

    def add(self, filepath: str, recursive: bool = False, **kwargs):
        return self._client.add(filepath, recursive=recursive, **kwargs)

    def add_bytes(self, data: bytes, **kwargs) -> str:
        return self._client.add_bytes(data, **kwargs)

    def add_str(self, string: str, **kwargs) -> str:
        return self._client.add_str(string, **kwargs)

    def add_json(self, obj: Any, **kwargs) -> str:
        return self._client.add_json(obj, **kwargs)

    def add_pyobj(self, py_obj, **kwargs) -> str:
        return self._client.add_bytes(pickle.dumps(py_obj), **kwargs)

    def post_upload(self, filepath: str, **kwargs) -> str:
        result = self._client.add(filepath, **kwargs)
        if isinstance(result, dict):
            return result['Hash']
        for attrs in result:
            return attrs['Hash']
        raise ValueError(f'Could not upload {filepath} to IPFS')
