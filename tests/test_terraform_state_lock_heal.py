"""Stale Terraform state-lock heal (Ctrl-C during apply/destroy)."""
from pathlib import Path

from cats.executor.structure._tf import (
    TF_STATE_LOCK_INFO,
    heal_stale_terraform_state_lock,
)


def test_heal_removes_stale_lock_when_no_holders(tmp_path, monkeypatch):
    lock = tmp_path / TF_STATE_LOCK_INFO
    lock.write_text('{"ID":"fake"}', encoding='utf-8')
    (tmp_path / 'terraform.tfstate').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(
        'cats.executor.structure._tf._path_has_open_holders',
        lambda _path: False,
    )

    heal_stale_terraform_state_lock(str(tmp_path))

    assert not lock.exists()


def test_heal_keeps_lock_when_holder_alive(tmp_path, monkeypatch):
    lock = tmp_path / TF_STATE_LOCK_INFO
    lock.write_text('{"ID":"fake"}', encoding='utf-8')
    monkeypatch.setattr(
        'cats.executor.structure._tf._path_has_open_holders',
        lambda _path: True,
    )

    heal_stale_terraform_state_lock(str(tmp_path))

    assert lock.exists()


def test_heal_noop_when_no_lock(tmp_path):
    heal_stale_terraform_state_lock(str(tmp_path))
    assert not (tmp_path / TF_STATE_LOCK_INFO).exists()
