"""LDP Link / Allow header helpers for Node-hosted control-plane resources."""
from __future__ import annotations

LDP_NS = 'http://www.w3.org/ns/ldp#'
LDP_RESOURCE = f'{LDP_NS}Resource'
LDP_RDF_SOURCE = f'{LDP_NS}RDFSource'
LDP_BASIC_CONTAINER = f'{LDP_NS}BasicContainer'


def resource_link_header() -> str:
    """RFC 8288 Link value marking an LDP RDF Source / Resource."""
    return (
        f'<{LDP_RESOURCE}>; rel="type", '
        f'<{LDP_RDF_SOURCE}>; rel="type"'
    )


def container_link_header() -> str:
    """RFC 8288 Link value marking an LDP Basic Container."""
    return (
        f'<{LDP_RESOURCE}>; rel="type", '
        f'<{LDP_BASIC_CONTAINER}>; rel="type"'
    )


def apply_resource_headers(response) -> None:
    """Set LDP headers on a Flask response for a BOM resource."""
    response.headers['Link'] = resource_link_header()
    response.headers['Allow'] = 'GET, HEAD, OPTIONS'
    response.headers['Content-Type'] = 'application/ld+json'


def apply_container_headers(response) -> None:
    """Set LDP headers on a Flask response for the boms container."""
    response.headers['Link'] = container_link_header()
    response.headers['Allow'] = 'GET, HEAD, OPTIONS'
    response.headers['Content-Type'] = 'application/ld+json'
