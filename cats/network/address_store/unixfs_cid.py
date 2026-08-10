"""Pure-Python UnixFS File CID (Kubo default ``add`` / ``only-hash``).

Supports single-block and multi-block **balanced** dag-pb File layouts
(chunker ``size-262144``, max 174 links per node, dag-pb leaves — not raw).
"""
from __future__ import annotations

import hashlib
from typing import Iterable, Iterator, List, Sequence, Tuple

import base58
from cid import CIDv1, make_cid


# Kubo default chunker size.
DEFAULT_CHUNK_SIZE = 262_144
# go-unixfs / boxo DefaultLinksPerBlock (8192 / 47 ≈ 174).
DEFAULT_LINKS_PER_BLOCK = 174


class UnixfsEncodeError(ValueError):
    """Raised when bytes cannot be encoded as a supported UnixFS File layout."""


def _encode_varint(n: int) -> bytes:
    out = bytearray()
    while True:
        bit = n & 0x7F
        n >>= 7
        out.append(bit | (0x80 if n else 0))
        if not n:
            break
    return bytes(out)


def _proto_bytes(field: int, data: bytes) -> bytes:
    tag = (field << 3) | 2
    return _encode_varint(tag) + _encode_varint(len(data)) + data


def _proto_varint(field: int, value: int) -> bytes:
    tag = (field << 3) | 0
    return _encode_varint(tag) + _encode_varint(value)


def _proto_string(field: int, value: str) -> bytes:
    return _proto_bytes(field, value.encode('utf-8'))


def encode_unixfs_file(data: bytes) -> bytes:
    """Serialize UnixFS ``Data`` protobuf for a single-chunk File leaf."""
    body = _proto_varint(1, 2)  # Type = File
    if data:
        body += _proto_bytes(2, data)
    body += _proto_varint(3, len(data))  # filesize
    return body


def encode_unixfs_file_intermediate(
    filesize: int, blocksizes: Sequence[int]
) -> bytes:
    """Serialize UnixFS ``Data`` for an intermediate File node (no inline Data)."""
    body = _proto_varint(1, 2)  # Type = File
    body += _proto_varint(3, filesize)
    for blocksize in blocksizes:
        body += _proto_varint(4, blocksize)
    return body


def encode_dag_pb_node(unixfs_data: bytes) -> bytes:
    """Serialize dag-pb ``PBNode`` with ``Data`` and no links."""
    return _proto_bytes(1, unixfs_data)


def encode_dag_pb_node_with_links(
    unixfs_data: bytes,
    links: Sequence[Tuple[bytes, int]],
) -> bytes:
    """Serialize dag-pb ``PBNode`` with Links then Data (Kubo wire order).

    Each link is ``(multihash_bytes, tsize)`` with an empty ``Name`` (``""``).
    """
    parts: List[bytes] = []
    for multihash, tsize in links:
        link = _proto_bytes(1, multihash)
        link += _proto_string(2, '')
        link += _proto_varint(3, tsize)
        parts.append(_proto_bytes(2, link))
    parts.append(_proto_bytes(1, unixfs_data))
    return b''.join(parts)


def sha256_multihash(block: bytes) -> bytes:
    digest = hashlib.sha256(block).digest()
    return bytes([0x12, 0x20]) + digest


def _cid_from_block(block: bytes, *, version: int = 0) -> str:
    mh = sha256_multihash(block)
    if version == 0:
        return base58.b58encode(mh).decode('ascii')
    if version == 1:
        encoded = CIDv1('dag-pb', mh).encode('base32')
        return encoded.decode('ascii') if isinstance(encoded, bytes) else str(encoded)
    raise ValueError(f'unsupported CID version: {version!r}')


class _DagNode:
    __slots__ = ('block', 'file_size', 'cum_size', 'multihash')

    def __init__(self, block: bytes, file_size: int):
        self.block = block
        self.file_size = file_size
        self.multihash = sha256_multihash(block)
        # ipld Size() = len(encoded node) + sum(link.Tsize); leaves have no links.
        self.cum_size = len(block)


def _make_leaf(data: bytes) -> _DagNode:
    block = encode_dag_pb_node(encode_unixfs_file(data))
    node = _DagNode(block, len(data))
    node.cum_size = len(block)
    return node


