"""CAT Mesh network package — content-store mesh + Order helpers.

Public imports are stable; implementation lives in sibling modules.
Plant CoD transport: ``cats.network.plant_transport.CoDTransport``.
W3C Phase 1/1b seams: ``feedback`` (JSON-LD/PROV + Data Integrity) /
``identity`` (DID + signing material). Phase 2a: ``AddressStore`` for
gateway-first CID reads + verify; ``ldp`` Node-hosted BOM control plane.
"""
from cats.network.address_store import (
    AddressStore,
    CidIntegrityError,
    GatewayError,
    IpfsHttpGateway,
    verify_bytes_match_cid,
)
from cats.network.ldp import (
    BomLdpStore,
    LdpEnvelopeError,
    bom_ldp_path,
    bom_ldp_uri,
    fetch_bom_envelope,
    register_ldp_routes,
)
from cats.network.bootstrap import (
    _bootstrap_content_store_utils_path,
    _load_bootstrap_content_store_module,
)
from cats.network.content_mesh import ContentMesh
from cats.network.feedback import (
    attach_node_did,
    build_execution_bom,
    sign_execution_bom,
    verify_execution_bom,
)
from cats.network.identity import load_node_signing_material, node_did, node_uri
from cats.network.named_binds import (
    STOCK_INFRAFUNCTION_SLOT_QUALNAMES,
    STOCK_PROCESS_SLOT_QUALNAMES,
    STOCK_SLOT_QUALNAMES,
    is_stock_function_callable,
    named_bind_payload,
    parse_named_bind_leaf,
)
from cats.network.node_http import (
    _activity_spinner,
    _node_base_url,
    _node_init_endpoint,
)
from cats.network.packaging import (
    FUNCTION_PACKAGE_NAMES,
    STRUCTURE_ROOT_DIRNAME,
    STRUCTURE_ROOT_FILES,
    materialize_structure_root_files,
    resolve_function_package_dirs,
    stage_function_package,
    stage_structure_root,
)
from cats.network.plant_transport import CoDTransport

__all__ = [
    'ContentMesh',
    'AddressStore',
    'CidIntegrityError',
    'GatewayError',
    'IpfsHttpGateway',
    'verify_bytes_match_cid',
    'BomLdpStore',
    'LdpEnvelopeError',
    'bom_ldp_path',
    'bom_ldp_uri',
    'fetch_bom_envelope',
    'register_ldp_routes',
    'CoDTransport',
    'node_did',
    'node_uri',
    'load_node_signing_material',
    'build_execution_bom',
    'attach_node_did',
    'sign_execution_bom',
    'verify_execution_bom',
    'STRUCTURE_ROOT_DIRNAME',
    'STRUCTURE_ROOT_FILES',
    'FUNCTION_PACKAGE_NAMES',
    'STOCK_PROCESS_SLOT_QUALNAMES',
    'STOCK_INFRAFUNCTION_SLOT_QUALNAMES',
    'STOCK_SLOT_QUALNAMES',
    'stage_structure_root',
    'materialize_structure_root_files',
    'resolve_function_package_dirs',
    'stage_function_package',
    'is_stock_function_callable',
    'named_bind_payload',
    'parse_named_bind_leaf',
    '_node_base_url',
    '_node_init_endpoint',
    '_activity_spinner',
    '_bootstrap_content_store_utils_path',
    '_load_bootstrap_content_store_module',
]
