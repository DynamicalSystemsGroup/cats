"""Named-bind JSON leaves vs pickle for Function Order slots."""
import json
import types

from cats.network.cas.content_ref import content_uri, equality_id, is_ni_or_digest

# Function package dirs addressed as process_source / infrafunction_source
# (sibling of structure/ under input/).
FUNCTION_PACKAGE_NAMES = ('process', 'infrafunction')

# Stock Order-slot public names (auto named-bind). Not slots: function_0/1.
STOCK_PROCESS_SLOT_QUALNAMES = frozenset({
    'ingress',
    'egress',
    'integration_cache',
    'process_0',
    'process_1',
})
STOCK_INFRAFUNCTION_SLOT_QUALNAMES = frozenset({'infrafunction_subproc'})
STOCK_SLOT_QUALNAMES = STOCK_PROCESS_SLOT_QUALNAMES | STOCK_INFRAFUNCTION_SLOT_QUALNAMES


def is_stock_function_callable(obj) -> bool:
    """True if ``obj`` is a stock Process/InfraFunction Order-slot callable."""
    if not isinstance(obj, types.FunctionType):
        return False
    qualname = getattr(obj, '__qualname__', None)
    module = getattr(obj, '__module__', None) or ''
    if qualname not in STOCK_SLOT_QUALNAMES:
        return False
    if qualname in STOCK_PROCESS_SLOT_QUALNAMES:
        return module == 'data.input.function.process' or module.startswith(
            'data.input.function.process.'
        )
    return module == 'data.input.function.infrafunction' or module.startswith(
        'data.input.function.infrafunction.'
    )


def named_bind_payload(source_content_id: str, module: str, qualname: str) -> dict:
    """Named-bind leaf: ``contentId`` + optional ``source_uri`` (no ``source_cid``)."""
    eid = (
        equality_id(source_content_id)
        if is_ni_or_digest(source_content_id)
        else source_content_id.strip()
    )
    payload = {
        'contentId': eid,
        'module': module,
        'qualname': qualname,
    }
    uri = content_uri(eid)
    if uri:
        payload['source_uri'] = uri
    return payload


def named_bind_source_id(spec: dict) -> str | None:
    """Equality id from a named-bind leaf (new ``contentId`` or legacy ``source_cid``)."""
    if not isinstance(spec, dict):
        return None
    for key in ('contentId', 'source_cid'):
        value = spec.get(key)
        if isinstance(value, str) and value.strip():
            value = value.strip()
            return equality_id(value) if is_ni_or_digest(value) else value
    uri = spec.get('source_uri')
    if isinstance(uri, str) and uri.strip():
        from cats.network.cas.content_ref import content_id_from_uri

        return content_id_from_uri(uri.strip())
    return None


def parse_named_bind_leaf(raw: bytes):
    """Return named-bind dict if ``raw`` is named-bind JSON, else ``None``."""
    try:
        text = raw.decode('utf-8')
        spec = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(spec, dict):
        return None
    if not isinstance(spec.get('module'), str) or not spec['module']:
        return None
    if not isinstance(spec.get('qualname'), str) or not spec['qualname']:
        return None
    if named_bind_source_id(spec) is None:
        return None
    return spec
