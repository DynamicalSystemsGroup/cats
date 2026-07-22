"""Thin sync Kubo HTTP RPC client behind CatsIPFSClient.

Talks to the host daemon at http://{host}:{port}/api/v0/* with plain
`requests` POSTs — no ipfshttpclient / http+ip4 multiaddr stack.
MeshClient reads and writes both go through this client (no `ipfs` CLI).
"""
from __future__ import annotations

import io
import json
import os
import pickle
import shutil
import tarfile
import tempfile
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
            # Prefer reading text for errors; streamed bodies may need content.
            try:
                err_body = response.text[:500]
            except Exception:
                err_body = ''
            raise KuboRpcError(endpoint, response.status_code, err_body)
        return response

    def id(self) -> dict:
        return self._post('id').json()

    def cat_bytes(self, cid: str) -> bytes:
        response = self._post('cat', params={'arg': cid})
        return response.content

    def cat(self, cid: str) -> str:
        return self.cat_bytes(cid).decode('utf-8')

    def ls(self, cid: str) -> list[dict]:
        """List UnixFS links under ``cid`` (``Objects[0].Links``)."""
        response = self._post('ls', params={'arg': cid})
        payload = response.json()
        objects = payload.get('Objects') or []
        if not objects:
            return []
        return list(objects[0].get('Links') or [])

    def dag_export(self, cid: str, filepath: str) -> None:
        """Stream ``/api/v0/dag/export`` CAR bytes to ``filepath``."""
        response = self._post('dag/export', params={'arg': cid}, stream=True)
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('wb') as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)

    def get(self, cid: str, dest_path: str) -> str:
        """Fetch CID to ``dest_path``, matching CLI ``ipfs get CID --output dest``.

        HTTP ``/api/v0/get`` returns a tar archive; extract and place the single
        top-level member at ``dest_path`` (file or directory root).
        """
        response = self._post(
            'get',
            params={'arg': cid, 'archive': 'true'},
            stream=True,
        )
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Materialize archive then extract — tarfile needs seekable or full stream.
        archive_bytes = response.content
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:*') as tar:
                # filter= avoids Python 3.14 DeprecationWarning on extractall.
                try:
                    tar.extractall(tmp_root, filter='data')
                except TypeError:
                    tar.extractall(tmp_root)
            entries = [p for p in tmp_root.iterdir()]
            if not entries:
                raise RuntimeError(f'Kubo get returned empty archive for {cid!r}')
            if len(entries) == 1:
                extracted = entries[0]
            else:
                # Unexpected multi-root tar: stage into a folder then move.
                extracted = tmp_root / '_cats_get_root'
                extracted.mkdir()
                for entry in entries:
                    shutil.move(str(entry), str(extracted / entry.name))

            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(extracted), str(dest))
        return str(dest)

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


def connect(
    host: str | None = None,
    port: int | None = None,
    validate: bool = False,
):
    """Build CatsIPFSClient; host/port kwargs override IPFS_API_HOST / IPFS_API_PORT."""
    if host is None:
        host = os.environ.get('IPFS_API_HOST', '127.0.0.1')
    if port is None:
        port = int(os.environ.get('IPFS_API_PORT', '5001'))
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

    def cat_bytes(self, cid: str) -> bytes:
        return self._client.cat_bytes(cid)

    def cat(self, cid: str) -> str:
        return self._client.cat(cid)

    def ls(self, cid: str) -> list[dict]:
        return self._client.ls(cid)

    def dag_export(self, cid: str, filepath: str) -> None:
        return self._client.dag_export(cid, filepath)

    def get(self, cid: str, dest_path: str) -> str:
        return self._client.get(cid, dest_path)

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
