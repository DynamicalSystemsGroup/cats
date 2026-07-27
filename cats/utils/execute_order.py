"""In-process Order execution via Runtime (no Flask / HTTP).

Same Factory → Executor path as ``POST /cat/node/init``, without binding a Node.
Prefer the Node + ``contentMesh.catSubmit`` for normal Mesh demos.
"""
from __future__ import annotations

import argparse
import json
from pprint import pprint
from typing import Any

from cats import RUNTIME


def execute_order(order_cid: str) -> Any:
    """Resolve ``order_cid``, run ``initFactory`` + ``execute``, return BOM."""
    order_request = {"order_cid": order_cid}
    order_request["order"] = json.loads(RUNTIME.contentMesh.cat(order_cid))
    order_request["invoice"] = json.loads(
        RUNTIME.contentMesh.cat(order_request["order"]["invoice_cid"])
    )
    cat_factory, updated_order_request = RUNTIME.initFactory(
        order_request, order_request["invoice"]["data_cid"]
    )
    return RUNTIME.execute(cat_factory, updated_order_request)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Execute a CAT Order in-process (no Flask). "
            "Requires ContentStore readiness and a resolvable order_cid."
        )
    )
    parser.add_argument(
        "order_cid",
        help="IPFS CID of the Order JSON to execute",
    )
    args = parser.parse_args(argv)
    pprint(execute_order(args.order_cid))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
