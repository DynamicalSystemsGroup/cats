"""CAT Node DID attribution and signing material (did:key; Phase 1b)."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cats.network.identity.multibase import multibase_z_encode

# Multicodec prefix for ed25519-pub (https://github.com/multiformats/multicodec)
ED25519_PUB_PREFIX = b'\xed\x01'


def ed25519_public_key_to_did_key(public_key_bytes: bytes) -> str:
    """Build ``did:key:z…`` from a raw 32-byte Ed25519 public key."""
    if len(public_key_bytes) != 32:
        raise ValueError(
            f'Ed25519 public key must be 32 bytes, got {len(public_key_bytes)}'
        )
    multibase = multibase_z_encode(ED25519_PUB_PREFIX + public_key_bytes)
    return f'did:key:{multibase}'


def did_key_verification_method(did: str) -> str:
    """Return ``did:key:…#…`` verificationMethod for a did:key DID."""
    if not did.startswith('did:key:'):
        raise ValueError(f'Expected did:key DID, got {did!r}')
    multibase = did[len('did:key:'):]
    return f'{did}#{multibase}'


def _default_cats_home() -> str:
    env_home = os.environ.get('CATS_HOME')
    if env_home:
        return env_home
    # Repo root: cats/network/identity/node_did.py → parents[3]
    return str(Path(__file__).resolve().parents[3])


def _key_path(cats_home: str) -> Path:
    return Path(cats_home) / '.cats' / 'node_did.json'


def _write_keyfile(
    path: Path,
    *,
    did: str,
    public_bytes: bytes,
    private_bytes: bytes,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                'did': did,
                'public_key_b64': base64.b64encode(public_bytes).decode('ascii'),
                'private_key_b64': base64.b64encode(private_bytes).decode('ascii'),
                'type': 'Ed25519',
            },
            indent=2,
        )
        + '\n',
        encoding='utf-8',
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _create_keyfile(cats_home: str) -> tuple[str, Ed25519PrivateKey]:
    path = _key_path(cats_home)
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    did = ed25519_public_key_to_did_key(public_bytes)
    _write_keyfile(
        path,
        did=did,
        public_bytes=public_bytes,
        private_bytes=private_bytes,
    )
    return did, private_key


def _read_keyfile(path: Path) -> tuple[str, Ed25519PrivateKey]:
    data = json.loads(path.read_text(encoding='utf-8'))
    did = data.get('did')
    private_b64 = data.get('private_key_b64')
    if not isinstance(did, str) or not did.startswith('did:'):
        raise ValueError(f'Invalid DID material in {path}')
    if not isinstance(private_b64, str) or not private_b64:
        raise ValueError(
            f'Keyfile {path} is missing private_key_b64; '
            'Phase 1b signing requires local key material'
        )
    private_bytes = base64.b64decode(private_b64)
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    return did, private_key


def _load_or_create_did(cats_home: str) -> str:
    path = _key_path(cats_home)
    if path.is_file():
        did, _ = _read_keyfile(path)
        return did
    did, _ = _create_keyfile(cats_home)
    return did


def load_node_signing_material(
    cats_home: str | None = None,
) -> tuple[str, Ed25519PrivateKey]:
    """Load (or create) Node DID + Ed25519 private key for Data Integrity.

    Signing always requires ``{CATS_HOME}/.cats/node_did.json``.

    - If the keyfile is missing and ``CAT_NODE_DID`` is unset, create a new
      ``did:key`` keyfile.
    - If ``CAT_NODE_DID`` is set and the keyfile is missing, raise — env DID
      alone is attribution-only and cannot sign.
    - If ``CAT_NODE_DID`` is set and differs from the keyfile DID, raise.
    """
    home = cats_home if cats_home is not None else _default_cats_home()
    path = _key_path(home)
    env_did = os.environ.get('CAT_NODE_DID')
    if env_did is not None:
        if not env_did.startswith('did:'):
            raise ValueError(
                f'CAT_NODE_DID must start with \"did:\", got {env_did!r}'
            )
        if not path.is_file():
            raise ValueError(
                'CAT_NODE_DID is set but no local keyfile exists at '
                f'{path}; Phase 1b signing requires '
                '{CATS_HOME}/.cats/node_did.json private key material '
                '(env DID alone is attribution-only)'
            )
        did, private_key = _read_keyfile(path)
        if did != env_did:
            raise ValueError(
                f'CAT_NODE_DID ({env_did!r}) does not match keyfile DID '
                f'({did!r}) at {path}; refuse to sign under mismatched '
                'attribution'
            )
        return did, private_key

    if path.is_file():
        return _read_keyfile(path)
    return _create_keyfile(home)


def node_did(cats_home: str | None = None) -> str:
    """Return the CAT Node DID for BOM attribution.

    Resolution order:
    1. ``CAT_NODE_DID`` environment variable (must start with ``did:``)
    2. Persisted ``did:key`` under ``{CATS_HOME}/.cats/node_did.json``
       (created on first use)

    HTTP Flask bind stays on ``cats.network.node_http``. Signing uses
    ``load_node_signing_material`` (keyfile required).
    """
    env_did = os.environ.get('CAT_NODE_DID')
    if env_did:
        if not env_did.startswith('did:'):
            raise ValueError(
                f'CAT_NODE_DID must start with \"did:\", got {env_did!r}'
            )
        return env_did
    home = cats_home if cats_home is not None else _default_cats_home()
    return _load_or_create_did(home)
