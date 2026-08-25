"""Unit tests for InfraStructure directory-model transport_utils / TransportContext."""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

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


class _FakeTransport:
    def migrate(self, input_dir_id):
        return (f'cid-for-{input_dir_id}', 'data_1')

    def stage_for_plant(self, input_dir_id, *, cwd, data_cache=None):
        return f'{cwd}/staged/{input_dir_id}'


def test_migrate_legacy_cid_fail_closed(tmp_path):
    """Legacy CID migrate fails closed (§6s); no remint path."""
    ctx = tu.TransportContext.default(structure_home=str(tmp_path))
    with pytest.raises(RuntimeError, match='unsupported|§6s'):
        ctx.migrate('QmInputLegacy')


def test_stage_for_plant_legacy_cid_fail_closed(tmp_path):
    """Legacy CID stage_for_plant fails closed (§6s)."""
    data_cache = tmp_path / 'outputs'
    data_cache.mkdir()
    ctx = tu.TransportContext.default(structure_home=str(tmp_path))
    with pytest.raises(RuntimeError, match='unsupported|§6s'):
        ctx.stage_for_plant(
            'QmIn', cwd=str(tmp_path), data_cache=str(data_cache)
        )


def test_migrate_cas_skips_docker(monkeypatch, tmp_path):
    """migrate on ni: materializes via CAS without Docker peers."""
    cats_home = tmp_path / 'cats_home'
    cats_home.mkdir()
    monkeypatch.setenv('CATS_HOME', str(cats_home))
    monkeypatch.setattr(tu.time, 'time', lambda: 99)

    from cats.network.cas import CasHttpStore, put_tree

    src = tmp_path / 'src'
    src.mkdir()
    (src / 'f.csv').write_text('a\n', encoding='utf-8')
    store = CasHttpStore(str(cats_home))
    content_id = put_tree(store, str(src))

    ctx = tu.TransportContext.default(structure_home=str(tmp_path / 'structure'))
    (tmp_path / 'structure').mkdir()
    out_id, name = ctx.migrate(content_id)
    assert out_id.startswith('ni:///sha-256;')
    assert name == 'data_99'


def test_stage_for_plant_cas_materializes_host(monkeypatch, tmp_path):
    """stage_for_plant on ni: writes the tree under data_cache."""
    cats_home = tmp_path / 'cats_home'
    cats_home.mkdir()
    monkeypatch.setenv('CATS_HOME', str(cats_home))
    monkeypatch.setattr(tu.time, 'time', lambda: 7)

    from cats.network.cas import CasHttpStore, put_tree

    src = tmp_path / 'src'
    src.mkdir()
    (src / 'x.csv').write_text('b\n', encoding='utf-8')
    content_id = put_tree(CasHttpStore(str(cats_home)), str(src))

    data_cache = tmp_path / 'outputs'
    data_cache.mkdir()

    ctx = tu.TransportContext.default(structure_home=str(tmp_path / 'structure'))
    (tmp_path / 'structure').mkdir()
    path = ctx.stage_for_plant(
        content_id, cwd=str(tmp_path), data_cache=str(data_cache)
    )
    assert path.endswith('staged_7')
    assert (Path(path) / 'x.csv').read_text(encoding='utf-8') == 'b\n'


def test_cli_status_ready():
    """CLI status exits 0 (CAS transport needs no peer containers)."""
    assert tu._main(['status']) == 0


def test_cli_ensure_peered_removed():
    """CLI ensure-peered is retired with Docker peers (§6s)."""
    with pytest.raises(SystemExit):
        tu._main(['ensure-peered'])


def test_no_cats_network_peering_module():
    """Legacy cats.network docker peering helper module must stay removed."""
    peering = (
        REPO_ROOT / 'cats' / 'network' / 'docker_ipfs_transport_peering.py'
    )
    assert not peering.exists()


def test_process_port_uses_fake_transport():
    """Process ingress/egress/integration_cache accept a TransportPort duck type."""
    from data.input.function import process as proc

    fake = _FakeTransport()
    assert proc.ingress('QmA', fake) == ('cid-for-QmA', 'data_1')
    assert proc.egress('QmB', fake) == 'cid-for-QmB'
    assert proc.integration_cache('QmC', '/cache', fake) == '/cache/staged/QmC'


def test_grep_guard_no_ensure_docker_ipfs_peers_in_process():
    """Process sources must not import or call transport peering internals."""
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
    """Shell peer script must stay gone."""
    orphan = (
        REPO_ROOT
        / 'data'
        / 'input'
        / 'structure'
        / 'infrastructure'
        / 'ipfs_connect_peers.sh'
    )
    assert not orphan.exists()


def test_tf_no_ipfs_peer_or_host_daemon_resources():
    """§6s: infrastructure TF has no Docker Kubo peers or host_ipfs_daemon."""
    main_tf = (
        REPO_ROOT
        / 'data'
        / 'input'
        / 'structure'
        / 'infrastructure'
        / 'main.tf'
    )
    text = main_tf.read_text(encoding='utf-8')
    assert 'docker_compose_ipfs_transport' not in text
    assert 'ipfs_transport_peering' not in text
    assert 'resource "shell_script" "host_ipfs_daemon"' not in text
    assert 'resource "shell_script" "docker_compose_minio_scratch"' in text


def test_ipfs_transport_compose_deleted():
    """Docker Kubo peer compose file is removed (§6s)."""
    compose = (
        REPO_ROOT
        / 'data'
        / 'input'
        / 'structure'
        / 'infrastructure'
        / 'ipfs_transport_compose.yaml'
    )
    assert not compose.exists()
