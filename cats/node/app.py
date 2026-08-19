"""Flask peer-edge HTTP API for CAT Node."""
from __future__ import annotations

import logging
import json
import os
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


def _resolve_order_id_from_request(body: dict) -> tuple[str | None, tuple | None]:
    """Resolve Order equality id from §6d/§6f intake keys.

    Accepts ``order_uri`` | ``data_uri`` | ``bom_ldp_uri`` / ``bom_solid_uri`` /
    ``bom_uri`` | ``content_id`` | ``hl`` (``ni:`` / hex / ``hl:`` / http).
    Rejects legacy ``order_cid`` / ``bom_cid`` / ``data_cid`` body keys with
    HTTP 400.

    Returns ``(order_id, error_response)`` — error_response is
    ``(jsonify(...), status)`` when resolution fails.
    """
    bad = [k for k in _LEGACY_INIT_KEYS if k in body and body[k] is not None]
    if bad:
        return None, (
            jsonify({
                'error': (
                    f'{", ".join(bad)} no longer accepted; use order_uri, '
                    'data_uri, bom_ldp_uri / bom_solid_uri, content_id, or hl'
                ),
            }),
            400,
        )

    from cats.network.cas import (
        is_hl,
        is_http_uri,
        is_ni_or_digest,
        resolve_intake_ref,
    )

    cats_home = CATS_HOME
    registry = BomRegistry(cats_home)

    def _id_from_value(value: str, *, label: str):
        try:
            if not (
                is_hl(value)
                or is_http_uri(value)
                or is_ni_or_digest(value)
            ):
                return None, (jsonify({'error': f'invalid {label}'}), 400)
            found = resolve_intake_ref(value, cats_home=cats_home)
        except ValueError:
            return None, (jsonify({'error': f'invalid {label}'}), 400)
        if found is None:
            return None, (jsonify({'error': 'not found', label: value}), 404)
        return found, None

    order_uri = body.get('order_uri')
    if order_uri:
        return _id_from_value(order_uri, label='order_uri')

    bom_locator = (
        body.get('bom_uri')
        or body.get('bom_ldp_uri')
        or body.get('bom_solid_uri')
    )
    if bom_locator:
        bom_id, err = _id_from_value(bom_locator, label='bom_uri')
        if err is not None:
            return None, err
        try:
            resolved = registry.lookup_order(bom_id)
        except ValueError:
            return None, (jsonify({'error': 'invalid bom_uri'}), 400)
        if resolved is None:
            return None, (jsonify({'error': 'not found', 'bom_uri': bom_locator}), 404)
        return resolved, None

    content_id = body.get('content_id') or body.get('hl')
    data_uri = body.get('data_uri')
    data_id = content_id

    if data_uri and not data_id:
        data_id, err = _id_from_value(data_uri, label='data_uri')
        if err is not None:
            return None, err

    if data_id:
        if is_hl(data_id) or is_http_uri(data_id):
            data_id, err = _id_from_value(data_id, label='content_id')
            if err is not None:
                return None, err
        # ``content_id`` / ``data_uri`` / ``hl`` → data equality → unique BOM → Order
        try:
            bom_id = registry.resolve_unique_bom(data_id)
        except AmbiguousBomError as exc:
            return None, (
                jsonify({
                    'error': 'ambiguous content_id',
                    'content_id': data_id,
                    'bom_ids': exc.bom_ids,
                }),
                409,
            )
        except RegistryError:
            return None, (
                jsonify({'error': 'not found', 'content_id': data_id}),
                404,
            )
        except ValueError:
            return None, (jsonify({'error': 'invalid content_id'}), 400)
        resolved = registry.lookup_order(bom_id)
        if resolved is None:
            return None, (
                jsonify({'error': 'not found', 'content_id': bom_id}),
                404,
            )
        return resolved, None

    return None, (
        jsonify({
            'error': (
                'order_uri, data_uri, bom_ldp_uri / bom_solid_uri, '
                'content_id, or hl required'
            ),
        }),
        400,
    )


@catNode.route('/cat/node/init', methods=['POST'])
def execute_init_cat():
    try:
        order_request = request.get_json() or {}
        order_id, err = _resolve_order_id_from_request(order_request)
        if err is not None:
            return err
        order_request = dict(order_request)
        order_request['order_id'] = order_id
        order_request["order"] = json.loads(
            RUNTIME.contentMesh.cat(order_request["order_id"])
        )
        from cats.network.cas import ref_id, ref_uri

        invoice_locator = ref_uri(order_request["order"], 'invoice') or ref_id(
            order_request["order"], 'invoice', cats_home=CATS_HOME
        )
        if not invoice_locator:
            raise RuntimeError('Order missing invoice_uri / invoice_cid')
        order_request['invoice'] = json.loads(
            RUNTIME.contentMesh.cat(invoice_locator)
        )
        init_data_id = ref_id(
            order_request['invoice'], 'data', cats_home=CATS_HOME
        )
        if not init_data_id:
            raise RuntimeError('Invoice missing data_uri / data_cid')

        catFactory, updated_order_request = RUNTIME.initFactory(
            order_request, init_data_id
        )
        bom_response = RUNTIME.execute(catFactory, updated_order_request)

        return jsonify(bom_response)

    except Exception as e:
        logger.error("An error occurred: %s", traceback.format_exc())
        return jsonify({'error': str(e)})
