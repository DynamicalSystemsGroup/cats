"""Minimal CARv1 reader (trustless block store for UnixFS extract)."""
from __future__ import annotations

import base58
import hashlib
from typing import BinaryIO, Iterable, Mapping

import cbor2
from cid import CIDv0, CIDv1, make_cid
from cbor2 import CBORTag  # DAG-CBOR CID tag 42

from cats.network.address_store.cid_verify import normalize_cid


class CarError(ValueError):
    """Raised when a CARv1 payload cannot be parsed."""


def _decode_varint(buf: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    shift = 0
    i = offset
    while True:
        if i >= len(buf):
            raise CarError('truncated unsigned-varint')
        byte = buf[i]
        i += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, i
        shift += 7
        if shift > 63:
            raise CarError('unsigned-varint too long')


def _encode_varint(n: int) -> bytes:
    out = bytearray()
    while True:
        bit = n & 0x7F
        n >>= 7
        out.append(bit | (0x80 if n else 0))
        if not n:
            break
    return bytes(out)


def cid_bytes_to_str(cid_bytes: bytes) -> str:
    """Decode raw CID bytes (CIDv0 multihash or CIDv1) to a string."""
    if not cid_bytes:
        raise CarError('empty CID bytes')
    # CIDv0: bare sha2-256 multihash (0x12 0x20 || digest)
    if len(cid_bytes) == 34 and cid_bytes[0] == 0x12 and cid_bytes[1] == 0x20:
        return base58.b58encode(cid_bytes).decode('ascii')
    try:
        return str(make_cid(cid_bytes))
    except Exception as exc:
        raise CarError(f'invalid CID bytes: {cid_bytes[:16]!r}...') from exc


def _dag_cbor_cid_to_str(value) -> str:
    """Decode a DAG-CBOR CID (tag 42) or already-decoded bytes/string."""
    if isinstance(value, CBORTag):
        if value.tag != 42:
            raise CarError(f'unexpected CBOR tag for CID: {value.tag}')
        raw = value.value
        if not isinstance(raw, (bytes, bytearray)):
            raise CarError('CID tag 42 value must be bytes')
        # Identity multibase prefix 0x00
        if raw and raw[0] == 0x00:
            raw = bytes(raw[1:])
        return cid_bytes_to_str(bytes(raw))
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        if raw and raw[0] == 0x00:
            raw = raw[1:]
        return cid_bytes_to_str(raw)
    if isinstance(value, str):
        return normalize_cid(value)
    raise CarError(f'unsupported CID header value type: {type(value)!r}')


def _read_cid_prefix(buf: bytes, offset: int) -> tuple[str, int]:
    """Read a CIDv0 or CIDv1 from ``buf`` at ``offset``; return (cid_str, new_offset)."""
    if offset >= len(buf):
        raise CarError('truncated CID')
    # CIDv0
    if buf[offset] == 0x12:
        if offset + 34 > len(buf):
            raise CarError('truncated CIDv0')
        cid_bytes = buf[offset : offset + 34]
        if cid_bytes[1] != 0x20:
            raise CarError('unsupported CIDv0 multihash')
        return cid_bytes_to_str(cid_bytes), offset + 34
    # CIDv1: version | codec varint | multihash
    if buf[offset] != 0x01:
        raise CarError(f'unsupported CID version byte: {buf[offset]:#x}')
    i = offset + 1
    # codec varint
    _, i = _decode_varint(buf, i)
    # multihash: code varint + length varint + digest
    _, i = _decode_varint(buf, i)
    mh_len, i = _decode_varint(buf, i)
    end = i + mh_len
    if end > len(buf):
        raise CarError('truncated CIDv1 multihash')
    cid_bytes = buf[offset:end]
    return cid_bytes_to_str(cid_bytes), end


def block_cid(block: bytes, *, codec: str = 'dag-pb') -> str:
    """Return CIDv0 (dag-pb) or CIDv1-raw string for ``block`` bytes."""
    digest = hashlib.sha256(block).digest()
    mh = bytes([0x12, 0x20]) + digest
    if codec == 'dag-pb':
        return base58.b58encode(mh).decode('ascii')
    if codec == 'raw':
        encoded = CIDv1('raw', mh).encode('base32')
        return encoded.decode('ascii') if isinstance(encoded, bytes) else str(encoded)
    raise CarError(f'unsupported codec for block_cid: {codec!r}')


def read_car(data: bytes | BinaryIO) -> tuple[list[str], dict[str, bytes]]:
    """Parse CARv1 into ``(root_cid_strings, {cid_str: block_bytes})``."""
    if not isinstance(data, (bytes, bytearray)):
        data = data.read()
    buf = bytes(data)
    if not buf:
        raise CarError('empty CAR')

    header_len, i = _decode_varint(buf, 0)
    header_end = i + header_len
    if header_end > len(buf):
        raise CarError('truncated CAR header')
    try:
        header = cbor2.loads(buf[i:header_end])
    except Exception as exc:
        raise CarError('invalid CAR header CBOR') from exc
    if not isinstance(header, dict):
        raise CarError('CAR header must be a map')
    if header.get('version') != 1:
        raise CarError(f'unsupported CAR version: {header.get("version")!r}')
    roots_raw = header.get('roots') or []
    if not isinstance(roots_raw, list):
        raise CarError('CAR roots must be a list')
    roots = [_dag_cbor_cid_to_str(r) for r in roots_raw]

    blocks: dict[str, bytes] = {}
    i = header_end
    while i < len(buf):
        section_len, i = _decode_varint(buf, i)
        section_end = i + section_len
        if section_end > len(buf):
            raise CarError('truncated CAR section')
        cid_str, j = _read_cid_prefix(buf, i)
        block = buf[j:section_end]
        blocks[normalize_cid(cid_str)] = block
        # Also index CIDv1 form when we stored CIDv0 (equality handled by callers).
        i = section_end

    return roots, blocks


def _cid_binary(cid_str: str) -> bytes:
    """Raw CID bytes as stored in CAR sections (CIDv0 multihash or CIDv1 buffer)."""
    c = make_cid(normalize_cid(cid_str))
    if isinstance(c, CIDv0) or getattr(c, 'version', None) == 0:
        mh = c.multihash
        return bytes(mh) if not isinstance(mh, bytes) else mh
    buf = getattr(c, 'buffer', None)
    if buf is not None:
        return bytes(buf)
    return c.to_bytes()


def write_car(
    roots: Iterable[str],
    blocks: Mapping[str, bytes] | Iterable[tuple[str, bytes]],
) -> bytes:
    """Encode a minimal CARv1 (used by tests and optional helpers)."""
    root_list = list(roots)
    if isinstance(blocks, Mapping):
        block_items = list(blocks.items())
    else:
        block_items = list(blocks)

    header_obj = {
        'version': 1,
        'roots': [CBORTag(42, b'\x00' + _cid_binary(r)) for r in root_list],
    }
    header = cbor2.dumps(header_obj)
    out = bytearray()
    out.extend(_encode_varint(len(header)))
    out.extend(header)
    for cid_str, block in block_items:
        cid_bin = _cid_binary(cid_str)
        section = cid_bin + block
        out.extend(_encode_varint(len(section)))
        out.extend(section)
    return bytes(out)
