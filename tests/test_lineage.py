"""Cross-CAT Order / Invoice lineage helpers."""
from __future__ import annotations

import pytest

from cats.network.registry import (
    assert_distinct_executions,
    assert_invoice_data_chain,
    assert_order_pairing_lineage,
)


def test_order_pairing_link_process():
    prior = {'function_uri': 'http://n/ldp/cas/fn0', 'structure_uri': 'st'}
    nxt = {'function_uri': 'http://n/ldp/cas/fn1', 'structure_uri': 'st'}
    out = assert_order_pairing_lineage(
        prior, nxt, function='mutated', structure='carried'
    )
    assert out['function_0'] != out['function_1']
    assert out['structure_0'] == out['structure_1'] == 'st'


def test_order_pairing_link_structure():
    prior = {'function_cid': 'fn', 'structure_cid': 'st0'}
    nxt = {'function_uri': 'fn', 'structure_uri': 'st1'}
    out = assert_order_pairing_lineage(
        prior, nxt, function='carried', structure='mutated'
    )
    assert out['function_0'] == out['function_1'] == 'fn'
    assert out['structure_0'] != out['structure_1']


def test_order_pairing_both_mutated():
    prior = {'function_cid': 'fn0', 'structure_cid': 'st0'}
    nxt = {'function_uri': 'fn1', 'structure_uri': 'st1'}
    assert_order_pairing_lineage(
        prior, nxt, function='mutated', structure='mutated'
    )


def test_order_pairing_function_not_mutated_raises():
    prior = {'function_uri': 'fn', 'structure_uri': 'st'}
    nxt = {'function_uri': 'fn', 'structure_uri': 'st'}
    with pytest.raises(AssertionError, match='Function should be mutated'):
        assert_order_pairing_lineage(
            prior, nxt, function='mutated', structure='carried'
        )


def test_order_pairing_structure_not_carried_raises():
    prior = {'function_uri': 'fn0', 'structure_uri': 'st0'}
    nxt = {'function_uri': 'fn1', 'structure_uri': 'st1'}
    with pytest.raises(AssertionError, match='Structure should be carried'):
        assert_order_pairing_lineage(
            prior, nxt, function='mutated', structure='carried'
        )


def test_order_pairing_missing_ref_raises():
    with pytest.raises(AssertionError, match='missing function ref'):
        assert_order_pairing_lineage(
            {'structure_uri': 'st'},
            {'function_uri': 'fn', 'structure_uri': 'st'},
            function='mutated',
            structure='carried',
        )


def test_order_pairing_bad_mode_raises():
    prior = {'function_uri': 'fn0', 'structure_uri': 'st'}
    nxt = {'function_uri': 'fn1', 'structure_uri': 'st'}
    with pytest.raises(AssertionError, match='mutated|carried'):
        assert_order_pairing_lineage(
            prior, nxt, function='unchanged', structure='carried'
        )


def test_invoice_data_chain_ok():
    prior = {'data_uri': 'http://n/ldp/cas/abc'}
    nxt = {'data_cid': 'abc'}
    out = assert_invoice_data_chain(prior, nxt)
    assert out['prior_output_data'] == out['next_input_data']


def test_invoice_data_chain_mismatch_raises():
    with pytest.raises(AssertionError, match='next input Invoice data'):
        assert_invoice_data_chain(
            {'data_uri': 'a'},
            {'data_uri': 'b'},
        )


def test_distinct_executions_ok():
    out = assert_distinct_executions(
        {'data_uri': 'd0'},
        {'data_uri': 'd1'},
        prior_seed={'seed': 'aa', 'rng_seed': 1, 'num_partitions': 2},
        next_seed={'seed': 'bb', 'rng_seed': 2, 'num_partitions': 2},
    )
    assert out['data_0'] == 'd0'
    assert out['data_1'] == 'd1'
    assert out['seed_0'] == 'aa'
    assert out['seed_1'] == 'bb'


def test_distinct_executions_same_data_raises():
    with pytest.raises(AssertionError, match='output data should differ'):
        assert_distinct_executions(
            {'data_uri': 'd0'},
            {'data_uri': 'd0'},
            prior_seed={'seed': 'aa', 'rng_seed': 1},
            next_seed={'seed': 'bb', 'rng_seed': 2},
        )


def test_distinct_executions_same_seed_raises():
    with pytest.raises(AssertionError, match='seed identity hex'):
        assert_distinct_executions(
            {'data_uri': 'd0'},
            {'data_uri': 'd1'},
            prior_seed={'seed': 'aa', 'rng_seed': 1},
            next_seed={'seed': 'aa', 'rng_seed': 2},
        )
