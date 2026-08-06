"""CARv1 + UnixFS directory/file extract (gateway hygiene leftover 1)."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cats.network.address_store import (
    AddressStore,
    GatewayError,
    UnixfsExtractError,
    block_cid,
    compute_unixfs_file_cid,
    extract_unixfs_from_car,
    read_car,
    write_car,
)
from cats.network.address_store.unixfs_cid import (
    DEFAULT_CHUNK_SIZE,
    encode_dag_pb_node,
    encode_dag_pb_node_with_links,
    encode_unixfs_file,
    encode_unixfs_file_intermediate,
    sha256_multihash,
)
from cats.network.address_store.unixfs_cid import (
    _proto_bytes,
    _proto_string,
    _proto_varint,
)


def _file_block(data: bytes) -> tuple[str, bytes]:
    block = encode_dag_pb_node(encode_unixfs_file(data))
    return block_cid(block), block


def _directory_block(named: list[tuple[str, bytes]]) -> tuple[str, bytes]:
    """Build a flat UnixFS Directory dag-pb node linking named child blocks."""
    ufs = _proto_varint(1, 1)  # Type = Directory
    parts: list[bytes] = []
    for name, child_block in named:
        mh = sha256_multihash(child_block)
        link = _proto_bytes(1, mh)
        link += _proto_string(2, name)
        link += _proto_varint(3, len(child_block))
        parts.append(_proto_bytes(2, link))
    parts.append(_proto_bytes(1, ufs))
    block = b''.join(parts)
    return block_cid(block), block


def _hamt_block() -> tuple[str, bytes]:
    ufs = _proto_varint(1, 5)  # HAMTShard
    block = encode_dag_pb_node(ufs)
    return block_cid(block), block


def test_car_roundtrip_single_file(tmp_path):
    cid, block = _file_block(b'hello car extract')
    car = write_car([cid], {cid: block})
    roots, blocks = read_car(car)
    assert roots == [cid]
    assert blocks[cid] == block
    dest = tmp_path / 'out.bin'
    extract_unixfs_from_car(car, cid, str(dest))
    assert dest.read_bytes() == b'hello car extract'


def test_extract_directory_two_files(tmp_path):
    c1, b1 = _file_block(b'one')
    c2, b2 = _file_block(b'two')
    dcid, dblock = _directory_block([('a.txt', b1), ('b.txt', b2)])
    car = write_car([dcid], {dcid: dblock, c1: b1, c2: b2})
    dest = tmp_path / 'root'
    extract_unixfs_from_car(car, dcid, str(dest))
    assert (dest / 'a.txt').read_bytes() == b'one'
    assert (dest / 'b.txt').read_bytes() == b'two'


def test_extract_multiblock_file_in_directory(tmp_path):
    payload = b'a' * (DEFAULT_CHUNK_SIZE + 1)
    file_cid = compute_unixfs_file_cid(payload)
    leaf1 = encode_dag_pb_node(encode_unixfs_file(b'a' * DEFAULT_CHUNK_SIZE))
    leaf2 = encode_dag_pb_node(encode_unixfs_file(b'a'))
    c1, c2 = block_cid(leaf1), block_cid(leaf2)
    ufs = encode_unixfs_file_intermediate(len(payload), [DEFAULT_CHUNK_SIZE, 1])
    root_file = encode_dag_pb_node_with_links(
        ufs,
        [
            (sha256_multihash(leaf1), len(leaf1)),
            (sha256_multihash(leaf2), len(leaf2)),
        ],
    )
    assert block_cid(root_file) == file_cid
    dcid, dblock = _directory_block([('big.bin', root_file)])
    car = write_car(
        [dcid],
        {dcid: dblock, file_cid: root_file, c1: leaf1, c2: leaf2},
    )
    dest = tmp_path / 'dir'
    extract_unixfs_from_car(car, dcid, str(dest))
    assert (dest / 'big.bin').read_bytes() == payload


def test_unsafe_link_name_rejected(tmp_path):
    c1, b1 = _file_block(b'x')
    dcid, dblock = _directory_block([('..', b1)])
    car = write_car([dcid], {dcid: dblock, c1: b1})
    with pytest.raises(UnixfsExtractError, match='unsafe'):
        extract_unixfs_from_car(car, dcid, str(tmp_path / 'bad'))


def test_missing_root_block(tmp_path):
    c1, b1 = _file_block(b'only-child')
    # CAR without the directory root block
    fake_root = compute_unixfs_file_cid(b'other')
    car = write_car([fake_root], {c1: b1})
    with pytest.raises(UnixfsExtractError, match='missing block'):
        extract_unixfs_from_car(car, fake_root, str(tmp_path / 'x'))


def test_hamt_unsupported(tmp_path):
    cid, block = _hamt_block()
    car = write_car([cid], {cid: block})
    with pytest.raises(UnixfsExtractError, match='unsupported UnixFS type'):
        extract_unixfs_from_car(car, cid, str(tmp_path / 'h'))


def test_address_store_get_car_extract_no_rpc(monkeypatch, tmp_path):
    c1, b1 = _file_block(b'one')
    c2, b2 = _file_block(b'two')
    dcid, dblock = _directory_block([('a.txt', b1), ('b.txt', b2)])
    car = write_car([dcid], {dcid: dblock, c1: b1, c2: b2})

    monkeypatch.setenv('IPFS_GATEWAY_URL', 'http://127.0.0.1:8080')
    ipfs = MagicMock()
    store = AddressStore(ipfs)
    store.gateway = MagicMock()
    store.gateway.get_file.side_effect = GatewayError(
        'http://gw/ipfs/QmD', 200, 'directory or HTML listing'
    )

    def _dag_export(cid, filepath):
        Path(filepath).write_bytes(car)

    store.gateway.dag_export.side_effect = _dag_export
    dest = str(tmp_path / 'out')
    assert store.get(dcid, dest) == dest
    assert (Path(dest) / 'a.txt').read_bytes() == b'one'
    assert (Path(dest) / 'b.txt').read_bytes() == b'two'
    ipfs.get.assert_not_called()
    store.gateway.dag_export.assert_called_once()


def test_address_store_get_car_fail_falls_back_rpc(monkeypatch, tmp_path):
    monkeypatch.setenv('IPFS_GATEWAY_URL', 'http://127.0.0.1:8080')
    ipfs = MagicMock()
    dest = str(tmp_path / 'dir')
    ipfs.get.return_value = dest
    store = AddressStore(ipfs)
    store.gateway = MagicMock()
    store.gateway.get_file.side_effect = GatewayError(
        'http://gw/ipfs/QmD', 200, 'directory or HTML listing'
    )
    store.gateway.dag_export.side_effect = GatewayError('u', 503, 'down')
    assert store.get('QmD', dest) == dest
    ipfs.get.assert_called_once_with('QmD', dest)
