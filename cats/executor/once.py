"""One-shot Executor: load one Order, execute, write the Job result, exit.

Does not bind the Flask peer. Entry: ``python -m cats.executor.once``.
Function and Structure come from the Order, not from this process image.
On success, Invoice / BOM / cited CAS blobs land in ``CAT_RESULT_DIR``
(outside ``CATS_HOME``). The Flask route does not write that directory.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_LOCATOR_KEYS = (
    'order_uri',
    'data_uri',
    'bom_uri',
    'bom_ldp_uri',
    'bom_solid_uri',
    'content_id',
    'hl',
)


def _body_from_args(args: argparse.Namespace) -> dict:
    body = {}
    for key in _LOCATOR_KEYS:
        value = getattr(args, key, None) or os.environ.get(key.upper())
        if value:
            body[key] = value
    return body


def _handoff_path(args: argparse.Namespace) -> str | None:
    return args.structure_handoff or os.environ.get('CATS_STRUCTURE_HANDOFF')


def _module_digest(args: argparse.Namespace) -> str | None:
    if args.module_digest is not None:
        return args.module_digest
    return os.environ.get('CATS_MODULE_DIGEST') or None


def load_structure_handoff(path: str | None) -> dict:
    """Terraform output names to strings. Does not invoke Terraform."""
    if not path:
        raise RuntimeError(
            'structure handoff required: '
            '--structure-handoff or CATS_STRUCTURE_HANDOFF'
        )
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not data:
        raise RuntimeError(
            'structure handoff must be a non-empty JSON object '
            'of terraform output names'
        )
    return {
        str(key): '' if value is None else str(value)
        for key, value in data.items()
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog='python -m cats.executor.once',
        description=(
            'Run one Order through Factory → Executor.execute, sign the BOM, '
            'print the response, and exit. Does not bind Flask.'
        ),
    )
    parser.add_argument('--order-uri', dest='order_uri')
    parser.add_argument('--data-uri', dest='data_uri')
    parser.add_argument('--bom-uri', dest='bom_uri')
    parser.add_argument('--bom-ldp-uri', dest='bom_ldp_uri')
    parser.add_argument('--bom-solid-uri', dest='bom_solid_uri')
    parser.add_argument('--content-id', dest='content_id')
    parser.add_argument('--hl', dest='hl')
    parser.add_argument(
        '--structure-handoff',
        dest='structure_handoff',
        help=(
            'JSON map of terraform output names to strings. '
            'Required. Once does not apply Structure. '
            'Env: CATS_STRUCTURE_HANDOFF.'
        ),
    )
    parser.add_argument(
        '--module-digest',
        dest='module_digest',
        help=(
            'sha256: plus 64 lowercase hex. When set, the Order structure '
            'content id must be that digest. Unset skips the check. '
            'Env: CATS_MODULE_DIGEST.'
        ),
    )
    args = parser.parse_args(argv)

    from cats import CATS_HOME
    from cats.executor.result import write_job_result
    from cats.node.app import OrderIntakeError, run_order

    try:
        body = _body_from_args(args)
        kwargs = {}
        if body:
            kwargs['apply_structure'] = False
            kwargs['structure_handoff'] = load_structure_handoff(
                _handoff_path(args)
            )
            module_digest = _module_digest(args)
            if module_digest is not None:
                kwargs['module_digest'] = module_digest
        bom_response = run_order(body, **kwargs)
        write_job_result(bom_response, cats_home=CATS_HOME)
    except OrderIntakeError as exc:
        print(json.dumps(exc.payload, default=str), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(bom_response, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
