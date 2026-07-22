"""Unit tests for AQ-safe Node CLI (start/stop/status/ensure)."""
from pathlib import Path
from types import SimpleNamespace

import pytest

import cats.node as node


NODE_PY = Path(__file__).resolve().parents[1] / 'cats' / 'node.py'


def test_node_py_has_no_ipfs_daemon_or_shutdown_strings():
    """Node CLI source must not start or shut down the host Kubo daemon."""
    text = NODE_PY.read_text(encoding='utf-8')
    assert 'ipfs shutdown' not in text
    assert 'ipfs daemon' not in text


def test_start_asserts_ready_before_run(monkeypatch):
    """start asserts ContentStore readiness before catNode.run."""
    calls = []

    def fake_assert():
        calls.append('assert')

    def fake_run(**kwargs):
        calls.append('run')
        return None

    monkeypatch.setattr(
        node, '_bootstrap_content_store_assert_ready', fake_assert
    )
    monkeypatch.setattr(node, '_free_stale_port', lambda *a, **k: None)
    monkeypatch.setattr(node.catNode, 'run', fake_run)
    monkeypatch.setattr(node.signal, 'signal', lambda *a, **k: None)

    assert node.main(['start']) == 0
    assert calls == ['assert', 'run']


def test_bare_main_defaults_to_start(monkeypatch):
    """Bare `python -m cats.node` with no args defaults to start."""
    calls = []
    monkeypatch.setattr(
        node, '_cmd_start', lambda: calls.append('start') or 0
    )
    assert node.main([]) == 0
    assert calls == ['start']


def test_start_assert_failure_skips_run(monkeypatch):
    """start exits non-zero and skips Flask run when ContentStore is not ready."""
    run_called = []

    def boom():
        raise RuntimeError('kubo down')

    monkeypatch.setattr(node, '_bootstrap_content_store_assert_ready', boom)
    monkeypatch.setattr(
        node.catNode, 'run', lambda **k: run_called.append(True)
    )

    assert node.main(['start']) == 1
    assert run_called == []


def test_stop_uses_port_helper_only(monkeypatch):
    """stop only frees the Flask port; it must not touch host Kubo."""
    stopped = []

    monkeypatch.setattr(
        node,
        '_stop_node_process',
        lambda host, port: stopped.append((host, port)),
    )
    monkeypatch.setattr(node, '_flask_listening', lambda *a, **k: False)

    assert node.main(['stop']) == 0
    assert stopped == [(node.HOST, node.PORT)]


def test_status_exit_codes(monkeypatch):
    """status is 0 only when both Flask and ContentStore are ready."""
    class FakeCS:
        ready = True

        @classmethod
        def is_ready(cls):
            return cls.ready

    monkeypatch.setattr(
        node,
        '_load_bootstrap_content_store_module',
        lambda cats_home: SimpleNamespace(ContentStore=FakeCS),
    )

    monkeypatch.setattr(node, '_flask_listening', lambda *a, **k: True)
    FakeCS.ready = True
    assert node.main(['status']) == 0

    FakeCS.ready = False
    assert node.main(['status']) == 1

    monkeypatch.setattr(node, '_flask_listening', lambda *a, **k: False)
    FakeCS.ready = True
    assert node.main(['status']) == 1


def test_ensure_still_heals_via_bootstrap_ensure(monkeypatch):
    """ensure still mutates via bootstrap ContentStore.ensure (operator path)."""
    calls = []

    monkeypatch.setattr(
        node,
        '_bootstrap_content_store_ensure',
        lambda: calls.append('ensure'),
    )
    assert node.main(['ensure']) == 0
    assert calls == ['ensure']

    def boom():
        raise OSError('missing utils')

    monkeypatch.setattr(node, '_bootstrap_content_store_ensure', boom)
    assert node.main(['ensure']) == 1


def test_assert_ready_raises_when_not_ready(monkeypatch):
    """_bootstrap_content_store_assert_ready raises when is_ready is False."""
    class FakeCS:
        @classmethod
        def is_ready(cls):
            return False

    monkeypatch.setattr(
        node,
        '_load_bootstrap_content_store_module',
        lambda cats_home: SimpleNamespace(ContentStore=FakeCS),
    )
    with pytest.raises(RuntimeError, match='not ready'):
        node._bootstrap_content_store_assert_ready()
