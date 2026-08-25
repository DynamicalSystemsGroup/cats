"""IoPort callables branching, opaque partition layout (§6p), RayComputePort parts."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from data.input.function.process.callables import egress, ingress
from data.input.structure.plant.partition_layout import (
    list_part_cars,
    list_part_layout,
    part_car_name,
    part_name,
    round_robin_paths,
    split_file_bytes,
)
from data.input.structure.plant.ray_compute_utils import _part_inputs
from data.input.structure.plant.ray_io_utils import run_partition_ingress


def test_part_name_stable():
    assert part_name(0) == 'part-00000'
    assert part_name(12) == 'part-00012'


def test_part_car_name_stable_legacy():
    assert part_car_name(0) == 'part-00000.car'
    assert part_car_name(12) == 'part-00012.car'


def test_split_file_bytes_equalish():
    data = b'abcdefghij'  # 10 bytes
    shards = split_file_bytes(data, 3)
    assert len(shards) == 3
    assert b''.join(shards) == data
    assert abs(len(shards[0]) - len(shards[1])) <= 1


def test_round_robin_paths(tmp_path):
    files = []
    for name in ('a', 'b', 'c', 'd', 'e'):
        p = tmp_path / f'{name}.csv'
        p.write_text('x', encoding='utf-8')
        files.append(p)
    bags = round_robin_paths(files, 2)
    assert len(bags) == 2
    assert len(bags[0]) + len(bags[1]) == 5


def test_ingress_n1_uses_transport():
    transport = MagicMock()
    transport.migrate.return_value = ('QmIn', 'data')
    io = MagicMock()
    assert ingress('QmX', transport, io=io, num_partitions=1) == ('QmIn', 'data')
    transport.migrate.assert_called_once_with('QmX')
    io.partition_ingress.assert_not_called()


def test_ingress_n_gt1_uses_io():
    transport = MagicMock()
    io = MagicMock()
    io.partition_ingress.return_value = ('QmLayout', 'layout')
    assert ingress('QmX', transport, io=io, num_partitions=4) == (
        'QmLayout',
        'layout',
    )
    io.partition_ingress.assert_called_once_with('QmX', num_partitions=4)
    transport.migrate.assert_not_called()


def test_egress_n1_uses_transport():
    transport = MagicMock()
    transport.migrate.return_value = ('QmOut', 'data')
    assert egress('QmY', transport, num_partitions=1) == 'QmOut'
    transport.migrate.assert_called_once()


def test_egress_n_gt1_uses_io():
    transport = MagicMock()
    io = MagicMock()
    io.partition_egress.return_value = 'QmParts'
    assert egress('QmY', transport, io=io, num_partitions=2) == 'QmParts'
    io.partition_egress.assert_called_once_with('QmY', num_partitions=2)


def test_part_inputs_prefers_opaque(tmp_path):
    for i in range(3):
        (tmp_path / part_name(i)).write_bytes(b'shard')
        (tmp_path / part_car_name(i)).write_bytes(b'car')
    paths = _part_inputs(str(tmp_path), 3)
    assert paths is not None
    assert len(paths) == 3
    assert all(not p.endswith('.car') for p in paths)


def test_part_inputs_detects_legacy_cars(tmp_path):
    for i in range(3):
        (tmp_path / part_car_name(i)).write_bytes(b'car')
    paths = _part_inputs(str(tmp_path), 3)
    assert paths is not None
    assert len(paths) == 3


def test_part_inputs_wrong_count(tmp_path):
    (tmp_path / part_name(0)).write_bytes(b'x')
    assert _part_inputs(str(tmp_path), 3) is None


def test_list_part_cars_sorted(tmp_path):
    (tmp_path / 'part-00001.car').write_bytes(b'b')
    (tmp_path / 'part-00000.car').write_bytes(b'a')
    names = [p.name for p in list_part_cars(tmp_path)]
    assert names == ['part-00000.car', 'part-00001.car']


def test_list_part_layout_opaque(tmp_path):
    (tmp_path / 'part-00001').write_bytes(b'b')
    (tmp_path / 'part-00000').mkdir()
    (tmp_path / 'part-00000' / 'a.csv').write_text('x', encoding='utf-8')
    (tmp_path / 'part-00002.car').write_bytes(b'legacy')
    names = [p.name for p in list_part_layout(tmp_path)]
    assert names == ['part-00000', 'part-00001']


def test_run_partition_ingress_opaque_no_ipfs(tmp_path):
    """Ingress writes opaque part-* and put_dir; never touches ipfsClient."""
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'data.bin').write_bytes(b'0123456789')

    mesh = MagicMock()
    mesh.CATS_HOME = str(tmp_path / 'cats_home')
    mesh.ipfsClient = MagicMock()

    def _get(*, content_id, filepath, output):
        out = Path(output) / filepath
        if out.exists() and out.is_dir():
            # mesh.get writes into output/filepath
            for child in src.iterdir():
                dest = out / child.name
                if child.is_file():
                    dest.write_bytes(child.read_bytes())
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists() and out.is_dir():
                pass
            # replicate AddressStore get: materialize under output/filepath
            target = Path(output) / filepath
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
            for child in src.iterdir():
                dest = target / child.name
                dest.write_bytes(child.read_bytes())

    mesh.get.side_effect = _get
    captured = {}

    def _put_dir(path):
        layout = Path(path)
        captured['parts'] = sorted(p.name for p in layout.iterdir())
        captured['has_car'] = any(p.name.endswith('.car') for p in layout.iterdir())
        return ('ni:///sha-256;deadbeef', layout.name)

    mesh.put_dir.side_effect = _put_dir

    layout_id, layout_name = run_partition_ingress(
        mesh, 'ni:///sha-256;input', num_partitions=2
    )
    assert layout_id == 'ni:///sha-256;deadbeef'
    assert layout_name == 'layout'
    mesh.put_dir.assert_called_once()
    mesh.ipfsClient.add.assert_not_called()
    mesh.ipfsClient.add_bytes.assert_not_called()
    mesh.getCar.assert_not_called()
    assert captured['parts'] == ['part-00000', 'part-00001']
    assert captured['has_car'] is False


def test_run_partition_ingress_requires_cats_home(tmp_path):
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'data.bin').write_bytes(b'abcd')

    mesh = MagicMock()
    mesh.CATS_HOME = None

    def _get(*, content_id, filepath, output):
        target = Path(output) / filepath
        target.mkdir(parents=True, exist_ok=True)
        (target / 'data.bin').write_bytes(b'abcd')

    mesh.get.side_effect = _get

    with pytest.raises(RuntimeError, match='CATS_HOME'):
        run_partition_ingress(mesh, 'ni:///sha-256;input', num_partitions=2)
    mesh.put_dir.assert_not_called()


def test_processor_io_partitions_env(monkeypatch):
    monkeypatch.setenv('CATS_IO_PARTITIONS', '4')
    from cats.executor.function.processor import _io_partitions

    assert _io_partitions() == 4


def test_processor_io_partitions_default(monkeypatch):
    monkeypatch.delenv('CATS_IO_PARTITIONS', raising=False)
    from cats.executor.function.processor import _io_partitions

    assert _io_partitions() == 1
