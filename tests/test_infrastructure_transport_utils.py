"""Unit tests for InfraStructure directory-model transport_utils / TransportContext."""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRANSPORT_UTILS = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'infrastructure'
    / 'transport_utils.py'

)
PROCESS_PY = (
    REPO_ROOT / 'data' / 'input' / 'function' / 'process' / 'callables.py'
)


def _load_transport_utils():
    spec = importlib.util.spec_from_file_location(
        'infrastructure_transport_utils', TRANSPORT_UTILS
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tu = _load_transport_utils()


class _FakeCompleted:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeTransport:
    def migrate(self, input_dir_cid):
        return (f'cid-for-{input_dir_cid}', 'data_1')

    def stage_for_plant(self, input_dir_cid, *, cwd, data_cache=None):
        return f'{cwd}/staged/{input_dir_cid}'


def test_assert_ready_fails_when_containers_missing(monkeypatch):
    monkeypatch.setattr(tu, '_container_running', lambda *_: False)
    ctx = tu.TransportContext.default()
    try:
        ctx.assert_ready()
        assert False, 'expected RuntimeError'
    except RuntimeError as exc:
        assert 'not ready' in str(exc)


def test_assert_ready_ok_when_both_running(monkeypatch):
    monkeypatch.setattr(tu, '_container_running', lambda *_: True)
    tu.TransportContext.default().assert_ready()


def test_ensure_peered_noops_when_migration_missing(monkeypatch):
    calls = []
    monkeypatch.setattr(tu, '_container_running', lambda name: False)
    monkeypatch.setattr(
        tu, '_swarm_connect', lambda *a, **k: calls.append(a)
    )
    tu.TransportContext.default().ensure_peered()
    assert calls == []


def test_ensure_peered_connects_peers(monkeypatch):
    connects = []

    def _running(name):
        return True

    monkeypatch.setattr(tu, '_container_running', _running)
    monkeypatch.setattr(tu, '_host_peer_id', lambda: 'hostpeer')
    monkeypatch.setattr(tu, '_container_ip', lambda c: '10.0.0.2')
    monkeypatch.setattr(tu, '_container_peer_id', lambda c: 'peerid')
    monkeypatch.setattr(
        tu, '_swarm_connect', lambda c, m: connects.append((c, m))
    )
    monkeypatch.setattr(
        tu, '_run', lambda *a, **k: _FakeCompleted(0)
    )

    tu.TransportContext.default().ensure_peered()
    assert any('host.docker.internal' in m for _, m in connects)
    assert any(tu.INTEGRATION_CONTAINER == c for c, _ in connects)


def test_migrate_parses_cid(monkeypatch, tmp_path):
    monkeypatch.setattr(tu, '_container_running', lambda *_: True)
    monkeypatch.setattr(tu.time, 'time', lambda: 1700000000)
    monkeypatch.setattr(
        tu,
        '_run',
        lambda cmd, **k: _FakeCompleted(
            0, stdout='added QmTestCID data_1700000000\n'
        ),
    )

    ctx = tu.TransportContext.default(structure_home=str(tmp_path))
    cid, name = ctx.migrate('QmInput')
    assert cid == 'QmTestCID'
    assert name == 'data_1700000000'


def test_stage_for_plant_returns_host_path(monkeypatch, tmp_path):
    monkeypatch.setattr(tu, '_container_running', lambda *_: True)
    monkeypatch.setattr(tu.time, 'time', lambda: 42)
    data_cache = tmp_path / 'outputs'
    staged = data_cache / 'staged_42'
    staged.mkdir(parents=True)
    monkeypatch.setattr(
        tu, '_run', lambda *a, **k: _FakeCompleted(0)
    )

    ctx = tu.TransportContext.default()
    path = ctx.stage_for_plant(
        'QmIn', cwd=str(tmp_path), data_cache=str(data_cache)
    )
    assert path == str(staged)


def test_cli_status_ready(monkeypatch):
    monkeypatch.setattr(
        tu.TransportContext, 'assert_ready', lambda self: None
    )
    assert tu._main(['status']) == 0


def test_cli_status_not_ready(monkeypatch):
    def _raise(self):
        raise RuntimeError('missing')

    monkeypatch.setattr(tu.TransportContext, 'assert_ready', _raise)
    assert tu._main(['status']) == 1


def test_cli_ensure_peered(monkeypatch):
    calls = []
    monkeypatch.setattr(
        tu.TransportContext,
        'ensure_peered',
        lambda self: calls.append(True),
    )
    assert tu._main(['ensure-peered']) == 0
    assert calls == [True]


def test_no_cats_network_peering_module():
    peering = (
        REPO_ROOT / 'cats' / 'network' / 'docker_ipfs_transport_peering.py'
    )
    assert not peering.exists()


def test_process_port_uses_fake_transport():
    from data.input.function import process as proc

    fake = _FakeTransport()
    assert proc.ingress('QmA', fake) == ('cid-for-QmA', 'data_1')
    assert proc.egress('QmB', fake) == 'cid-for-QmB'
    assert proc.integration_cache('QmC', '/cache', fake) == '/cache/staged/QmC'


def test_grep_guard_no_ensure_docker_ipfs_peers_in_process():
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


def test_orphan_ipfs_connect_peers_sh_removed():
    """Sole peering path is transport_utils; shell script must stay gone."""
    orphan = (
        REPO_ROOT
        / 'data'
        / 'input'
        / 'structure'
        / 'infrastructure'
        / 'ipfs_connect_peers.sh'

    )
    assert not orphan.exists()


def test_tf_peering_resource_every_apply_not_on_compose_create():
    """Option B: Compose create-once; peering mutates every apply via triggers."""
    main_tf = (
        REPO_ROOT
        / 'data'
        / 'input'
        / 'structure'
        / 'infrastructure'
        / 'main.tf'

    )
    text = main_tf.read_text(encoding='utf-8')
    assert 'resource "shell_script" "ipfs_transport_peering"' in text
    assert 'timestamp()' in text
    # Compose create block must not call ensure-peered (peering resource does).
    compose_start = text.index('resource "shell_script" "docker_compose_ipfs_transport"')
    peering_start = text.index('resource "shell_script" "ipfs_transport_peering"')
    compose_block = text[compose_start:peering_start]
    assert 'ensure-peered' not in compose_block
    peering_block = text[peering_start:]
    assert 'ensure-peered' in peering_block


def test_transport_assert_wraps_assert_ready(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from cats.executor.structure import InfraStructure

    infra = InfraStructure.__new__(InfraStructure)
    infra.INPUT_STRUCTURE_HOME = str(tmp_path)
    infra.service = SimpleNamespace()

    monkeypatch.setattr(
        infra,
        'transport_context',
        lambda: SimpleNamespace(
            assert_ready=lambda: (_ for _ in ()).throw(
                RuntimeError('missing containers')
            )
        ),
    )
    try:
        infra.transport_assert()
        raised = False
    except RuntimeError as exc:
        raised = True
        assert 'ipfs_transport_peering' in str(exc)
        assert 'missing containers' in str(exc)
    assert raised