def _commit_internal(children: Sequence[_DagNode]) -> _DagNode:
    filesize = sum(child.file_size for child in children)
    blocksizes = [child.file_size for child in children]
    unixfs = encode_unixfs_file_intermediate(filesize, blocksizes)
    links = [(child.multihash, child.cum_size) for child in children]
    block = encode_dag_pb_node_with_links(unixfs, links)
    node = _DagNode(block, filesize)
    node.cum_size = len(block) + sum(child.cum_size for child in children)
    return node


def _iter_fixed_chunks(data: bytes) -> Iterator[bytes]:
    for i in range(0, len(data), DEFAULT_CHUNK_SIZE):
        yield data[i : i + DEFAULT_CHUNK_SIZE]


def _normalize_chunk_stream(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Yield ``DEFAULT_CHUNK_SIZE`` slices from an arbitrary byte iterable."""
    buf = bytearray()
    for piece in chunks:
        if not piece:
            continue
        buf.extend(piece)
        while len(buf) >= DEFAULT_CHUNK_SIZE:
            yield bytes(buf[:DEFAULT_CHUNK_SIZE])
            del buf[:DEFAULT_CHUNK_SIZE]
    if buf:
        yield bytes(buf)


class _ChunkSource:
    def __init__(self, chunks: Iterator[bytes]):
        self._chunks = chunks
        self._pending: bytes | None = None
        self._exhausted = False
        self._advance()

    def _advance(self) -> None:
        if self._exhausted:
            self._pending = None
            return
        try:
            self._pending = next(self._chunks)
        except StopIteration:
            self._pending = None
            self._exhausted = True

    def done(self) -> bool:
        return self._pending is None

    def next_leaf(self) -> _DagNode:
        if self._pending is None:
            raise UnixfsEncodeError('no more chunks')
        leaf = _make_leaf(self._pending)
        self._advance()
        return leaf


def _fill_node_rec(
    src: _ChunkSource,
    children: List[_DagNode],
    depth: int,
    *,
    max_links: int,
) -> _DagNode:
    while len(children) < max_links and not src.done():
        if depth == 1:
            children.append(src.next_leaf())
        else:
            children.append(
                _fill_node_rec(src, [], depth - 1, max_links=max_links)
            )
    return _commit_internal(children)


def _balanced_root_from_chunks(
    chunks: Iterator[bytes],
    *,
    max_links: int = DEFAULT_LINKS_PER_BLOCK,
) -> _DagNode:
    """Build root dag-pb node matching go-unixfs balanced.Layout."""
    src = _ChunkSource(chunks)
    if src.done():
        return _make_leaf(b'')

    root = src.next_leaf()
    depth = 1
    while not src.done():
        root = _fill_node_rec(src, [root], depth, max_links=max_links)
        depth += 1
    return root


def compute_unixfs_file_cid(data: bytes, *, version: int = 0) -> str:
    """Return CIDv0 (default) or CIDv1-dag-pb for UnixFS File bytes.

    Matches Kubo ``ipfs add`` / ``add?only-hash=true`` for the default importer
    (``size-262144``, balanced, dag-pb leaves). Single-block and multi-block.
    """
    if len(data) <= DEFAULT_CHUNK_SIZE:
        block = encode_dag_pb_node(encode_unixfs_file(data))
        return _cid_from_block(block, version=version)
    root = _balanced_root_from_chunks(_iter_fixed_chunks(data))
    return _cid_from_block(root.block, version=version)


def compute_unixfs_file_cid_from_chunks(
    chunks: Iterable[bytes],
    *,
    version: int = 0,
) -> str:
    """Same CID as ``compute_unixfs_file_cid`` for the concatenation of ``chunks``.

    Pieces larger than ``DEFAULT_CHUNK_SIZE`` are re-sliced to the default chunker.
    """
    root = _balanced_root_from_chunks(_normalize_chunk_stream(chunks))
    return _cid_from_block(root.block, version=version)


def local_cids_equal(left: str, right: str) -> bool:
    """True if CID strings denote the same content id (v0/v1 tolerant)."""
    a = left.strip()
    b = right.strip()
    if a == b:
        return True
    try:
        ca = make_cid(a)
        cb = make_cid(b)
    except Exception:
        return False
    return ca.multihash == cb.multihash
