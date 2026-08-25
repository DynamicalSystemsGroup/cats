"""Unit tests for AQ-safe Node CLI (start/stop/status/ensure)."""
from pathlib import Path
from types import SimpleNamespace

import pytest

import cats.node as node
from cats.node import app, cli


NODE_PKG = Path(__file__).resolve().parents[1] / 'cats' / 'node'


def test_node_pkg_has_no_ipfs_daemon_or_shutdown_strings():
    """Node CLI/edge source must not start or shut down the host Kubo daemon."""
    text = '\n'.join(
        path.read_text(encoding='utf-8') for path in NODE_PKG.rglob('*.py')
    )
    assert 'ipfs shutdown' not in text
    assert 'ipfs daemon' not in text


def test_start_soft_probes_before_run(monkeypatch):
    """start soft-probes ContentStore then binds Flask (§6r)."""
    calls = []

    def fake_soft():
        calls.append('soft')

    def fake_run(**kwargs):
        calls.append('run')
        return None

    monkeypatch.setattr(
        cli, '_bootstrap_content_store_soft_ready', fake_soft
    )
    monkeypatch.setattr(cli, '_free_stale_port', lambda *a, **k: None)
    monkeypatch.setattr(cli, '_flask_listening', lambda *a, **k: False)
    monkeypatch.setattr(app.catNode, 'run', fake_run)
    monkeypatch.setattr(cli.signal, 'signal', lambda *a, **k: None)

    assert node.main(['start']) == 0
    assert calls == ['soft', 'run']


def test_start_rejects_foreign_port_holder(monkeypatch):
    """start exits when the Node port is held by a non-cats.node process."""
    monkeypatch.setattr(
        cli, '_bootstrap_content_store_soft_ready', lambda: None
    )
    monkeypatch.setattr(cli, '_free_stale_port', lambda *a, **k: None)
    monkeypatch.setattr(cli, '_flask_listening', lambda *a, **k: True)
    monkeypatch.setattr(cli, '_cats_node_on_port', lambda *a, **k: False)
    run_called = []
    monkeypatch.setattr(
        app.catNode, 'run', lambda **k: run_called.append(True)
    )

    assert node.main(['start']) == 1
    assert run_called == []


def test_bare_main_defaults_to_start(monkeypatch):
    """Bare `python -m cats.node` with no args defaults to start."""
    calls = []
    monkeypatch.setattr(
        cli, '_cmd_start', lambda: calls.append('start') or 0
    )
    assert node.main([]) == 0
    assert calls == ['start']


def test_start_continues_when_content_store_not_ready(monkeypatch):
    """start still runs Flask when soft probe finds Kubo down (§6r)."""
    run_called = []

    def soft_warn():
        # Soft probe may warn; must not raise / abort start.
        return None

    monkeypatch.setattr(cli, '_bootstrap_content_store_soft_ready', soft_warn)
    monkeypatch.setattr(cli, '_free_stale_port', lambda *a, **k: None)
    monkeypatch.setattr(cli, '_flask_listening', lambda *a, **k: False)
    monkeypatch.setattr(cli.signal, 'signal', lambda *a, **k: None)
    monkeypatch.setattr(
        app.catNode, 'run', lambda **k: run_called.append(True)
    )

    assert node.main(['start']) == 0
    assert run_called == [True]

def test_stop_uses_port_helper_only(monkeypatch):
    """stop only frees the Flask port; it must not touch host Kubo."""
    stopped = []

    monkeypatch.setattr(
        cli,
        '_stop_node_process',
        lambda host, port: stopped.append((host, port)),
    )
    monkeypatch.setattr(cli, '_flask_listening', lambda *a, **k: False)

    assert node.main(['stop']) == 0
    assert stopped == [(app.HOST, app.PORT)]


def test_status_exit_codes(monkeypatch):
    """status is 0 only when both cats.node Flask and ContentStore are ready."""
    class FakeCS:
        ready = True

        @classmethod
        def is_ready(cls):
            return cls.ready

    monkeypatch.setattr(
        cli,
        '_load_bootstrap_content_store_module',
        lambda cats_home: SimpleNamespace(ContentStore=FakeCS),
    )

    # TCP-only listeners (e.g. AirPlay) must not count as flask=up.
    monkeypatch.setattr(cli, '_cats_node_on_port', lambda *a, **k: True)
    monkeypatch.setattr(cli, '_flask_listening', lambda *a, **k: True)
    FakeCS.ready = True
    assert node.main(['status']) == 0

    FakeCS.ready = False
    assert node.main(['status']) == 1

    monkeypatch.setattr(cli, '_cats_node_on_port', lambda *a, **k: False)
    FakeCS.ready = True
    assert node.main(['status']) == 1


def test_ensure_still_heals_via_bootstrap_ensure(monkeypatch):
    """ensure still mutates via bootstrap ContentStore.ensure (operator path)."""
    calls = []

    monkeypatch.setattr(
        cli,
        '_bootstrap_content_store_ensure',
        lambda: calls.append('ensure'),
    )
    assert node.main(['ensure']) == 0
    assert calls == ['ensure']

    def boom():
        raise OSError('missing utils')

    monkeypatch.setattr(cli, '_bootstrap_content_store_ensure', boom)
    assert node.main(['ensure']) == 1


def test_assert_ready_raises_when_not_ready(monkeypatch):
    """_bootstrap_content_store_assert_ready raises when is_ready is False."""
    class FakeCS:
        @classmethod
        def is_ready(cls):
            return False

    monkeypatch.setattr(
        cli,
        '_load_bootstrap_content_store_module',
        lambda cats_home: SimpleNamespace(ContentStore=FakeCS),
    )
    with pytest.raises(RuntimeError, match='not ready'):
        cli._bootstrap_content_store_assert_ready()
