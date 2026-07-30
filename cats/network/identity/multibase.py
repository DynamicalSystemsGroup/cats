"""Multibase base58 (prefix ``z``) helpers for did:key / Data Integrity."""
from __future__ import annotations

# Spec: https://github.com/multiformats/multibase
_BASE58_ALPHABET = b'123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
_BASE58_INDEX = {c: i for i, c in enumerate(_BASE58_ALPHABET)}


def b58encode(data: bytes) -> str:
    """Encode bytes as multibase base58 (no checksum)."""
    n = int.from_bytes(data, 'big')
    chars = bytearray()
    while n > 0:
        n, rem = divmod(n, 58)
        chars.append(_BASE58_ALPHABET[rem])
    pad = 0
    for b in data:
        if b == 0:
            pad += 1
        else:
            break
    return ('1' * pad + chars.decode('ascii')[::-1]) if chars or pad else ''


def b58decode(text: str) -> bytes:
    """Decode multibase base58 (no checksum) to bytes."""
    if not text:
        return b''
    n = 0
    for ch in text.encode('ascii'):
        try:
            n = n * 58 + _BASE58_INDEX[ch]
        except KeyError as exc:
            raise ValueError(f'Invalid base58 character: {ch!r}') from exc
    # Reconstruct byte length including leading zeros ('1' → 0x00)
    pad = 0
    for ch in text:
        if ch == '1':
            pad += 1
        else:
            break
    body = n.to_bytes((n.bit_length() + 7) // 8, 'big') if n else b''
    return b'\x00' * pad + body


def multibase_z_encode(data: bytes) -> str:
    """Encode bytes as multibase with ``z`` (base58) prefix."""
    return 'z' + b58encode(data)


def multibase_z_decode(text: str) -> bytes:
    """Decode a multibase ``z…`` string to bytes."""
    if not text.startswith('z'):
        raise ValueError(f'Expected multibase z-prefix, got {text[:1]!r}')
    return b58decode(text[1:])
