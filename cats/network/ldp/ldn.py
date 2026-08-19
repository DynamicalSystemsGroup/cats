"""Linked Data Notifications announce for Solid BOM publish (Phase 2a / §6f).

After a successful Solid PUT, POST a minimal notification to configured
Inbox URLs (``SOLID_LDN_INBOX_URLS``, comma-separated). Best-effort: log
failures; never raise to the caller of Runtime.execute.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


def ldn_inbox_urls() -> list[str]:
    """Parse ``SOLID_LDN_INBOX_URLS`` (comma-separated absolute URLs)."""
    raw = os.environ.get('SOLID_LDN_INBOX_URLS', '').strip()
    if not raw:
        return []
    urls: list[str] = []
    for part in raw.split(','):
        url = part.strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            logger.warning('Ignoring invalid SOLID_LDN_INBOX_URL: %s', url)
            continue
        urls.append(url)
    return urls


def build_bom_announcement(
    *,
    content_id: str,
    bom_solid_uri: str,
    hl: str | None = None,
) -> dict[str, Any]:
    """Minimal JSON-LD Activity/Notification (``content_id`` + optional ``hl``)."""
    context: list[Any] = [
        'https://www.w3.org/ns/activitystreams',
        {
            'content_id': 'https://w3id.org/cats#contentId',
            'bom_solid_uri': 'https://w3id.org/cats#bomSolidUri',
            'hl': 'https://w3id.org/cats#hl',
        },
    ]
    note: dict[str, Any] = {
        '@context': context,
        '@type': 'Announce',
        'object': {'@id': bom_solid_uri},
        'content_id': content_id,
        'bom_solid_uri': bom_solid_uri,
    }
    if hl:
        note['hl'] = hl
    return note


def announce_bom(
    inbox_urls: list[str] | None,
    content_id: str,
    bom_solid_uri: str,
    *,
    hl: str | None = None,
    timeout: float = 30.0,
    session: requests.Session | None = None,
) -> list[str]:
    """POST announcement to each inbox; return list of successful inbox URLs.

    Never raises for network/HTTP errors — logs and continues.
    """
    targets = inbox_urls if inbox_urls is not None else ldn_inbox_urls()
    if not targets:
        return []
    body = build_bom_announcement(
        content_id=content_id,
        bom_solid_uri=bom_solid_uri,
        hl=hl,
    )
    payload = json.dumps(body, indent=2, sort_keys=True) + '\n'
    http = session or requests.Session()
    headers = {
        'Content-Type': 'application/ld+json',
    }
    ok: list[str] = []
    for inbox in targets:
        try:
            response = http.post(
                inbox,
                data=payload.encode('utf-8'),
                headers=headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            logger.warning('LDN POST %s failed: %s', inbox, exc)
            continue
        if response.status_code >= 400:
            logger.warning(
                'LDN POST %s failed (%s): %s',
                inbox,
                response.status_code,
                response.text[:300],
            )
            continue
        ok.append(inbox)
        logger.info('LDN announced content_id=%s to %s', content_id, inbox)
    return ok
