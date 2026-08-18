"""Flask peer-edge HTTP API for CAT Node."""
from __future__ import annotations

import logging
import json
import os
import traceback

from flask import Flask, request, jsonify

from cats import CATS_HOME, RUNTIME
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
# Before 2b: BOM registry index (BOM→Order, data_cid→BOM).
register_registry_routes(catNode, cats_home=CATS_HOME)


def _resolve_order_cid_from_request(body: dict) -> tuple[str | None, tuple | None]:
    """Prefer ``order_cid``; else registry ``bom_cid`` / unique ``data_cid``.

    Returns ``(order_cid, error_response)`` — error_response is
    ``(jsonify(...), status)`` when resolution fails.
    """
    order_cid = body.get('order_cid')
    if order_cid:
        return order_cid, None

    registry = BomRegistry(CATS_HOME)
    bom_cid = body.get('bom_cid')
    data_cid = body.get('data_cid')

    if bom_cid:
        try:
            resolved = registry.lookup_order(bom_cid)
        except ValueError:
            return None, (jsonify({'error': 'invalid bom_cid'}), 400)
        if resolved is None:
            return None, (jsonify({'error': 'not found', 'bom_cid': bom_cid}), 404)
        return resolved, None

    if data_cid:
        try:
            bom_cid = registry.resolve_unique_bom(data_cid)
        except AmbiguousBomError as exc:
            return None, (
                jsonify({
                    'error': 'ambiguous data_cid',
                    'data_cid': data_cid,
                    'bom_cids': exc.bom_cids,
                }),
                409,
            )
        except RegistryError:
            return None, (jsonify({'error': 'not found', 'data_cid': data_cid}), 404)
        except ValueError:
            return None, (jsonify({'error': 'invalid data_cid'}), 400)
        resolved = registry.lookup_order(bom_cid)
        if resolved is None:
            return None, (jsonify({'error': 'not found', 'bom_cid': bom_cid}), 404)
        return resolved, None

    return None, (
        jsonify({'error': 'order_cid, bom_cid, or data_cid required'}),
        400,
    )


@catNode.route('/cat/node/init', methods=['POST'])
def execute_init_cat():
    try:
        order_request = request.get_json() or {}
        order_cid, err = _resolve_order_cid_from_request(order_request)
        if err is not None:
            return err
        order_request = dict(order_request)
        order_request['order_cid'] = order_cid
        order_request["order"] = json.loads(
            RUNTIME.contentMesh.cat(order_request["order_cid"])
        )
        order_request['invoice'] = json.loads(
            RUNTIME.contentMesh.cat(order_request['order']['invoice_cid'])
        )

        catFactory, updated_order_request = RUNTIME.initFactory(
            order_request, order_request["invoice"]["data_cid"]
        )
        bom_response = RUNTIME.execute(catFactory, updated_order_request)

        return jsonify(bom_response)

    except Exception as e:
        logger.error("An error occurred: %s", traceback.format_exc())
        return jsonify({'error': str(e)})
