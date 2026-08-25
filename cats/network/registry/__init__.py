"""Phase 2a BOM registry — Control-Feedback index (before Phase 2b)."""
from cats.network.registry.content_equiv import (
    assert_bom_content_equiv,
    assert_bom_subcomponent_equiv,
    assert_fetch_equiv,
    assert_invoice_content_equiv,
    assert_invoice_subcomponent_equiv,
    assert_order_content_equiv,
    assert_order_subcomponent_equiv,
)
from cats.network.registry.handoff import (
    assert_control_plane_handoff_coherence,
    assert_input_invoice_slots,
    assert_order_function_slots,
    assert_order_structure_slots,
    make_content_fetch_ref,
    resolve_handoff_invoice_uri,
)
from cats.network.registry.parity import (
    assert_locator_index_parity,
    assert_registry_bom_parity,
    assert_registry_by_data_parity,
    assert_registry_by_order_parity,
    assert_registry_index_parity,
    registry_path_key,
)
from cats.network.registry.projection import assert_handoff_projection_complete
from cats.network.registry.reachability import assert_registry_claims_reachable
from cats.network.registry.routes import register_registry_routes
from cats.network.registry.store import (
    AmbiguousBomError,
    BomRegistry,
    RegistryError,
    build_record,
    project_record,
)

__all__ = [
    'AmbiguousBomError',
    'BomRegistry',
    'RegistryError',
    'assert_bom_content_equiv',
    'assert_bom_subcomponent_equiv',
    'assert_control_plane_handoff_coherence',
    'assert_fetch_equiv',
    'assert_handoff_projection_complete',
    'assert_input_invoice_slots',
    'assert_invoice_content_equiv',
    'assert_invoice_subcomponent_equiv',
    'assert_locator_index_parity',
    'assert_order_content_equiv',
    'assert_order_function_slots',
    'assert_order_structure_slots',
    'assert_order_subcomponent_equiv',
    'assert_registry_bom_parity',
    'assert_registry_by_data_parity',
    'assert_registry_by_order_parity',
    'assert_registry_claims_reachable',
    'assert_registry_index_parity',
    'build_record',
    'make_content_fetch_ref',
    'project_record',
    'register_registry_routes',
    'registry_path_key',
    'resolve_handoff_invoice_uri',
]
