"""TransportPort Protocol + as_transport_port facade hardening."""
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
    def migrate(self, input_dir_cid):
        return (f'cid-for-{input_dir_cid}', 'data_1')

    def stage_for_plant(self, input_dir_cid, *, cwd, data_cache=None):
        return f'{cwd}/staged/{input_dir_cid}'


def test_fake_and_facade_satisfy_transport_port_protocol():
    from data.input.function.process.transport_port import (
        TransportPort,
        as_transport_port,
    )

    fake = _FakeTransport()
    assert isinstance(fake, TransportPort)

    facade = as_transport_port(fake)
    assert isinstance(facade, TransportPort)
    assert facade.migrate('QmX') == ('cid-for-QmX', 'data_1')
    assert facade.stage_for_plant('QmY', cwd='/cache') == '/cache/staged/QmY'


def test_as_transport_port_strips_structure_surface():
    from data.input.function.process.transport_port import as_transport_port

    tu = _load_transport_utils()
    ctx = tu.TransportContext.default()
    assert hasattr(ctx, 'ensure_peered')
    assert hasattr(ctx, 'assert_ready')
    assert hasattr(ctx, 'migration_container')

    port = as_transport_port(ctx)
    assert hasattr(port, 'migrate')
    assert hasattr(port, 'stage_for_plant')
    assert not hasattr(port, 'ensure_peered')
    assert not hasattr(port, 'assert_ready')
    assert not hasattr(port, 'migration_container')
    assert not hasattr(port, 'integration_container')


def test_as_transport_port_idempotent():
    from data.input.function.process.transport_port import as_transport_port

    fake = _FakeTransport()
    once = as_transport_port(fake)
    twice = as_transport_port(once)
    assert once is twice


def test_transport_port_module_has_no_infrastructure_imports():
    text = TRANSPORT_PORT_PY.read_text(encoding='utf-8')
    assert 'import transport_utils' not in text
    assert 'from transport_utils' not in text
    assert 'cats.network' not in text
    assert 'importlib' not in text  # no dynamic load of IaaS adapter


def test_process_grep_guards_transport_port_surface():
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
    )
    for token in banned:
        assert token not in text, f'process.py must not contain {token!r}'
    assert 'TransportPort' in text
