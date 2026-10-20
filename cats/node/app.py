"""Flask peer-edge HTTP API for CAT Node."""
from __future__ import annotations

import logging
import json
import os
import re
import traceback

from flask import Flask, request, jsonify

from cats import CATS_HOME, RUNTIME
from cats.network.cas import register_cas_routes
from cats.network.ldp import register_ldp_routes
from cats.network.registry import (
    AmbiguousBomError,
    BomRegistry,
    RegistryError,
    register_registry_routes,
)

catNode = Flask(__name__)

# Overridable so multiple CAT Node peers can eventually run side-by-side
# (e.g. simulating a local mesh). ContentMesh Order endpoints use the same
# CAT_NODE_HOST / CAT_NODE_PORT defaults via `_node_base_url()`.
HOST = os.environ.get('CAT_NODE_HOST', '127.0.0.1')
PORT = int(os.environ.get('CAT_NODE_PORT', 5000))

logger = logging.getLogger(__name__)

# Phase 2a control plane: LDP-shaped BOM envelope GETs (publish via Runtime).
register_ldp_routes(catNode, cats_home=CATS_HOME)
# Before 2b: BOM registry index (BOM→Order, data→BOM).
register_registry_routes(catNode, cats_home=CATS_HOME)
# CAS-over-HTTP: digest-keyed blob GETs (publish via ContentMesh / Runtime).
register_cas_routes(catNode, cats_home=CATS_HOME)

_LEGACY_INIT_KEYS = ('order_cid', 'bom_cid', 'data_cid')

_MODULE_DIGEST = re.compile(r'^sha256:[0-9a-f]{64}$')

_MISSING_FUNCTION_STRUCTURE = (
    'Order missing structure / function refs '
    '(structure_uri/structure_cid, function_uri/function_cid)'
)


class OrderIntakeError(Exception):
    """Order locator could not be resolved (HTTP status on the Flask path)."""

    def __init__(self, payload: dict, status: int):
        super().__init__(payload.get('error', 'order intake failed'))
        self.payload = payload
        self.status = status


def resolve_order_id(body: dict, *, cats_home: str | None = None) -> str:
    """Resolve Order equality id from §6d/§6f intake keys.

    Accepts ``order_uri`` | ``data_uri`` | ``bom_ldp_uri`` / ``bom_solid_uri`` /
    ``bom_uri`` | ``content_id`` | ``hl`` (``ni:`` / hex / ``hl:`` / http).
    Rejects legacy ``order_cid`` / ``bom_cid`` / ``data_cid`` body keys.
    """
    cats_home = CATS_HOME if cats_home is None else cats_home
    bad = [k for k in _LEGACY_INIT_KEYS if k in body and body[k] is not None]
    if bad:
        raise OrderIntakeError(
            {
                'error': (
                    f'{", ".join(bad)} no longer accepted; use order_uri, '
                    'data_uri, bom_ldp_uri / bom_solid_uri, content_id, or hl'
                ),
            },
            400,
        )

    from cats.network.cas import (
        is_hl,
        is_http_uri,
        is_ni_or_digest,
        resolve_intake_ref,
    )

    registry = BomRegistry(cats_home)

    def _id_from_value(value: str, *, label: str) -> str:
        try:
            if not (
                is_hl(value)
                or is_http_uri(value)
                or is_ni_or_digest(value)
            ):
                raise OrderIntakeError({'error': f'invalid {label}'}, 400)
            found = resolve_intake_ref(value, cats_home=cats_home)
        except ValueError:
            raise OrderIntakeError({'error': f'invalid {label}'}, 400)
        if found is None:
            raise OrderIntakeError({'error': 'not found', label: value}, 404)
        return found

    order_uri = body.get('order_uri')
    if order_uri:
        return _id_from_value(order_uri, label='order_uri')

    bom_locator = (
        body.get('bom_uri')
        or body.get('bom_ldp_uri')
        or body.get('bom_solid_uri')
    )
    if bom_locator:
        bom_id = _id_from_value(bom_locator, label='bom_uri')
        try:
            resolved = registry.lookup_order(bom_id)
        except ValueError:
            raise OrderIntakeError({'error': 'invalid bom_uri'}, 400)
        if resolved is None:
            raise OrderIntakeError(
                {'error': 'not found', 'bom_uri': bom_locator},
                404,
            )
        return resolved

    content_id = body.get('content_id') or body.get('hl')
    data_uri = body.get('data_uri')
    data_id = content_id

    if data_uri and not data_id:
        data_id = _id_from_value(data_uri, label='data_uri')

    if data_id:
        if is_hl(data_id) or is_http_uri(data_id):
            data_id = _id_from_value(data_id, label='content_id')
        try:
            bom_id = registry.resolve_unique_bom(data_id)
        except AmbiguousBomError as exc:
            raise OrderIntakeError(
                {
                    'error': 'ambiguous content_id',
                    'content_id': data_id,
                    'bom_ids': exc.bom_ids,
                },
                409,
            )
        except RegistryError:
            raise OrderIntakeError(
                {'error': 'not found', 'content_id': data_id},
                404,
            )
        except ValueError:
            raise OrderIntakeError({'error': 'invalid content_id'}, 400)
        resolved = registry.lookup_order(bom_id)
        if resolved is None:
            raise OrderIntakeError(
                {'error': 'not found', 'content_id': bom_id},
                404,
            )
        return resolved

    raise OrderIntakeError(
        {
            'error': (
                'order_uri, data_uri, bom_ldp_uri / bom_solid_uri, '
                'content_id, or hl required'
            ),
        },
        400,
    )


