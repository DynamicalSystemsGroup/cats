"""Flask routes for Node-hosted LDP BOM control plane."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from cats.network.ldp.bom_store import BomLdpStore
from cats.network.ldp.headers import apply_container_headers, apply_resource_headers
from cats.network.node_http import _node_base_url


def register_ldp_routes(app: Flask, *, cats_home: str) -> None:
    """Attach ``/ldp/boms/`` routes; publish remains Runtime-only (no open PUT)."""

    def _store() -> BomLdpStore:
        return BomLdpStore(cats_home)

    @app.route('/ldp/boms/', methods=['GET', 'HEAD', 'OPTIONS'])
    def ldp_boms_container():
        if request.method == 'OPTIONS':
            resp = Response(status=204)
            apply_container_headers(resp)
            return resp
        doc = _store().container_document(base_url=_node_base_url())
        resp = jsonify(doc)
        apply_container_headers(resp)
        return resp

    @app.route('/ldp/boms/<bom_cid>', methods=['GET', 'HEAD', 'OPTIONS', 'PUT'])
    def ldp_bom_resource(bom_cid: str):
        if request.method == 'PUT':
            # Slice-1: open-world PUT deferred until Solid WebID/ACL.
            resp = jsonify(
                {
                    'error': (
                        'LDP PUT not open; Node publishes via Runtime.execute '
                        '(BomLdpStore) only'
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
            bom = _store().get(bom_cid)
        except ValueError:
            return jsonify({'error': 'invalid bom_cid'}), 400
        if bom is None:
            return jsonify({'error': 'not found'}), 404
        resp = jsonify(bom)
        apply_resource_headers(resp)
        return resp
