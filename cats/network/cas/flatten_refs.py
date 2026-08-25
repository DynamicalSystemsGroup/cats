"""Recursively inline ``*_uri`` refs in nested dicts (drop uri keys once expanded)."""
from __future__ import annotations

from collections.abc import Callable, Collection, Set
from typing import Any

FetchRef = Callable[[str, str], Any]
"""``fetch(stem, uri) -> payload``. Caller remaps ``uri`` to a locator if needed."""


def flatten_uri_dict(
    obj: Any,
    fetch: FetchRef,
    *,
    max_depth: int = 8,
    visited: Set[str] | None = None,
    stems: Collection[str] | None = None,
) -> Any:
    """Return a copy of ``obj`` with ``*_uri`` slots inlined under their stems.

    For each ``{stem}_uri`` string at a dict level (optionally filtered by
    ``stems``), call ``fetch(stem, uri)``, place the result at ``stem``, and
    omit ``{stem}_uri`` / legacy ``{stem}_cid``. Nested dicts and list items
    are walked the same way until ``max_depth`` expansions are exhausted.

    Cycles: if ``uri`` is already in ``visited``, keep ``{stem}_uri`` and do
    not fetch again. Non-dict / non-list payloads are stored as-is.
    """
    seen: set[str] = set(visited) if visited is not None else set()
    allow = set(stems) if stems is not None else None
    return _flatten(obj, fetch, max_depth=max_depth, visited=seen, allow=allow)


def _flatten(
    obj: Any,
    fetch: FetchRef,
    *,
    max_depth: int,
    visited: set[str],
    allow: set[str] | None,
) -> Any:
    if isinstance(obj, list):
        return [
            _flatten(
                item, fetch, max_depth=max_depth, visited=visited, allow=allow
            )
            for item in obj
        ]
    if not isinstance(obj, dict):
        return obj

    uri_by_stem: dict[str, str] = {}
    for key, value in obj.items():
        if not isinstance(key, str) or not key.endswith('_uri'):
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        stem = key[: -len('_uri')]
        if allow is not None and stem not in allow:
            continue
        uri_by_stem[stem] = value.strip()

    skip: set[str] = set()
    for stem in uri_by_stem:
        skip.add(f'{stem}_uri')
        skip.add(f'{stem}_cid')

    out: dict[str, Any] = {}
    for key, value in obj.items():
        if key in skip:
            continue
        if key in uri_by_stem:
            # Prefer fetched payload over any pre-existing stem value.
            continue
        if isinstance(value, (dict, list)):
            out[key] = _flatten(
                value,
                fetch,
                max_depth=max_depth,
                visited=visited,
                allow=allow,
            )
        else:
            out[key] = value

    for stem, uri in uri_by_stem.items():
        if max_depth <= 0 or uri in visited:
            out[f'{stem}_uri'] = uri
            continue
        payload = fetch(stem, uri)
        child_visited = visited | {uri}
        if isinstance(payload, (dict, list)):
            out[stem] = _flatten(
                payload,
                fetch,
                max_depth=max_depth - 1,
                visited=child_visited,
                allow=allow,
            )
        else:
            out[stem] = payload

    return out