def _resolve_order_id_from_request(body: dict) -> tuple[str | None, tuple | None]:
    """Flask wrapper around :func:`resolve_order_id`."""
    try:
        return resolve_order_id(body, cats_home=CATS_HOME), None
    except OrderIntakeError as exc:
        return None, (jsonify(exc.payload), exc.status)


def _refuse_unless_module_digest(structure_id: str, module_digest: str) -> None:
    """Refuse when ``structure_id`` is not the Job's ``sha256:`` module digest."""
    if not _MODULE_DIGEST.fullmatch(module_digest):
        raise RuntimeError(
            'module digest must be sha256: plus 64 lowercase hex'
        )
    from cats.network.content_mesh import ContentMesh

    try:
        spelled = ContentMesh.bundle_digest(None, structure_id)
    except ValueError as exc:
        raise RuntimeError(
            'structure content id is not the module digest'
        ) from exc
    if spelled != module_digest:
        raise RuntimeError(
            'structure content id is not the module digest'
        )


def run_order(
    order_request,
    *,
    runtime=None,
    cats_home=None,
    apply_structure=None,
    structure_handoff=None,
    module_digest=None,
    run_emitter=None,
):
    """Load one Order, run Factory → Executor, sign the BOM.

    Function and Structure come from the Order. Missing either fails closed.
    Does not bind Flask.

    ``apply_structure`` is omitted on the peer path, so Executor applies
    Structure. The one-shot entry passes ``False`` and a handoff map.
    A flag or handoff on the request body is ignored.

    ``module_digest`` is omitted on the peer path. The one-shot entry passes
    it only when the caller supplies ``sha256:`` plus 64 hex. A digest on
    the request body is ignored.

    ``run_emitter`` is omitted on the peer path. The one-shot entry passes
    it only when the Plane set a job environment. An emitter on the request
    body is ignored.
    """
    runtime = RUNTIME if runtime is None else runtime
    cats_home = CATS_HOME if cats_home is None else cats_home
    order_request = dict(order_request)
    order_request.pop('apply_structure', None)
    order_request.pop('structure_handoff', None)
    order_request.pop('module_digest', None)
    order_request.pop('run_emitter', None)
    if apply_structure is not None:
        order_request['apply_structure'] = apply_structure
    if structure_handoff is not None:
        order_request['structure_handoff'] = structure_handoff
    if run_emitter is not None:
        order_request['run_emitter'] = run_emitter
    if not order_request.get('order_id'):
        order_request['order_id'] = resolve_order_id(
            order_request, cats_home=cats_home
        )
    if 'order' not in order_request:
        order_request['order'] = json.loads(
            runtime.contentMesh.cat(order_request['order_id'])
        )
    from cats.network.cas import ref_id, ref_uri

    order = order_request['order']
    function_id = ref_id(order, 'function', cats_home=cats_home)
    structure_id = ref_id(order, 'structure', cats_home=cats_home)
    if not function_id or not structure_id:
        raise RuntimeError(_MISSING_FUNCTION_STRUCTURE)
    if module_digest is not None:
        _refuse_unless_module_digest(structure_id, module_digest)

    invoice_locator = ref_uri(order, 'invoice') or ref_id(
        order, 'invoice', cats_home=cats_home
    )
    if not invoice_locator:
        raise RuntimeError('Order missing invoice_uri / invoice_cid')
    if 'invoice' not in order_request:
        order_request['invoice'] = json.loads(
            runtime.contentMesh.cat(invoice_locator)
        )
    init_data_id = ref_id(
        order_request['invoice'], 'data', cats_home=cats_home
    )
    if not init_data_id:
        raise RuntimeError('Invoice missing data_uri / data_cid')

    catFactory, updated_order_request = runtime.initFactory(
        order_request, init_data_id
    )
    return runtime.execute(catFactory, updated_order_request)


@catNode.route('/cat/node/init', methods=['POST'])
def execute_init_cat():
    try:
        bom_response = run_order(request.get_json() or {})
        return jsonify(bom_response)
    except OrderIntakeError as exc:
        return jsonify(exc.payload), exc.status
    except Exception as e:
        logger.error("An error occurred: %s", traceback.format_exc())
        return jsonify({'error': str(e)}), 500
