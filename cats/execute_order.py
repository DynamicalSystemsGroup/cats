"""CLI entrypoint: ``python -m cats.execute_order <order_cid>``.

Implementation lives in ``cats.utils.execute_order``.
"""
from cats.utils.execute_order import main

if __name__ == "__main__":
    raise SystemExit(main())
