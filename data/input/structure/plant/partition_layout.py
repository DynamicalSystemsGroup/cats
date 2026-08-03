"""Stable CAR-per-partition layout helpers (Plant I/O; no Ray import).

Layout: a directory of ``part-00000.car`` … ``part-{n-1:05d}.car`` files
(each file body is CARv1 bytes). Used by RayIoPort / ray_io_entrypoint and
RayComputePort alignment.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def part_car_name(index: int) -> str:
    """Stable partition CAR filename (shuffle key)."""
    if index < 0:
        raise ValueError(f'partition index must be >= 0, got {index}')
    return f'part-{index:05d}.car'


def part_shard_name(index: int) -> str:
    """Stable partition shard stem / directory name (pre-CAR)."""
    if index < 0:
        raise ValueError(f'partition index must be >= 0, got {index}')
    return f'part-{index:05d}'


def list_part_cars(directory: str | Path) -> list[Path]:
    """Sorted ``part-*.car`` paths under ``directory``."""
    root = Path(directory)
    parts = sorted(root.glob('part-*.car'))
    return parts


def list_part_shards(directory: str | Path) -> list[Path]:
    """Sorted non-CAR ``part-*`` files/dirs (hotF CSV outputs)."""
    root = Path(directory)
    return sorted(
        p for p in root.glob('part-*')
        if not p.name.endswith('.car')
    )


def split_file_bytes(data: bytes, num_partitions: int) -> list[bytes]:
    """Split a single file into ``num_partitions`` nearly equal byte shards."""
    if num_partitions < 1:
        raise ValueError(f'num_partitions must be >= 1, got {num_partitions}')
    if num_partitions == 1:
        return [data]
    n = len(data)
    if n == 0:
        return [b''] * num_partitions
    base, rem = divmod(n, num_partitions)
    shards: list[bytes] = []
    offset = 0
    for i in range(num_partitions):
        size = base + (1 if i < rem else 0)
        shards.append(data[offset : offset + size])
        offset += size
    return shards


def round_robin_paths(paths: list[Path], num_partitions: int) -> list[list[Path]]:
    """Distribute file paths into ``num_partitions`` bags (round-robin)."""
    if num_partitions < 1:
        raise ValueError(f'num_partitions must be >= 1, got {num_partitions}')
    bags: list[list[Path]] = [[] for _ in range(num_partitions)]
    for i, path in enumerate(sorted(paths)):
        bags[i % num_partitions].append(path)
    return bags


def collect_input_files(root: Path) -> list[Path]:
    """Files under ``root`` (recursive), excluding hidden/.git noise."""
    if root.is_file():
        return [root]
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for name in filenames:
            if name.startswith('.'):
                continue
            files.append(Path(dirpath) / name)
    return sorted(files)


def write_shard_tree(bag: list[Path], dest_dir: Path, *, source_root: Path) -> None:
    """Copy bag files into ``dest_dir``, preserving relative paths when possible."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not bag:
        (dest_dir / '.empty').write_text('', encoding='utf-8')
        return
    for src in bag:
        if source_root.is_file():
            rel = src.name
        else:
            try:
                rel = str(src.relative_to(source_root))
            except ValueError:
                rel = src.name
        out = dest_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
