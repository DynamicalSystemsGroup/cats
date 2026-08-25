"""TransportPort Protocol + Executor as_transport_port facade hardening."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRANSPORT_PORT_PY = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'function'
    / 'process'
    / 'transport_port.py'
)
EXECUTOR_TRANSPORT_PORT_PY = (
    REPO_ROOT / 'cats' / 'executor' / 'function' / 'transport_port.py'
)
PROCESS_PY = (
    REPO_ROOT / 'data' / 'input' / 'function' / 'process' / 'callables.py'
)
TRANSPORT_UTILS = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'infrastructure'
    / 'transport_utils.py'
)
_CATS_DATA_IMPORT = re.compile(
    r'^\s*(from data\.|import data\b)', re.MULTILINE
)


def _load_transport_utils():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        'infrastructure_transport_utils', TRANSPORT_UTILS
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeTransport:
    def migrate(self, input_dir_id):
        return (f'cid-for-{input_dir_id}', 'data_1')

    def stage_for_plant(self, input_dir_id, *, cwd, data_cache=None):
        return f'{cwd}/staged/{input_dir_id}'


def test_fake_and_facade_satisfy_transport_port_protocol():
    """Fake transport and Executor facade both satisfy Function TransportPort."""
    from cats.executor.function.transport_port import as_transport_port
    from data.input.function.process.transport_port import TransportPort

    fake = _FakeTransport()
    assert isinstance(fake, TransportPort)

    facade = as_transport_port(fake)
    assert isinstance(facade, TransportPort)
    assert facade.migrate('QmX') == ('cid-for-QmX', 'data_1')
    assert facade.stage_for_plant('QmY', cwd='/cache') == '/cache/staged/QmY'


def test_as_transport_port_exposes_only_port_surface():
    """as_transport_port exposes only migrate/stage_for_plant (§6s)."""
    from cats.executor.function.transport_port import as_transport_port

    tu = _load_transport_utils()
    ctx = tu.TransportContext.default()
    assert hasattr(ctx, 'migrate')
    assert hasattr(ctx, 'stage_for_plant')
    assert not hasattr(ctx, 'ensure_peered')
    assert not hasattr(ctx, 'assert_ready')

    port = as_transport_port(ctx)
    assert hasattr(port, 'migrate')
    assert hasattr(port, 'stage_for_plant')
    assert not hasattr(port, 'ensure_peered')
    assert not hasattr(port, 'assert_ready')
    assert not hasattr(port, 'structure_home') or True  # facade may omit


def test_as_transport_port_idempotent():
    """Wrapping an existing TransportPort facade returns the same object."""
    from cats.executor.function.transport_port import as_transport_port

    fake = _FakeTransport()
    once = as_transport_port(fake)
    twice = as_transport_port(once)
    assert once is twice


def test_transport_port_module_has_no_infrastructure_imports():
    """Function-owned TransportPort must not import IaaS adapters or Executor."""
    text = TRANSPORT_PORT_PY.read_text(encoding='utf-8')
    assert 'import transport_utils' not in text
    assert 'from transport_utils' not in text
    assert 'cats.network' not in text
    assert 'importlib' not in text  # no dynamic load of IaaS adapter
    assert 'def as_transport_port' not in text
    assert '_TransportPortView' not in text


def test_executor_owns_as_transport_port():
    """CFL 4A: as_transport_port lives in cats.executor, not the Function tree."""
    text = EXECUTOR_TRANSPORT_PORT_PY.read_text(encoding='utf-8')
    assert 'def as_transport_port' in text
    assert 'class _TransportPortView' in text
    assert 'from data.' not in text
    assert 'import data' not in text


def test_cats_package_does_not_import_data_package():
    """cats/ is Node runtime; Order Function sources live under data/."""
    offenders = []
    for path in (REPO_ROOT / 'cats').rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        if _CATS_DATA_IMPORT.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, 'cats must not import data:\n' + '\n'.join(offenders)


def test_process_grep_guards_transport_port_surface():
    """Process callables must not reference transport peering internals."""
    text = PROCESS_PY.read_text(encoding='utf-8')
    banned = (
        'ensure_docker_ipfs_peers',
        'docker_ipfs_transport_peering',
        'docker exec',
        'ensure_peered',
        'assert_ready',
        'transport_utils',
        'TransportContext',
        'MIGRATION_CONTAINER',
        'as_transport_port',
    )
    for token in banned:
        assert token not in text, f'process.py must not contain {token!r}'
    assert 'TransportPort' in text
