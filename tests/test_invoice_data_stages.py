"""Invoice ``data_stages`` nest resolver + mint invariants."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from cats.network.cas import (
    assert_egressed_matches_data,
    resolve_invoice_data_stages,
    set_ref,
    to_ni,
)


def test_resolve_prefers_data_stages_nest():
    egress = to_ni('a' * 64)
    integ = to_ni('b' * 64)
    ingres = to_ni('c' * 64)
    nest = {}
    set_ref(nest, 'egressed_data', egress)
    set_ref(nest, 'integrated_data', integ)
    set_ref(nest, 'ingressed_data', ingres)
    nest_id = to_ni('d' * 64)

    invoice = {}
    set_ref(invoice, 'data', egress)
    set_ref(invoice, 'data_stages', nest_id)
    # Flat siblings must be ignored when nest loads.
    set_ref(invoice, 'ingress_data', to_ni('e' * 64))
    set_ref(invoice, 'integration_data', to_ni('f' * 64))

    mesh = MagicMock()
    mesh.CATS_HOME = None
    mesh.cat.side_effect = lambda key: json.dumps(nest)

    stages = resolve_invoice_data_stages(invoice, content_mesh=mesh)
    assert stages['ingress_data_id'] == ingres
    assert stages['integration_data_id'] == integ
    assert stages['egress_data_id'] == egress
    assert stages['data_stages_id'] == nest_id


def test_resolve_falls_back_to_flat_siblings():
    egress = to_ni('a' * 64)
    integ = to_ni('b' * 64)
    ingres = to_ni('c' * 64)
    invoice = {}
    set_ref(invoice, 'data', egress)
    set_ref(invoice, 'ingress_data', ingres)
    set_ref(invoice, 'integration_data', integ)

    stages = resolve_invoice_data_stages(invoice, content_mesh=None)
    assert stages['ingress_data_id'] == ingres
    assert stages['integration_data_id'] == integ
    assert stages['egress_data_id'] == egress
    assert stages['data_stages_id'] is None


def test_assert_egressed_matches_data_ok_and_fail():
    egress = to_ni('a' * 64)
    other = to_ni('b' * 64)
    invoice = {}
    nest = {}
    set_ref(invoice, 'data', egress)
    set_ref(nest, 'egressed_data', egress)
    assert_egressed_matches_data(invoice, nest)

    set_ref(nest, 'egressed_data', other)
    with pytest.raises(AssertionError):
        assert_egressed_matches_data(invoice, nest)
