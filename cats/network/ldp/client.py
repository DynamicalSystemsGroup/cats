"""Fetch LDP / Solid BOM envelopes and verify Data Integrity proofs.

Accepts Node ``/ldp/boms/…`` URLs and Solid pod URLs — same GET +
``verify_execution_bom`` path (no protocol fork).
"""
from __future__ import annotations

from typing import Any

import requests

from cats.network.feedback import verify_execution_bom


class LdpEnvelopeError(RuntimeError):
    """Raised when an LDP/Solid BOM envelope cannot be fetched or verified."""


def fetch_bom_envelope(
    url: str,
    *,
    timeout: float = 60.0,
    session: requests.Session | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """GET ``url``, parse JSON-LD, verify ExecutionBom proof (fail closed).

    Works for Node LDP cache URIs and Solid pod URIs. Optional ``headers``
    (e.g. Solid Bearer) are forwarded on the GET.
    """
    http = session or requests.Session()
    try:
        response = http.get(url, timeout=timeout, headers=headers or {})
    except requests.RequestException as exc:
        raise LdpEnvelopeError(f'BOM envelope GET {url} failed: {exc}') from exc
    if response.status_code >= 400:
        raise LdpEnvelopeError(
            f'BOM envelope GET {url} failed ({response.status_code}): '
            f'{response.text[:500]}'
        )
    try:
        bom = response.json()
    except ValueError as exc:
        raise LdpEnvelopeError(
            f'BOM envelope GET {url} returned non-JSON'
        ) from exc
    if not isinstance(bom, dict):
        raise LdpEnvelopeError(
            f'BOM envelope GET {url} returned non-object JSON'
        )
    try:
        verify_execution_bom(bom)
    except Exception as exc:
        raise LdpEnvelopeError(
            f'BOM envelope at {url} failed Data Integrity verify: {exc}'
        ) from exc
    return bom
