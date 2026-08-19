"""Flask routes for Node-hosted LDP BOM + Order/Invoice control/data plane."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from cats.network.ldp.bom_store import BomLdpStore
from cats.network.ldp.headers import apply_container_headers, apply_resource_headers
from cats.network.ldp.resource_store import JsonResourceStore
from cats.network.node_http import _node_base_url


def _put_not_allowed(message: str) -> Response:
    resp = jsonify({'error': message})
    resp.status_code = 405
    apply_resource_headers(resp)
    resp.headers['Allow'] = 'GET, HEAD, OPTIONS'
    return resp


def register_ldp_routes(app: Flask, *, cats_home: str) -> None:
    """Attach ``/ldp/boms|invoices|orders/``; publish remains Runtime/Order only."""

    def _bom_store() -> BomLdpStore:
        return BomLdpStore(cats_home)

    @app.route('/ldp/boms/', methods=['GET', 'HEAD', 'OPTIONS'])
    def ldp_boms_container():
        if request.method == 'OPTIONS':
            resp = Response(status=204)
            apply_container_headers(resp)
            return resp
        doc = _bom_store().container_document(base_url=_node_base_url())
        resp = jsonify(doc)
        apply_container_headers(resp)
        return resp

    @app.route('/ldp/boms/<bom_cid>', methods=['GET', 'HEAD', 'OPTIONS', 'PUT'])
    def ldp_bom_resource(bom_cid: str):
        if request.method == 'PUT':
            return _put_not_allowed(
                'LDP PUT not open; Node publishes via Runtime.execute '
                '(BomLdpStore) only'
            )
        if request.method == 'OPTIONS':
            resp = Response(status=204)
            apply_resource_headers(resp)
            return resp
        try:
            bom = _bom_store().get(bom_cid)
        except ValueError:
            return jsonify({'error': 'invalid bom_cid'}), 400
        if bom is None:
            return jsonify({'error': 'not found'}), 404
        resp = jsonify(bom)
        apply_resource_headers(resp)
        return resp

    def _register_json_kind(kind: str) -> None:
        def store() -> JsonResourceStore:
            return JsonResourceStore(cats_home, kind)  # type: ignore[arg-type]

        @app.route(
            f'/ldp/{kind}/',
            methods=['GET', 'HEAD', 'OPTIONS'],
            endpoint=f'ldp_{kind}_container',
        )
        def ldp_json_container():
            if request.method == 'OPTIONS':
                resp = Response(status=204)
                apply_container_headers(resp)
                return resp
            doc = store().container_document(base_url=_node_base_url())
            resp = jsonify(doc)
            apply_container_headers(resp)
            return resp

        @app.route(
            f'/ldp/{kind}/<content_id>',
            methods=['GET', 'HEAD', 'OPTIONS', 'PUT'],
            endpoint=f'ldp_{kind}_resource',
        )
        def ldp_json_resource(content_id: str):
            if request.method == 'PUT':
                return _put_not_allowed(
                    f'LDP PUT not open; Node publishes {kind} via Runtime/Order only'
                )
            if request.method == 'OPTIONS':
                resp = Response(status=204)
                apply_resource_headers(resp)
                return resp
            try:
                obj = store().get(content_id)
            except ValueError:
                return jsonify({'error': f'invalid {kind} id'}), 400
            if obj is None:
                return jsonify({'error': 'not found'}), 404
            resp = jsonify(obj)
            apply_resource_headers(resp)
            return resp

    _register_json_kind('invoices')
    _register_json_kind('orders')
