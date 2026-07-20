"""Unit tests for host IPFS daemon readiness probe (HTTP API, not bare ipfs id)."""
import cats.network.clients as clients


class _FakeResponse:
    def __init__(self, ok):
        self.ok = ok


class _FakeCompleted:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stdout = ''
        self.stderr = ''


def test_ipfs_is_running_true_when_api_ok(monkeypatch):
    monkeypatch.setattr(
        clients.requests, 'post', lambda *a, **k: _FakeResponse(True)
    )
    assert clients._ipfs_is_running() is True


def test_ipfs_is_running_false_when_connection_refused(monkeypatch):
    def _raise(*a, **k):
        raise clients.requests.ConnectionError('refused')

    monkeypatch.setattr(clients.requests, 'post', _raise)
    assert clients._ipfs_is_running() is False


def test_ipfs_is_running_false_when_http_error(monkeypatch):
    monkeypatch.setattr(
        clients.requests, 'post', lambda *a, **k: _FakeResponse(False)
    )
    assert clients._ipfs_is_running() is False


def test_daemon_api_already_up_skips_heal_and_does_not_own(monkeypatch):
    clients._host_daemon_owned = False
    heal_calls = []

    monkeypatch.setattr(clients, '_ipfs_is_running', lambda *a, **k: True)
    monkeypatch.setattr(
        clients, '_heal_stale_repo_lock', lambda: heal_calls.append(True)
    )

    assert clients.ipfs().daemon() is None
    assert heal_calls == []
    assert clients._host_daemon_owned is False


def test_heal_unlinks_stale_lock_when_no_daemon_process(monkeypatch, tmp_path):
    lock_path = tmp_path / 'repo.lock'
    lock_path.write_text('stale')

    monkeypatch.setattr(clients, '_ipfs_is_running', lambda *a, **k: False)
    monkeypatch.setattr(clients, '_repo_lock_path', lambda: str(lock_path))
    monkeypatch.setattr(clients, '_lock_holder_pids', lambda *_: [])
    monkeypatch.setattr(clients, '_ipfs_daemon_pids', lambda: [])
    monkeypatch.setattr(clients.time, 'sleep', lambda *_: None)
    monkeypatch.setattr(
        clients.subprocess,
        'run',
        lambda *a, **k: _FakeCompleted(0),
    )

    clients._heal_stale_repo_lock()
    assert not lock_path.exists()


def test_heal_terminates_lock_holders_then_unlinks(monkeypatch, tmp_path):
    lock_path = tmp_path / 'repo.lock'
    lock_path.write_text('held')
    terminated = []

    monkeypatch.setattr(clients, '_ipfs_is_running', lambda *a, **k: False)
    monkeypatch.setattr(clients, '_repo_lock_path', lambda: str(lock_path))
    monkeypatch.setattr(clients, '_lock_holder_pids', lambda *_: [23385])
    monkeypatch.setattr(clients, '_ipfs_daemon_pids', lambda: [])
    monkeypatch.setattr(
        clients, '_terminate_pids', lambda pids, **k: terminated.extend(pids)
    )
    monkeypatch.setattr(clients.time, 'sleep', lambda *_: None)
    monkeypatch.setattr(
        clients.subprocess,
        'run',
        lambda *a, **k: _FakeCompleted(0),
    )

    # After terminate, no holders remain → unlink proceeds.
    holders = {'first': True}

    def _holders_after_kill(_path=None):
        if holders.pop('first', False):
            return [23385]
        return []

    monkeypatch.setattr(clients, '_lock_holder_pids', _holders_after_kill)

    clients._heal_stale_repo_lock()
    assert terminated == [23385]
    assert not lock_path.exists()


def test_shutdown_owned_daemon_noops_when_not_owned(monkeypatch):
    clients._host_daemon_owned = False
    calls = []

    monkeypatch.setattr(
        clients.subprocess,
        'run',
        lambda *a, **k: calls.append(a) or _FakeCompleted(0),
    )

    clients.shutdown_owned_daemon()
    assert calls == []
    assert clients._host_daemon_owned is False


def test_shutdown_owned_daemon_clears_flag_when_owned(monkeypatch):
    clients._host_daemon_owned = True
    calls = []

    monkeypatch.setattr(
        clients.subprocess,
        'run',
        lambda *a, **k: calls.append(a[0]) or _FakeCompleted(0),
    )
    monkeypatch.setattr(clients, '_wait_for_ipfs_api_down', lambda **k: True)

    clients.shutdown_owned_daemon()
    assert calls == [['ipfs', 'shutdown']]
    assert clients._host_daemon_owned is False
