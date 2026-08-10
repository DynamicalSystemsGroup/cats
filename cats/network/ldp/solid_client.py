"""Solid pod publisher for signed ExecutionBom envelopes (Phase 2a).

CSS-compatible HTTP PUT of ``application/ld+json`` under
``{SOLID_POD_BASE_URL}{SOLID_BOMS_PATH}/{bom_cid}``.

Auth (thin seam):
- ``SOLID_CLIENT_ACCESS_TOKEN`` → ``Authorization: Bearer …``
- else ``SOLID_CLIENT_ID`` + ``SOLID_CLIENT_SECRET`` → HTTP Basic

CID remains the data-plane address of record; the Solid URL is a control-plane
locator only.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any
from urllib.parse import urljoin

import requests

from cats.network.ldp.bom_store import _validate_bom_cid

logger = logging.getLogger(__name__)


class SolidPublishError(RuntimeError):
    """Raised when a Solid BOM publish fails."""


def solid_configured() -> bool:
    """True when ``SOLID_POD_BASE_URL`` is set (Solid dual-write enabled)."""
    return bool(os.environ.get('SOLID_POD_BASE_URL', '').strip())


def solid_boms_base_url() -> str:
    """Return ``{SOLID_POD_BASE_URL}{SOLID_BOMS_PATH}/`` (trailing slash)."""
    base = os.environ.get('SOLID_POD_BASE_URL', '').strip().rstrip('/')
    if not base:
        raise SolidPublishError('SOLID_POD_BASE_URL is not set')
    path = os.environ.get('SOLID_BOMS_PATH', '/boms').strip() or '/boms'
    if not path.startswith('/'):
        path = f'/{path}'
    path = path.rstrip('/')
    return f'{base}{path}/'


def bom_solid_uri(bom_cid: str) -> str:
    """Absolute Solid resource URI for ``bom_cid`` (no network I/O)."""
    cid = _validate_bom_cid(bom_cid)
    return urljoin(solid_boms_base_url(), cid)


def _auth_headers() -> dict[str, str]:
    token = os.environ.get('SOLID_CLIENT_ACCESS_TOKEN', '').strip()
    if token:
        return {'Authorization': f'Bearer {token}'}
    client_id = os.environ.get('SOLID_CLIENT_ID', '').strip()
    client_secret = os.environ.get('SOLID_CLIENT_SECRET', '').strip()
    if client_id and client_secret:
        raw = f'{client_id}:{client_secret}'.encode('utf-8')
        encoded = base64.b64encode(raw).decode('ascii')
        return {'Authorization': f'Basic {encoded}'}
    raise SolidPublishError(
        'Solid auth unset: set SOLID_CLIENT_ACCESS_TOKEN or '
        'SOLID_CLIENT_ID + SOLID_CLIENT_SECRET'
    )


class SolidBomPublisher:
    """PUT signed BOM envelopes to a CSS-compatible Solid pod."""

    def __init__(
        self,
        *,
        timeout: float = 60.0,
        session: requests.Session | None = None,
    ):
        self.timeout = timeout
        self._session = session or requests.Session()

    def publish(self, bom_cid: str, bom: dict[str, Any]) -> str:
        """PUT ``bom`` to the Solid boms container; return resource URI.

        Raises ``SolidPublishError`` on auth/config/HTTP failure (fail closed
        when Solid is configured).
        """
        uri = bom_solid_uri(bom_cid)
        headers = {
            **_auth_headers(),
            'Content-Type': 'application/ld+json',
            'Link': (
                '<http://www.w3.org/ns/ldp#Resource>; rel="type", '
                '<http://www.w3.org/ns/ldp#RDFSource>; rel="type"'
            ),
        }
        body = json.dumps(bom, indent=2, sort_keys=True) + '\n'
        try:
            response = self._session.put(
                uri,
                data=body.encode('utf-8'),
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise SolidPublishError(f'Solid PUT {uri} failed: {exc}') from exc
        if response.status_code in (401, 403):
            raise SolidPublishError(
                f'Solid PUT {uri} denied ({response.status_code}): '
                f'{response.text[:500]}'
            )
        if response.status_code >= 400:
            raise SolidPublishError(
                f'Solid PUT {uri} failed ({response.status_code}): '
                f'{response.text[:500]}'
            )
        logger.info('Published BOM envelope to Solid: %s', uri)
        return uri
