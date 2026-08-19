"""Flask routes for Node-hosted CAS blob GETs (PUT closed for clients)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from cats.network.cas.digest import from_ni, is_ni_or_digest, validate_digest_segment
from cats.network.cas.store import CasHttpStore
from cats.network.ldp.headers import apply_resource_headers


def register_cas_routes(app: Flask, *, cats_home: str) -> None:
    """Attach ``/ldp/cas/<digest>`` GET routes; writes via ContentMesh/Runtime only."""

    def _store() -> CasHttpStore:
        return CasHttpStore(cats_home)

    @app.route('/ldp/cas/<digest>', methods=['GET', 'HEAD', 'OPTIONS', 'PUT'])
    def ldp_cas_resource(digest: str):
        if request.method == 'PUT':
            resp = jsonify(
                {
                    'error': (
                        'CAS PUT not open; Node publishes via ContentMesh / '
                        'Runtime (CasHttpStore) only'
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
            if is_ni_or_digest(digest):
                key = from_ni(digest)
            else:
                key = validate_digest_segment(digest)
            data = _store().get(key)
        except ValueError:
            return jsonify({'error': 'invalid digest'}), 400
        if data is None:
            return jsonify({'error': 'not found'}), 404
        resp = Response(data, mimetype='application/octet-stream')
        apply_resource_headers(resp)
        return resp
