"""Named-bind JSON leaves vs pickle for Function Order slots."""
import json
import types

# Function package dirs CIDed as function_cid.process_source_cid /
# infrafunction_source_cid (sibling of structure/ under input/).
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


def named_bind_payload(source_cid: str, module: str, qualname: str) -> dict:
    return {
        'source_cid': source_cid,
        'module': module,
        'qualname': qualname,
    }


def parse_named_bind_leaf(raw: bytes):
    """Return named-bind dict if ``raw`` is named-bind JSON, else ``None``."""
    try:
        text = raw.decode('utf-8')
        spec = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(spec, dict):
        return None
    if not all(k in spec for k in ('source_cid', 'module', 'qualname')):
        return None
    if not all(isinstance(spec[k], str) and spec[k] for k in (
        'source_cid', 'module', 'qualname',
    )):
        return None
    return spec
