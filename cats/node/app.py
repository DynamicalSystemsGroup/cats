"""Flask peer-edge HTTP API for CAT Node."""
from __future__ import annotations

import logging
import json
import os
import traceback

from flask import Flask, request, jsonify

from cats import RUNTIME

catNode = Flask(__name__)

# Overridable so multiple CAT Node peers can eventually run side-by-side
# (e.g. simulating a local mesh). ContentMesh Order endpoints use the same
# CAT_NODE_HOST / CAT_NODE_PORT defaults via `_node_base_url()`.
HOST = os.environ.get('CAT_NODE_HOST', '127.0.0.1')
PORT = int(os.environ.get('CAT_NODE_PORT', 5000))

logger = logging.getLogger(__name__)


@catNode.route('/cat/node/init', methods=['POST'])
def execute_init_cat():
    try:
        order_request = request.get_json()
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
