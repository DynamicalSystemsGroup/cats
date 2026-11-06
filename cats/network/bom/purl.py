"""FRU catalog part numbers (Package URL). No envelope I/O.

Maps role + identity to the locked strings in ``bomsIntegration.md`` P1 /
``BOMs.md`` two-level identity. ``purl`` is not Typed Standards ``kid`` /
Node ``did:key``. Do not use CPE as the primary FRU id.
"""
from __future__ import annotations

from cats.network.cas.content_ref import equality_id
from cats.network.cas.digest import from_ni, is_legacy_cid, is_ni_or_digest

_CATS_ROLES = frozenset({'function', 'structure', 'dataset'})
_OCI_ROLE = 'oci'
_PYPI_ROLE = 'pypi'
_KNOWN_ROLES = _CATS_ROLES | {_OCI_ROLE, _PYPI_ROLE}
_SHA256_PREFIX = 'sha256:'


def fru_purl(
    role: str,
    content_id: str | None = None,
    *,
    name: str | None = None,
    version: str | None = None,
) -> str:
    """Return a catalog purl for ``role``.

    * ``function`` / ``structure`` / ``dataset`` — ``content_id`` (``ni:`` or
      hex) → ``pkg:generic/cats/{role}@{ni}``.
    * ``oci`` — ``name`` (image path) plus digest in ``content_id`` or
      ``version`` → ``pkg:oci/{name}@sha256:{hex}``.
    * ``pypi`` — ``name`` + ``version`` (PyPI version, not ``ni:``) →
      ``pkg:pypi/{name}@{version}``.
    """
    kind = (role or '').strip().lower()
    if kind not in _KNOWN_ROLES:
        raise ValueError(f'unknown FRU role: {role!r}')
    if kind in _CATS_ROLES:
        return f'pkg:generic/cats/{kind}@{_cats_ni(content_id)}'
    if kind == _OCI_ROLE:
        return _oci_purl(name, content_id=content_id, version=version)
    return _pypi_purl(name, version)


def _require_token(value: str | None, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} is required')
    return value.strip()


def _cats_ni(content_id: str | None) -> str:
    token = _require_token(content_id, label='content_id')
    if is_legacy_cid(token):
        raise ValueError(f'legacy CID is not a FRU lot id: {content_id!r}')
    if not is_ni_or_digest(token):
        raise ValueError(f'content_id must be ni: or hex sha-256: {content_id!r}')
    return equality_id(token)


def _digest_hex(token: str) -> str:
    value = token.strip()
    if value.lower().startswith(_SHA256_PREFIX):
        value = value[len(_SHA256_PREFIX) :]
    if is_legacy_cid(value):
        raise ValueError(f'legacy CID is not an OCI digest: {token!r}')
    if not is_ni_or_digest(value):
        raise ValueError(f'OCI digest must be ni: or hex sha-256: {token!r}')
    return from_ni(value)


def _oci_purl(
    name: str | None,
    *,
    content_id: str | None,
    version: str | None,
) -> str:
    image = _require_token(name, label='name')
    digest = content_id if content_id and str(content_id).strip() else version
    hex_digest = _digest_hex(_require_token(digest, label='content_id or version'))
    return f'pkg:oci/{image}@{_SHA256_PREFIX}{hex_digest}'


def _pypi_purl(name: str | None, version: str | None) -> str:
    pkg = _require_token(name, label='name')
    ver = _require_token(version, label='version')
    if is_ni_or_digest(ver) or ver.lower().startswith('ni:'):
        raise ValueError('pypi version must not be ni: / hex digest')
    return f'pkg:pypi/{pkg}@{ver}'
