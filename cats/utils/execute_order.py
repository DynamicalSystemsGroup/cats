"""In-process Order execution via Runtime (no Flask / HTTP).

Same Factory → Executor path as ``POST /cat/node/init``, without binding a Node.
Prefer the Node + ``contentMesh.catSubmit`` for normal Mesh demos.
"""
from __future__ import annotations

import argparse
import json
from pprint import pprint
from typing import Any

from cats import CATS_HOME, RUNTIME
from cats.network.cas import ref_id, ref_uri


def execute_order(order_id: str) -> Any:
    """Resolve ``order_id``, run ``initFactory`` + ``execute``, return BOM."""
    order_request = {"order_id": order_id}
    order_request["order"] = json.loads(RUNTIME.contentMesh.cat(order_id))
    invoice_locator = ref_uri(order_request["order"], 'invoice') or ref_id(
        order_request["order"], 'invoice', cats_home=CATS_HOME
    )
    if not invoice_locator:
        raise RuntimeError('Order missing invoice_uri / invoice_cid')
    order_request["invoice"] = json.loads(
        RUNTIME.contentMesh.cat(invoice_locator)
    )
    init_data_id = ref_id(
        order_request["invoice"], 'data', cats_home=CATS_HOME
    )
    if not init_data_id:
        raise RuntimeError('Invoice missing data_uri / data_cid')
    cat_factory, updated_order_request = RUNTIME.initFactory(
        order_request, init_data_id
    )
    return RUNTIME.execute(cat_factory, updated_order_request)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Execute a CAT Order in-process (no Flask). "
            "Requires ContentStore readiness and a resolvable order_id."
        )
    )
    parser.add_argument(
        "order_id",
        help="Content id of the Order JSON to execute",
    )
    args = parser.parse_args(argv)
    pprint(execute_order(args.order_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
