"""Materialize UnixFS File / Directory trees from a CAR block store."""
from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO, Mapping, NamedTuple

from cats.network.address_store.car_v1 import CarError, block_cid, read_car
from cats.network.address_store.cid_verify import (
    normalize_cid,
    verify_bytes_match_cid,
)
from cats.network.address_store.unixfs_cid import local_cids_equal

# UnixFS DataType enum
_UNIXFS_RAW = 0
_UNIXFS_DIRECTORY = 1
_UNIXFS_FILE = 2
_UNIXFS_METADATA = 3
_UNIXFS_SYMLINK = 4
_UNIXFS_HAMT = 5


class UnixfsExtractError(ValueError):
    """Raised when a UnixFS DAG cannot be extracted (unsupported or corrupt)."""


class _PbLink(NamedTuple):
    hash_bytes: bytes
    name: str
    tsize: int


class _PbNode(NamedTuple):
    data: bytes
    links: list[_PbLink]


class _UnixfsData(NamedTuple):
    type: int
    data: bytes
    filesize: int | None
    blocksizes: list[int]


def _decode_varint(buf: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    shift = 0
    i = offset
    while True:
        if i >= len(buf):
            raise UnixfsExtractError('truncated protobuf varint')
        byte = buf[i]
        i += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, i
        shift += 7
        if shift > 63:
            raise UnixfsExtractError('protobuf varint too long')


def _decode_pb_fields(buf: bytes) -> list[tuple[int, int, bytes | int]]:
    """Return list of (field_number, wire_type, value_or_bytes)."""
    fields: list[tuple[int, int, bytes | int]] = []
    i = 0
    while i < len(buf):
        key, i = _decode_varint(buf, i)
        field = key >> 3
        wire = key & 0x07
        if wire == 0:  # varint
            val, i = _decode_varint(buf, i)
            fields.append((field, wire, val))
        elif wire == 2:  # length-delimited
            length, i = _decode_varint(buf, i)
            end = i + length
            if end > len(buf):
                raise UnixfsExtractError('truncated protobuf bytes field')
            fields.append((field, wire, buf[i:end]))
            i = end
        else:
            raise UnixfsExtractError(f'unsupported protobuf wire type: {wire}')
    return fields


def decode_dag_pb_node(block: bytes) -> _PbNode:
    """Decode a dag-pb PBNode."""
    data = b''
    links: list[_PbLink] = []
    for field, _wire, value in _decode_pb_fields(block):
        if field == 1 and isinstance(value, (bytes, bytearray)):
            data = bytes(value)
        elif field == 2 and isinstance(value, (bytes, bytearray)):
            links.append(_decode_pb_link(bytes(value)))
    return _PbNode(data=data, links=links)


def _decode_pb_link(buf: bytes) -> _PbLink:
    hash_bytes = b''
    name = ''
    tsize = 0
    for field, _wire, value in _decode_pb_fields(buf):
        if field == 1 and isinstance(value, (bytes, bytearray)):
            hash_bytes = bytes(value)
        elif field == 2 and isinstance(value, (bytes, bytearray)):
            name = bytes(value).decode('utf-8')
        elif field == 3 and isinstance(value, int):
            tsize = value
    if not hash_bytes:
        raise UnixfsExtractError('PBLink missing Hash')
    return _PbLink(hash_bytes=hash_bytes, name=name, tsize=tsize)


def decode_unixfs_data(buf: bytes) -> _UnixfsData:
    """Decode UnixFS Data protobuf."""
    typ = _UNIXFS_FILE
    data = b''
    filesize: int | None = None
    blocksizes: list[int] = []
    for field, _wire, value in _decode_pb_fields(buf):
        if field == 1 and isinstance(value, int):
            typ = value
        elif field == 2 and isinstance(value, (bytes, bytearray)):
            data = bytes(value)
        elif field == 3 and isinstance(value, int):
            filesize = value
        elif field == 4 and isinstance(value, int):
            blocksizes.append(value)
    return _UnixfsData(
        type=typ, data=data, filesize=filesize, blocksizes=blocksizes
    )


def _link_cid_str(hash_bytes: bytes) -> str:
    from cats.network.address_store.car_v1 import cid_bytes_to_str

    return cid_bytes_to_str(hash_bytes)


def _lookup_block(blocks: Mapping[str, bytes], cid: str) -> bytes:
    key = normalize_cid(cid)
    if key in blocks:
        return blocks[key]
    # v0/v1 tolerant scan
    for stored, block in blocks.items():
        if local_cids_equal(stored, key):
            return block
    raise UnixfsExtractError(f'missing block for CID {cid!r}')


def _assert_block_matches_cid(block: bytes, cid: str) -> None:
    computed = block_cid(block, codec='dag-pb')
    if local_cids_equal(computed, cid):
        return
    # raw leaves (leftover 3 not pinned yet, but tolerate if present)
    raw = block_cid(block, codec='raw')
    if local_cids_equal(raw, cid):
        return
    raise UnixfsExtractError(
        f'block does not match CID: expected {cid!r}, computed {computed!r}'
    )


def _safe_child_name(name: str) -> str:
    if not name or name in ('.', '..') or '/' in name or '\\' in name or '\x00' in name:
        raise UnixfsExtractError(f'unsafe UnixFS link name: {name!r}')
    return name


def _read_file_bytes(
    cid: str,
    blocks: Mapping[str, bytes],
    *,
    ipfs_client: Any = None,
) -> bytes:
    block = _lookup_block(blocks, cid)
    _assert_block_matches_cid(block, cid)
    # raw codec: entire block is file bytes
    try:
        from cid import make_cid

        c = make_cid(normalize_cid(cid))
        if getattr(c, 'codec', None) == 'raw' or (
            isinstance(getattr(c, 'codec', None), str) and 'raw' in str(c.codec)
        ):
            verify_bytes_match_cid(ipfs_client, cid, block)
            return block
    except Exception:
        pass

    node = decode_dag_pb_node(block)
    if not node.data and not node.links:
        # empty dag-pb?
        data = b''
        verify_bytes_match_cid(ipfs_client, cid, data)
        return data
    if not node.data:
        raise UnixfsExtractError(f'file node {cid!r} missing UnixFS Data')
    ufs = decode_unixfs_data(node.data)
    if ufs.type == _UNIXFS_RAW:
        data = ufs.data
    elif ufs.type != _UNIXFS_FILE:
        raise UnixfsExtractError(
            f'expected UnixFS File at {cid!r}, got type={ufs.type}'
        )
    elif node.links:
        parts: list[bytes] = []
        for link in node.links:
            child_cid = _link_cid_str(link.hash_bytes)
            parts.append(
                _read_file_bytes(child_cid, blocks, ipfs_client=ipfs_client)
            )
        data = b''.join(parts)
        if ufs.data:
            # unusual: intermediate with inline data — prepend
            data = ufs.data + data
    else:
        data = ufs.data

    if ufs.filesize is not None and len(data) != ufs.filesize:
        raise UnixfsExtractError(
            f'file size mismatch at {cid!r}: got {len(data)}, '
            f'unixfs filesize={ufs.filesize}'
        )
    verify_bytes_match_cid(ipfs_client, cid, data)
    return data


def _extract_node(
    cid: str,
    blocks: Mapping[str, bytes],
    dest_path: Path,
    *,
    ipfs_client: Any = None,
) -> None:
    block = _lookup_block(blocks, cid)
    _assert_block_matches_cid(block, cid)
    node = decode_dag_pb_node(block)
    if not node.data:
        raise UnixfsExtractError(f'node {cid!r} missing UnixFS Data')
    ufs = decode_unixfs_data(node.data)

    if ufs.type in (_UNIXFS_FILE, _UNIXFS_RAW):
        data = _read_file_bytes(cid, blocks, ipfs_client=ipfs_client)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.exists():
            if dest_path.is_dir():
                raise UnixfsExtractError(
                    f'dest is a directory, expected file: {dest_path}'
                )
            dest_path.unlink()
        dest_path.write_bytes(data)
        return

    if ufs.type == _UNIXFS_DIRECTORY:
        if dest_path.exists() and not dest_path.is_dir():
            dest_path.unlink()
        dest_path.mkdir(parents=True, exist_ok=True)
        for link in node.links:
            name = _safe_child_name(link.name)
            child_cid = _link_cid_str(link.hash_bytes)
            _extract_node(
                child_cid,
                blocks,
                dest_path / name,
                ipfs_client=ipfs_client,
            )
        return

    raise UnixfsExtractError(
        f'unsupported UnixFS type {ufs.type} at {cid!r} '
        f'(HAMT/symlink/metadata fall back to RPC)'
    )


def extract_unixfs(
    cid: str,
    blocks: Mapping[str, bytes],
    dest_path: str,
    *,
    ipfs_client: Any = None,
) -> str:
    """Materialize UnixFS CID from ``blocks`` into ``dest_path``."""
    dest = Path(dest_path)
    _extract_node(
        normalize_cid(cid), blocks, dest, ipfs_client=ipfs_client
    )
    return str(dest)


def extract_unixfs_from_car(
    car: bytes | BinaryIO | str | Path,
    cid: str,
    dest_path: str,
    *,
    ipfs_client: Any = None,
) -> str:
    """Read a CARv1 and materialize ``cid`` to ``dest_path``."""
    if isinstance(car, (str, Path)):
        data = Path(car).read_bytes()
    else:
        data = car
    try:
        _roots, blocks = read_car(data)
    except CarError as exc:
        raise UnixfsExtractError(str(exc)) from exc
    return extract_unixfs(
        cid, blocks, dest_path, ipfs_client=ipfs_client
    )
