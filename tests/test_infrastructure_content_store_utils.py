"""Unit tests for InfraStructure directory-model content_store_utils / ContentStore."""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_STORE_UTILS = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'infrastructure'
    / 'content_store_utils.py'

)


def _load_content_store_utils():
    spec = importlib.util.spec_from_file_location(
        'infrastructure_content_store_utils', CONTENT_STORE_UTILS
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


csu = _load_content_store_utils()


class _FakeResponse:
    def __init__(self, ok):
        self.ok = ok


class _FakeCompleted:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stdout = ''
        self.stderr = ''


def test_is_ready_true_when_api_ok(monkeypatch):
    """is_ready is True when the Kubo HTTP id probe returns ok."""
    monkeypatch.setattr(
        csu.requests, 'post', lambda *a, **k: _FakeResponse(True)
    )
    assert csu.ContentStore.is_ready() is True


def test_is_ready_false_when_connection_refused(monkeypatch):
    """is_ready is False when the probe raises ConnectionError."""
    def _raise(*a, **k):
        raise csu.requests.ConnectionError('refused')

    monkeypatch.setattr(csu.requests, 'post', _raise)
    assert csu.ContentStore.is_ready() is False


def test_is_ready_false_when_http_error(monkeypatch):
    """is_ready is False when the probe response is not ok."""
    monkeypatch.setattr(
        csu.requests, 'post', lambda *a, **k: _FakeResponse(False)
    )
    assert csu.ContentStore.is_ready() is False


def test_ensure_api_already_up_skips_heal_and_start(monkeypatch):
    """ensure is a no-op for heal/daemon start when the API is already up."""
    heal_calls = []
    popen_calls = []

    monkeypatch.setattr(
        csu.ContentStore, 'is_ready', lambda *a, **k: True
    )
    monkeypatch.setattr(
        csu, '_heal_stale_repo_lock', lambda: heal_calls.append(True)
    )
    monkeypatch.setattr(
        csu.subprocess,
        'Popen',
        lambda *a, **k: popen_calls.append(a) or None,
    )

    csu.ContentStore.ensure()
    assert heal_calls == []
    assert popen_calls == []


def test_heal_unlinks_stale_lock_when_no_daemon_process(monkeypatch, tmp_path):
    """Heal removes a stale repo.lock when no holder or daemon PIDs exist."""
    lock_path = tmp_path / 'repo.lock'
    lock_path.write_text('stale')

    monkeypatch.setattr(csu.ContentStore, 'is_ready', lambda *a, **k: False)
    monkeypatch.setattr(csu, '_repo_lock_path', lambda: str(lock_path))
    monkeypatch.setattr(csu, '_lock_holder_pids', lambda *_: [])
    monkeypatch.setattr(csu, '_ipfs_daemon_pids', lambda: [])
    monkeypatch.setattr(csu.time, 'sleep', lambda *_: None)
    monkeypatch.setattr(
        csu.subprocess,
        'run',
        lambda *a, **k: _FakeCompleted(0),
    )

    csu._heal_stale_repo_lock()
    assert not lock_path.exists()


def test_heal_terminates_lock_holders_then_unlinks(monkeypatch, tmp_path):
    """Heal terminates lock-holder PIDs, then unlinks the repo lock."""
    lock_path = tmp_path / 'repo.lock'
    lock_path.write_text('held')
    terminated = []

    monkeypatch.setattr(csu.ContentStore, 'is_ready', lambda *a, **k: False)
    monkeypatch.setattr(csu, '_repo_lock_path', lambda: str(lock_path))
    monkeypatch.setattr(csu, '_ipfs_daemon_pids', lambda: [])
    monkeypatch.setattr(
        csu, '_terminate_pids', lambda pids, **k: terminated.extend(pids)
    )
    monkeypatch.setattr(csu.time, 'sleep', lambda *_: None)
    monkeypatch.setattr(
        csu.subprocess,
        'run',
        lambda *a, **k: _FakeCompleted(0),
    )

    holders = {'first': True}

    def _holders_after_kill(_path=None):
        if holders.pop('first', False):
            return [23385]
        return []

    monkeypatch.setattr(csu, '_lock_holder_pids', _holders_after_kill)

    csu._heal_stale_repo_lock()
    assert terminated == [23385]
    assert not lock_path.exists()


def test_cli_status_ready(monkeypatch):
    """CLI status exits 0 when ContentStore reports ready."""
    monkeypatch.setattr(csu.ContentStore, 'is_ready', lambda *a, **k: True)
    assert csu._main(['status']) == 0


def test_cli_status_not_ready(monkeypatch):
    """CLI status exits 1 when ContentStore reports not ready."""
    monkeypatch.setattr(csu.ContentStore, 'is_ready', lambda *a, **k: False)
    assert csu._main(['status']) == 1


def test_cli_ensure_invokes_content_store(monkeypatch):
    """CLI ensure delegates to ContentStore.ensure."""
    calls = []
    monkeypatch.setattr(
        csu.ContentStore, 'ensure', lambda **k: calls.append(True)
    )
    assert csu._main(['ensure']) == 0
    assert calls == [True]


def test_clients_no_longer_export_owned_daemon_api():
    """cats.network.clients no longer exports Node-owned daemon lifecycle APIs."""
    import cats.network.clients as clients

    assert not hasattr(clients, 'shutdown_owned_daemon')
    assert not hasattr(clients, '_host_daemon_owned')
    assert not hasattr(clients, 'ipfs')


def test_ipfs_api_id_url_defaults_match_connect(monkeypatch):
    """ContentStore probe and CatsIPFSClient.connect share IPFS_API_* defaults."""
    monkeypatch.delenv('CATS_IPFS_API_ID_URL', raising=False)
    monkeypatch.delenv('IPFS_API_HOST', raising=False)
    monkeypatch.delenv('IPFS_API_PORT', raising=False)
    assert csu._ipfs_api_id_url() == 'http://127.0.0.1:5001/api/v0/id'

    from cats.network.clients.ipfs_client import connect

    client = connect()
    assert f'{client._client.base_url}/id' == csu._ipfs_api_id_url()


def test_ipfs_api_id_url_follows_ipfs_api_host_port(monkeypatch):
    """Probe URL follows IPFS_API_HOST / IPFS_API_PORT when set."""
    monkeypatch.delenv('CATS_IPFS_API_ID_URL', raising=False)
    monkeypatch.setenv('IPFS_API_HOST', '10.0.0.9')
    monkeypatch.setenv('IPFS_API_PORT', '5009')
    assert csu._ipfs_api_id_url() == 'http://10.0.0.9:5009/api/v0/id'


def test_ipfs_api_id_url_full_override_wins(monkeypatch):
    """CATS_IPFS_API_ID_URL overrides host/port env vars."""
    monkeypatch.setenv('CATS_IPFS_API_ID_URL', 'http://example:1/api/v0/id')
    monkeypatch.setenv('IPFS_API_HOST', '10.0.0.9')
    monkeypatch.setenv('IPFS_API_PORT', '5009')
    assert csu._ipfs_api_id_url() == 'http://example:1/api/v0/id'
