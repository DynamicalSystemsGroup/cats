"""IoPort callables branching, partition layout naming, RayComputePort parts."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from data.input.function.process.callables import egress, ingress
from data.input.structure.plant.partition_layout import (
    list_part_cars,
    part_car_name,
    round_robin_paths,
    split_file_bytes,
)
from data.input.structure.plant.ray_compute_utils import _part_inputs


def test_part_car_name_stable():
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


def test_part_inputs_detects_cars(tmp_path):
    for i in range(3):
        (tmp_path / part_car_name(i)).write_bytes(b'car')
    paths = _part_inputs(str(tmp_path), 3)
    assert paths is not None
    assert len(paths) == 3


def test_part_inputs_wrong_count(tmp_path):
    (tmp_path / part_car_name(0)).write_bytes(b'car')
    assert _part_inputs(str(tmp_path), 3) is None


def test_list_part_cars_sorted(tmp_path):
    (tmp_path / 'part-00001.car').write_bytes(b'b')
    (tmp_path / 'part-00000.car').write_bytes(b'a')
    names = [p.name for p in list_part_cars(tmp_path)]
    assert names == ['part-00000.car', 'part-00001.car']


def test_processor_io_partitions_env(monkeypatch):
    monkeypatch.setenv('CATS_IO_PARTITIONS', '4')
    from cats.executor.function.processor import _io_partitions

    assert _io_partitions() == 4


def test_processor_io_partitions_default(monkeypatch):
    monkeypatch.delenv('CATS_IO_PARTITIONS', raising=False)
    from cats.executor.function.processor import _io_partitions

    assert _io_partitions() == 1
