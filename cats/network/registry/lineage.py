"""Cross-CAT Order / Invoice lineage — pairing, data chain, distinct executions.

Distinct from per-run handoff / content_equiv / execution_bind / stageLineage.
Two executions required; not a CAT0-only inspect.
"""
from __future__ import annotations

from typing import Any, Literal

from cats.network.cas import equality_id, ref_id

PairingMode = Literal['mutated', 'carried']


def _require_stem_id(obj: dict[str, Any], stem: str, *, label: str) -> str:
    if not isinstance(obj, dict):
        raise AssertionError(
            f'{label} is not a JSON object: {type(obj).__name__}'
        )
    value = ref_id(obj, stem)
    if not value:
        raise AssertionError(f'{label} missing {stem} ref')
    return equality_id(value)


def _assert_pairing(
    prior_id: str,
    next_id: str,
    *,
    mode: PairingMode,
    label: str,
) -> None:
    if mode == 'mutated':
        if prior_id == next_id:
            raise AssertionError(
                f'{label} should be mutated; both {prior_id!r}'
            )
        return
    if mode == 'carried':
        if prior_id != next_id:
            raise AssertionError(
                f'{label} should be carried; {prior_id!r} != {next_id!r}'
            )
        return
    raise AssertionError(
        f'{label} mode must be mutated|carried, got {mode!r}'
    )


def assert_order_pairing_lineage(
    prior_order: dict[str, Any],
    next_order: dict[str, Any],
    *,
    function: PairingMode,
    structure: PairingMode,
) -> dict[str, str]:
    """Assert Function / Structure ids mutated or carried across Orders.

    ``function`` / ``structure`` are ``'mutated'`` or ``'carried'``
    (``linkProcess``: function mutated, structure carried).
    """
    fn0 = _require_stem_id(prior_order, 'function', label='prior Order')
    fn1 = _require_stem_id(next_order, 'function', label='next Order')
    st0 = _require_stem_id(prior_order, 'structure', label='prior Order')
    st1 = _require_stem_id(next_order, 'structure', label='next Order')
    _assert_pairing(fn0, fn1, mode=function, label='Function')
    _assert_pairing(st0, st1, mode=structure, label='Structure')
    return {
        'function_0': fn0,
        'function_1': fn1,
        'structure_0': st0,
        'structure_1': st1,
    }


def assert_invoice_data_chain(
    prior_output_invoice: dict[str, Any],
    next_input_invoice: dict[str, Any],
) -> dict[str, str]:
    """Assert next Order input Invoice ``data`` ≡ prior output Invoice ``data``."""
    prior = _require_stem_id(
        prior_output_invoice, 'data', label='prior output Invoice'
    )
    nxt = _require_stem_id(
        next_input_invoice, 'data', label='next input Invoice'
    )
    if prior != nxt:
        raise AssertionError(
            f'next input Invoice data {nxt!r} != prior output data {prior!r}'
        )
    return {
        'prior_output_data': prior,
        'next_input_data': nxt,
    }


def _require_seed_field(seed: dict[str, Any], key: str, *, label: str) -> Any:
    if not isinstance(seed, dict):
        raise AssertionError(
            f'{label} is not a JSON object: {type(seed).__name__}'
        )
    if key not in seed:
        raise AssertionError(f'{label} missing {key!r}: {seed!r}')
    return seed[key]


def assert_distinct_executions(
    prior_invoice: dict[str, Any],
    next_invoice: dict[str, Any],
    *,
    prior_seed: dict[str, Any],
    next_seed: dict[str, Any],
) -> dict[str, Any]:
    """Assert two Executor runs minted distinct output data and Seeds."""
    data0 = _require_stem_id(
        prior_invoice, 'data', label='prior output Invoice'
    )
    data1 = _require_stem_id(
        next_invoice, 'data', label='next output Invoice'
    )
    if data0 == data1:
        raise AssertionError(
            f'output data should differ per execution; both {data0!r}'
        )
    seed0 = _require_seed_field(prior_seed, 'seed', label='prior Seed')
    seed1 = _require_seed_field(next_seed, 'seed', label='next Seed')
    rng0 = _require_seed_field(prior_seed, 'rng_seed', label='prior Seed')
    rng1 = _require_seed_field(next_seed, 'rng_seed', label='next Seed')
    if seed0 == seed1:
        raise AssertionError(
            f'seed identity hex should differ per execution; both {seed0!r}'
        )
    if rng0 == rng1:
        raise AssertionError(
            f'rng_seed should differ per execution; both {rng0!r}'
        )
    return {
        'data_0': data0,
        'data_1': data1,
        'seed_0': seed0,
        'seed_1': seed1,
    }
