"""WAC bootstrap for the Solid BOM container (Phase 2a).

Creates the BOM container (if needed) and a minimal ACL granting the Node
agent ``acl:Write`` / ``acl:Append`` and configured readers ``acl:Read``.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import urljoin

import requests

from cats.network.identity.webid import webid_uri, write_webid_document
from cats.network.ldp.solid_client import (
    SolidPublishError,
    _auth_headers,
    solid_boms_base_url,
    solid_configured,
)

logger = logging.getLogger(__name__)


def _reader_webids() -> list[str]:
    raw = os.environ.get('SOLID_BOM_READERS', '').strip()
    if not raw:
        # Public Read when no readers configured (stewardship default).
        return ['http://xmlns.com/foaf/0.1/Agent']
    return [part.strip() for part in raw.split(',') if part.strip()]


def build_bom_container_acl(
    *,
    resource_uri: str,
    agent_webid: str,
    readers: list[str] | None = None,
) -> dict[str, Any]:
    """Build a WAC ACL document (JSON-LD) for the BOM container."""
    read_agents = readers if readers is not None else _reader_webids()
    authorizations: list[dict[str, Any]] = [
        {
            '@type': 'acl:Authorization',
            'acl:accessTo': {'@id': resource_uri},
            'acl:default': {'@id': resource_uri},
            'acl:agent': {'@id': agent_webid},
            'acl:mode': [
                {'@id': 'acl:Read'},
                {'@id': 'acl:Write'},
                {'@id': 'acl:Append'},
                {'@id': 'acl:Control'},
            ],
        }
    ]
    for reader in read_agents:
        if reader == agent_webid:
            continue
        mode_entry: dict[str, Any] = {
            '@type': 'acl:Authorization',
            'acl:accessTo': {'@id': resource_uri},
            'acl:default': {'@id': resource_uri},
            'acl:mode': [{'@id': 'acl:Read'}],
        }
        if reader == 'http://xmlns.com/foaf/0.1/Agent':
            mode_entry['acl:agentClass'] = {'@id': reader}
        else:
            mode_entry['acl:agent'] = {'@id': reader}
        authorizations.append(mode_entry)
    return {
        '@context': {
            'acl': 'http://www.w3.org/ns/auth/acl#',
            'foaf': 'http://xmlns.com/foaf/0.1/',
        },
        '@graph': authorizations,
    }


def ensure_solid_bom_acl(
    *,
    cats_home: str | None = None,
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> str:
    """Create BOM container + WAC ACL on the configured Solid pod.

    Returns the BOM container URI. No-op (returns '') when Solid is unset.
    Raises ``SolidPublishError`` on HTTP failure when Solid is configured.
    """
    if not solid_configured():
        logger.debug('Solid unset; skip ensure_solid_bom_acl')
        return ''

    write_webid_document(cats_home=cats_home)
    agent = webid_uri(cats_home)
    container = solid_boms_base_url()
    http = session or requests.Session()
    headers = {
        **_auth_headers(),
        'Content-Type': 'text/turtle',
        'Link': (
            '<http://www.w3.org/ns/ldp#BasicContainer>; rel="type"'
        ),
    }
    # Ensure container exists (PUT empty turtle / slug).
    try:
        put_c = http.put(
            container.rstrip('/') + '/',
            data=b'',
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise SolidPublishError(
            f'Solid BOM container PUT {container} failed: {exc}'
        ) from exc
    if put_c.status_code in (401, 403):
        raise SolidPublishError(
            f'Solid BOM container PUT denied ({put_c.status_code}): '
            f'{put_c.text[:500]}'
        )
    # 200/201/204/405 (already exists / method) are acceptable.
    if put_c.status_code >= 400 and put_c.status_code not in (405, 409):
        # Some CSS versions use POST to parent; try HEAD then continue.
        head = http.head(container, headers=_auth_headers(), timeout=timeout)
        if head.status_code >= 400:
            raise SolidPublishError(
                f'Solid BOM container unavailable ({put_c.status_code}): '
                f'{put_c.text[:500]}'
            )

    acl_uri = urljoin(container, '.acl')
    # Prefer resource URI without trailing slash inconsistency.
    resource_uri = container.rstrip('/') + '/'
    acl_doc = build_bom_container_acl(
        resource_uri=resource_uri,
        agent_webid=agent,
    )
    acl_headers = {
        **_auth_headers(),
        'Content-Type': 'application/ld+json',
        'Link': '<http://www.w3.org/ns/auth/acl#AccessControl>; rel="type"',
    }
    try:
        put_acl = http.put(
            acl_uri,
            data=(json.dumps(acl_doc, indent=2) + '\n').encode('utf-8'),
            headers=acl_headers,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise SolidPublishError(
            f'Solid ACL PUT {acl_uri} failed: {exc}'
        ) from exc
    if put_acl.status_code in (401, 403):
        raise SolidPublishError(
            f'Solid ACL PUT denied ({put_acl.status_code}): '
            f'{put_acl.text[:500]}'
        )
    if put_acl.status_code >= 400:
        raise SolidPublishError(
            f'Solid ACL PUT {acl_uri} failed ({put_acl.status_code}): '
            f'{put_acl.text[:500]}'
        )
    logger.info('Ensured Solid BOM ACL at %s for agent %s', acl_uri, agent)
    return resource_uri


if __name__ == '__main__':
    import sys

    uri = ensure_solid_bom_acl()
    if not uri:
        print('SOLID_POD_BASE_URL unset; nothing to do', file=sys.stderr)
        sys.exit(1)
    print(uri)
