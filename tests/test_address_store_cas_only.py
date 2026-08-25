"""AddressStore CAS-only — legacy CID fail closed (§6s)."""
from pathlib import Path

import pytest

from cats.network.address_store import AddressStore
from cats.network.cas import CasHttpStore


def test_legacy_cid_cat_fail_closed(tmp_path):
    store = AddressStore(None, cats_home=str(tmp_path))
    with pytest.raises(RuntimeError, match='§6s'):
        store.cat_bytes('QmLegacyCidThatIsNotSupported')


def test_legacy_cid_get_fail_closed(tmp_path):
    store = AddressStore(None, cats_home=str(tmp_path))
    with pytest.raises(RuntimeError, match='§6s'):
        store.get('bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi', str(tmp_path / 'out'))


def test_cas_roundtrip_still_works(tmp_path):
    cas = CasHttpStore(str(tmp_path))
    ni = cas.put(b'hello-6s')
    store = AddressStore(None, cats_home=str(tmp_path))
    assert store.cat_bytes(ni) == b'hello-6s'
    dest = tmp_path / 'out.bin'
    store.get(ni, str(dest))
    assert Path(dest).read_bytes() == b'hello-6s'
