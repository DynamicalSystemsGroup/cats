"""P1 FRU catalog purl — naming only, no envelope I/O."""
from __future__ import annotations

import pytest

from cats.network.bom import fru_purl
from cats.network.cas import sha256_hex, to_ni

_HEX = sha256_hex(b'p1-fru-lot')
_NI = to_ni(_HEX)
_LEGACY_CID = 'QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG'


def test_cats_roles_match_locked_shape():
    for role in ('function', 'structure', 'dataset'):
        assert fru_purl(role, _NI) == f'pkg:generic/cats/{role}@{_NI}'


def test_hex_and_ni_yield_same_generic_purl():
    assert fru_purl('function', _HEX) == fru_purl('function', _NI)
    assert fru_purl('function', _HEX).endswith(f'@{_NI}')


def test_oci_uses_sha256_hex_not_ni():
    expected = f'pkg:oci/rayproject/ray@sha256:{_HEX}'
    assert fru_purl('oci', _HEX, name='rayproject/ray') == expected
    assert fru_purl('oci', _NI, name='rayproject/ray') == expected
    assert fru_purl('oci', name='rayproject/ray', version=f'sha256:{_HEX}') == expected
    assert '@ni:' not in fru_purl('oci', _NI, name='rayproject/ray')


def test_pypi_locked_shape():
    assert fru_purl('pypi', name='numpy', version='2.1.0') == 'pkg:pypi/numpy@2.1.0'


def test_pypi_rejects_ni_version():
    with pytest.raises(ValueError, match='pypi version'):
        fru_purl('pypi', name='numpy', version=_NI)
    with pytest.raises(ValueError, match='pypi version'):
        fru_purl('pypi', name='numpy', version=_HEX)


@pytest.mark.parametrize(
    'kwargs',
    [
        {'role': 'widget', 'content_id': _NI},
        {'role': 'function'},
        {'role': 'function', 'content_id': ''},
        {'role': 'function', 'content_id': _LEGACY_CID},
        {'role': 'oci', 'content_id': _HEX},
        {'role': 'oci', 'name': 'rayproject/ray'},
        {'role': 'pypi', 'name': 'numpy'},
        {'role': 'pypi', 'version': '2.1.0'},
    ],
)
def test_fail_closed(kwargs):
    role = kwargs.pop('role')
    with pytest.raises(ValueError):
        fru_purl(role, **kwargs)
