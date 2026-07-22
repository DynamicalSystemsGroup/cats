"""Tests for Order-submitted vs MeshClient bootstrap ContentStore binding."""
import hashlib
import importlib
import importlib.util
import shutil
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cats.executor.structure import InfraStructure
from cats.network import (
    MeshClient,
    _bootstrap_content_store_utils_path,
)
from cats import CATS_HOME

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_CONTENT_STORE_UTILS = (
    REPO_ROOT
    / 'data'
    / 'input'
    / 'structure'
    / 'infrastructure'
    / 'content_store_utils.py'

)


def _write_fake_content_store_utils(path: Path, marker_name: str, *, ready=True):
    """Write a tiny content_store_utils that records ensure / is_ready calls."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        textwrap.dedent(
            f"""\
            class ContentStore:
                ensured = []
                probed = []
                _ready = {ready!r}

                @classmethod
                def ensure(cls, cwd=None):
                    cls.ensured.append({{'cwd': cwd, 'marker': {marker_name!r}}})

                @classmethod
                def is_ready(cls):
                    cls.probed.append({{'marker': {marker_name!r}}})
                    return cls._ready
            """
        ),
        encoding='utf-8',
    )


def _infra_with_structure_home(structure_home: Path, cats_home: Path):
    service = SimpleNamespace(
        INPUT_STRUCTURE_HOME=str(structure_home),
        CATS_HOME=str(cats_home),
        executeCMD=MagicMock(),
    )
    infra = InfraStructure.__new__(InfraStructure)
    infra.service = service
    infra.structure_cid = 'bafy-test'
    infra.INPUT_STRUCTURE_HOME = str(structure_home)
    return infra


def test_bootstrap_path_never_under_input_structure_home():
    """Bootstrap ContentStore utils live under checkout input/, never jobs/."""
    path = _bootstrap_content_store_utils_path(CATS_HOME)
    assert path is not None
    assert 'INPUT_STRUCTURE_HOME' not in path
    # Job-scoped structure homes live under data/jobs — bootstrap must not.
    assert '/jobs/' not in path.replace('\\', '/')
    assert path.endswith(
        'data/input/structure/infrastructure/content_store_utils.py'
    ) or path.endswith(
        'data\\input\\structure\\infrastructure\\content_store_utils.py'
    )


def test_order_loader_path_is_under_input_structure_home(tmp_path):
    """InfraStructure loads ContentStore utils from the Order structure tree."""
    structure_home = tmp_path / 'order_structure'
    utils_path = (
        structure_home
        / 'infrastructure'
        / 'content_store_utils.py'

    )
    _write_fake_content_store_utils(utils_path, 'order-submitted')
    infra = _infra_with_structure_home(structure_home, tmp_path / 'cats_home')
    mod = infra._load_content_store_module()
    assert hasattr(mod, 'ContentStore')
    # Module was loaded from Order tree (fake has marker via ensure).
    mod.ContentStore.ensure(cwd='x')
    assert mod.ContentStore.ensured[-1]['marker'] == 'order-submitted'


def test_repo_content_store_utils_required_public_api():
    """Repo content_store_utils exposes ContentStore ensure/is_ready and CLI."""
    spec = importlib.util.spec_from_file_location(
        'content_store_utils_api_check', REPO_CONTENT_STORE_UTILS
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert hasattr(module, 'ContentStore')
    assert callable(module.ContentStore.ensure)
    assert callable(module.ContentStore.is_ready)
    assert callable(module._ipfs_api_id_url)
    assert callable(module._main)
    assert module._main(['status']) in (0, 1)


def test_content_store_utils_sha256_matches_when_order_tree_copied_from_repo(
    tmp_path,
):
    """Demo invariant: Order tree copied from repo checkout has no republish lag."""
    src = REPO_CONTENT_STORE_UTILS
    assert src.is_file()
    order_utils = (
        tmp_path
        / 'structure'
        / 'infrastructure'
        / 'content_store_utils.py'

    )
    order_utils.parent.mkdir(parents=True)
    shutil.copy2(src, order_utils)

    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    assert _sha(src) == _sha(order_utils)


def test_infrastructure_content_store_ensure_loads_order_tree(tmp_path):
    """À la carte API still loads Order-submitted utils (not used by apply)."""
    structure_home = tmp_path / 'order_structure'
    utils_path = (
        structure_home
        / 'infrastructure'
        / 'content_store_utils.py'

    )
    _write_fake_content_store_utils(utils_path, 'order-submitted')

    infra = _infra_with_structure_home(structure_home, tmp_path / 'cats_home')
    infra.content_store_ensure(cwd=infra.service.CATS_HOME)

    mod = importlib.import_module('infrastructure_content_store_utils_order')
    assert mod.ContentStore.ensured == [
        {'cwd': infra.service.CATS_HOME, 'marker': 'order-submitted'}
    ]


def test_content_store_assert_passes_when_ready(tmp_path):
    """content_store_assert succeeds when Order-tree ContentStore reports ready."""
    structure_home = tmp_path / 'order_structure'
    utils_path = (
        structure_home
        / 'infrastructure'
        / 'content_store_utils.py'

    )
    _write_fake_content_store_utils(utils_path, 'order-submitted', ready=True)
    infra = _infra_with_structure_home(structure_home, tmp_path / 'cats_home')
    infra.content_store_assert()


def test_content_store_assert_raises_when_not_ready(tmp_path):
    """content_store_assert raises when Order-tree ContentStore is not ready."""
    structure_home = tmp_path / 'order_structure'
    utils_path = (
        structure_home
        / 'infrastructure'
        / 'content_store_utils.py'

    )
    _write_fake_content_store_utils(utils_path, 'order-submitted', ready=False)
    infra = _infra_with_structure_home(structure_home, tmp_path / 'cats_home')
    with pytest.raises(RuntimeError, match='ContentStore not ready'):
        infra.content_store_assert()


def test_apply_does_not_call_content_store_ensure(tmp_path, monkeypatch):
    """apply asserts readiness only; it must not call content_store_ensure."""
    structure_home = tmp_path / 'order_structure'
    utils_path = (
        structure_home
        / 'infrastructure'
        / 'content_store_utils.py'

    )
    _write_fake_content_store_utils(utils_path, 'order-submitted', ready=True)
    infra = _infra_with_structure_home(structure_home, tmp_path / 'cats_home')

    ensure_calls = []
    monkeypatch.setattr(
        infra,
        'content_store_ensure',
        lambda *a, **k: ensure_calls.append((a, k)),
    )
    monkeypatch.setattr(
        'cats.executor.structure.configure_terraform_data_dir',
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        'cats.executor.structure.ensure_integration_cache_env',
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        'cats.executor.structure.cleanup_stale_docker_compose_ipfs_transport_state',
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        'cats.executor.structure.terraform_bin',
        lambda *_a, **_k: 'terraform',
    )

    plant_utils = SimpleNamespace(
        cleanup_stale_plant_state=lambda *_a, **_k: None,
    )
    plant = SimpleNamespace(_load_plant_utils=lambda: plant_utils)
    monkeypatch.setattr(infra, 'compose', lambda: plant)

    obj_mod = SimpleNamespace(
        cleanup_stale_obj_store_state=lambda *_a, **_k: None,
    )
    monkeypatch.setattr(infra, '_load_obj_store_module', lambda: obj_mod)

    content_assert_calls = []
    transport_assert_calls = []
    ensure_peered_calls = []

    monkeypatch.setattr(
        infra,
        'content_store_assert',
        lambda: content_assert_calls.append('assert'),
    )
    monkeypatch.setattr(
        infra,
        'transport_assert',
        lambda: transport_assert_calls.append('assert'),
    )
    monkeypatch.setattr(
        infra,
        'transport_context',
        lambda: SimpleNamespace(
            ensure_peered=lambda: ensure_peered_calls.append('peer'),
            assert_ready=lambda: None,
        ),
    )

    infra.apply()

    assert ensure_calls == []
    assert content_assert_calls == ['assert']
    assert transport_assert_calls == ['assert']
    assert ensure_peered_calls == []
    infra.service.executeCMD.assert_called()


def test_meshclient_init_does_not_call_bootstrap_ensure(tmp_path, monkeypatch):
    """MeshClient construction does not probe or ensure ContentStore."""
    calls = []

    def _spy(self):
        calls.append('ensure')
        self._bootstrap_content_store_ensured = True

    monkeypatch.setattr(MeshClient, 'ensure_bootstrap_content_store', _spy)
    client = MeshClient(ipfsClient=MagicMock(), CATS_HOME=str(tmp_path))
    assert calls == []
    assert client._bootstrap_content_store_ensured is False


def test_meshclient_ciddir_triggers_bootstrap_readiness_once(tmp_path, monkeypatch):
    """cidDir triggers bootstrap readiness checks (soft probe path)."""
    calls = []

    def _spy(self):
        calls.append('ready_check')
        self._bootstrap_content_store_ensured = True

    monkeypatch.setattr(MeshClient, 'ensure_bootstrap_content_store', _spy)

    fake_ipfs = MagicMock()
    fake_ipfs.add.return_value = {'Hash': 'bafyFake', 'Name': 'payload'}
    client = MeshClient(ipfsClient=fake_ipfs, CATS_HOME=str(tmp_path))
    assert calls == []

    payload = tmp_path / 'payload'
    payload.mkdir()
    (payload / 'f.txt').write_text('x', encoding='utf-8')

    assert client.cidDir(str(payload)) == 'bafyFake'
    assert calls == ['ready_check']

    client.cidDir(str(payload))
    assert calls == ['ready_check', 'ready_check']


def test_meshclient_bootstrap_probes_is_ready_not_ensure(tmp_path):
    """Bootstrap path probes is_ready and never calls ContentStore.ensure."""
    cats_home = tmp_path / 'cats_home'
    utils_path = (
        cats_home
        / 'data'
        / 'input'
        / 'structure'
        / 'infrastructure'
        / 'content_store_utils.py'

    )
    _write_fake_content_store_utils(utils_path, 'bootstrap', ready=True)

    client = MeshClient(ipfsClient=MagicMock(), CATS_HOME=str(cats_home))
    assert client._bootstrap_content_store_ensured is False

    client.ensure_bootstrap_content_store()
    mod = importlib.import_module('infrastructure_content_store_utils_bootstrap')
    assert mod.ContentStore.ensured == []
    assert mod.ContentStore.probed == [{'marker': 'bootstrap'}]
    assert client._bootstrap_content_store_ensured is True

    client.ensure_bootstrap_content_store()
    assert mod.ContentStore.probed == [{'marker': 'bootstrap'}]
    assert mod.ContentStore.ensured == []


def test_meshclient_bootstrap_skips_when_utils_missing(tmp_path):
    """Missing bootstrap utils soft-skips and marks bootstrap as checked."""
    cats_home = tmp_path / 'empty_home'
    cats_home.mkdir()
    client = MeshClient(ipfsClient=MagicMock(), CATS_HOME=str(cats_home))
    client.ensure_bootstrap_content_store()
    assert client._bootstrap_content_store_ensured is True
