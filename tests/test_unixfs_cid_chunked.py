"""Multi-block UnixFS File CID (Kubo default balanced layout) goldens."""
from unittest.mock import MagicMock

import pytest

from cats.network.address_store import (
    CidIntegrityError,
    compute_unixfs_file_cid,
    compute_unixfs_file_cid_from_chunks,
    verify_bytes_match_cid,
)
from cats.network.address_store.unixfs_cid import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_LINKS_PER_BLOCK,
)


# Locked against Kubo 0.21.0 ``ipfs add --only-hash`` (default importer).
_GOLDEN_TWO_CHUNK_A = 'QmTaxvXcxpzzaatSEEAYr7t3knkJ6DmTVbr8MjJJWLRWpV'
_GOLDEN_EXACT_TWO_B = 'QmNM4Guu5ENpcY4TiYktgRwaDdm36YHscx9WzxHKQ1TXSE'
_GOLDEN_THREE_CHUNK_C = 'QmQKeyRQQCZfWTsd4wMippHaMzgkuwuEynn2gMmcfJCL46'
_GOLDEN_EXACT_ONE_D = 'QmSL1qd69nnsqV6uBySVTh6gieXYeESsmkcAg6c2pk7epn'
_GOLDEN_FANOUT_175_E = 'QmSpDp5xNHC5rtWDXRGUnWZpYZURMxXo5VzjPmmKeKZc3b'


def test_boundary_exact_chunk_is_single_block():
    data = b'd' * DEFAULT_CHUNK_SIZE
    assert compute_unixfs_file_cid(data) == _GOLDEN_EXACT_ONE_D


def test_two_chunk_golden():
    data = b'a' * (DEFAULT_CHUNK_SIZE + 1)
    assert compute_unixfs_file_cid(data) == _GOLDEN_TWO_CHUNK_A


def test_exact_two_chunks_golden():
    data = b'b' * (DEFAULT_CHUNK_SIZE * 2)
    assert compute_unixfs_file_cid(data) == _GOLDEN_EXACT_TWO_B


def test_three_chunk_golden():
    data = b'c' * (DEFAULT_CHUNK_SIZE * 2 + 100)
    assert compute_unixfs_file_cid(data) == _GOLDEN_THREE_CHUNK_C


def test_fanout_depth_bump_175_chunks():
    """175 leaves forces balanced depth bump (max links = 174)."""
    assert DEFAULT_LINKS_PER_BLOCK == 174
    data = b'e' * (DEFAULT_LINKS_PER_BLOCK + 1) * DEFAULT_CHUNK_SIZE
    assert compute_unixfs_file_cid(data) == _GOLDEN_FANOUT_175_E


def test_verify_multi_block_pure_no_oracle():
    data = b'a' * (DEFAULT_CHUNK_SIZE + 1)
    cid = _GOLDEN_TWO_CHUNK_A
    client = MagicMock()
    verify_bytes_match_cid(client, cid, data)
    client.only_hash_bytes.assert_not_called()


def test_verify_multi_block_without_client():
    data = b'b' * (DEFAULT_CHUNK_SIZE * 2)
    verify_bytes_match_cid(None, _GOLDEN_EXACT_TWO_B, data)


def test_verify_multi_block_tamper():
    data = b'a' * (DEFAULT_CHUNK_SIZE + 1)
    client = MagicMock()
    client.only_hash_bytes.return_value = 'QmOther'
    client.cid_format.side_effect = RuntimeError('no format')
    with pytest.raises(CidIntegrityError) as exc:
        verify_bytes_match_cid(client, _GOLDEN_TWO_CHUNK_A, data[:-1] + b'Z')
    assert exc.value.cid == _GOLDEN_TWO_CHUNK_A


def test_from_chunks_matches_contiguous():
    data = b'c' * (DEFAULT_CHUNK_SIZE * 2 + 100)
    contiguous = compute_unixfs_file_cid(data)
    # Uneven pieces that still concatenate to ``data``.
    pieces = [
        data[:1000],
        data[1000 : DEFAULT_CHUNK_SIZE + 50],
        data[DEFAULT_CHUNK_SIZE + 50 :],
    ]
    assert compute_unixfs_file_cid_from_chunks(pieces) == contiguous
    assert contiguous == _GOLDEN_THREE_CHUNK_C


def test_from_chunks_empty():
    assert (
        compute_unixfs_file_cid_from_chunks([])
        == compute_unixfs_file_cid(b'')
        == 'QmbFMke1KXqnYyBBWxB74N4c5SBnJMVAiMNRcGu6x1AwQH'
    )


def test_multi_block_v0_v1_equal():
    data = b'a' * (DEFAULT_CHUNK_SIZE + 1)
    v0 = compute_unixfs_file_cid(data, version=0)
    v1 = compute_unixfs_file_cid(data, version=1)
    assert v0 == _GOLDEN_TWO_CHUNK_A
    assert v1.startswith('bafy')
    from cats.network.address_store.unixfs_cid import local_cids_equal

    assert local_cids_equal(v0, v1)
