"""CAT Node identity seams (DID attribution + signing material + HTTP URI)."""
from cats.network.identity.node_did import (
    did_key_verification_method,
    ed25519_public_key_to_did_key,
    load_node_signing_material,
    node_did,
)
from cats.network.identity.node_uri import node_uri
from cats.network.identity.webid import (
    build_webid_document,
    webid_uri,
    write_webid_document,
)

__all__ = [
    'node_did',
    'node_uri',
    'load_node_signing_material',
    'ed25519_public_key_to_did_key',
    'did_key_verification_method',
    'webid_uri',
    'build_webid_document',
    'write_webid_document',
]
