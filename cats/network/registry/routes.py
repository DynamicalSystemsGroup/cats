"""Flask routes for Node-local BOM registry (query index; PUT closed)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from cats.network.ldp.headers import apply_container_headers, apply_resource_headers
from cats.network.node_http import _node_base_url
from cats.network.registry.store import BomRegistry


def register_registry_routes(app: Flask, *, cats_home: str) -> None:
    """Attach ``/ldp/registry/`` GET routes; writes via Runtime.execute only."""

    def _registry() -> BomRegistry:
        return BomRegistry(cats_home)

    @app.route('/ldp/registry/', methods=['GET', 'HEAD', 'OPTIONS'])
    def registry_container():
        if request.method == 'OPTIONS':
            resp = Response(status=204)
            apply_container_headers(resp)
            return resp
        doc = _registry().container_document(base_url=_node_base_url())
        resp = jsonify(doc)
        apply_container_headers(resp)
        return resp

    @app.route(
        '/ldp/registry/boms/<bom_cid>',
        methods=['GET', 'HEAD', 'OPTIONS', 'PUT'],
    )
    def registry_bom_resource(bom_cid: str):
        if request.method == 'PUT':
            resp = jsonify(
                {
                    'error': (
                        'Registry PUT not open; Node indexes via '
                        'Runtime.execute (BomRegistry) only'
                    )
                }
            )
            resp.status_code = 405
            apply_resource_headers(resp)
            resp.headers['Allow'] = 'GET, HEAD, OPTIONS'
            return resp
        if request.method == 'OPTIONS':
            resp = Response(status=204)
            apply_resource_headers(resp)
            return resp
        try:
            record = _registry().get(bom_cid)
        except ValueError:
            return jsonify({'error': 'invalid bom_cid'}), 400
        if record is None:
            return jsonify({'error': 'not found'}), 404
        resp = jsonify(record)
        apply_resource_headers(resp)
        return resp

    @app.route(
        '/ldp/registry/by-data/<data_cid>',
        methods=['GET', 'HEAD', 'OPTIONS'],
    )
    def registry_by_data(data_cid: str):
        if request.method == 'OPTIONS':
            resp = Response(status=204)
            apply_resource_headers(resp)
            return resp
        try:
            bom_cids = _registry().lookup_bom(data_cid)
        except ValueError:
            return jsonify({'error': 'invalid data_cid'}), 400
        resp = jsonify({'data_cid': data_cid, 'bom_cids': bom_cids})
        apply_resource_headers(resp)
        return resp

    @app.route(
        '/ldp/registry/by-order/<order_cid>',
        methods=['GET', 'HEAD', 'OPTIONS'],
    )
    def registry_by_order(order_cid: str):
        if request.method == 'OPTIONS':
            resp = Response(status=204)
            apply_resource_headers(resp)
            return resp
        try:
            bom_cids = _registry().lookup_by_order(order_cid)
        except ValueError:
            return jsonify({'error': 'invalid order_cid'}), 400
        resp = jsonify({'order_cid': order_cid, 'bom_cids': bom_cids})
        apply_resource_headers(resp)
        return resp

    @app.route(
        '/ldp/registry/by-content/<digest>',
        methods=['GET', 'HEAD', 'OPTIONS'],
    )
    def registry_by_content(digest: str):
        if request.method == 'OPTIONS':
            resp = Response(status=204)
            apply_resource_headers(resp)
            return resp
        from cats.network.cas import LocatorIndex

        try:
            doc = LocatorIndex(cats_home).get(digest)
        except ValueError:
            return jsonify({'error': 'invalid content_id'}), 400
        if doc is None:
            return jsonify({'error': 'not found', 'content_id': digest}), 404
        resp = jsonify(doc)
        apply_resource_headers(resp)
        return resp
