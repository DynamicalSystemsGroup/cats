"""Optional Syft CLI + docker digest resolve. Fail-open (missing binary → skip)."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

_SYFT_TIMEOUT_S = 120
_DOCKER_TIMEOUT_S = 15
_SHA256_PREFIX = 'sha256:'


def syft_binary(explicit: str | None = None) -> str | None:
    """Return a Syft executable path, or ``None`` when unavailable."""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    return shutil.which('syft')


def run_syft(
    image: str,
    *,
    syft_bin: str | None = None,
    timeout: float = _SYFT_TIMEOUT_S,
) -> tuple[dict[str, Any] | None, float | None]:
    """Catalog ``image`` as Syft JSON.

    Returns ``(document, elapsed_s)``. Missing / failing Syft is skip + log,
    never an exception (fail-open).
    """
    binary = syft_binary(syft_bin)
    if not binary:
        logger.info('syft not on PATH; skipping image catalog for %s', image)
        return None, None
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [binary, image, '-o', 'syft-json'],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.info('syft skip for %s: %s', image, exc)
        return None, None
    elapsed = time.monotonic() - started
    if proc.returncode != 0:
        logger.info(
            'syft exit %s for %s: %s',
            proc.returncode,
            image,
            (proc.stderr or '').strip()[:400],
        )
        return None, elapsed
    try:
        doc = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        logger.info('syft JSON parse failed for %s: %s', image, exc)
        return None, elapsed
    if not isinstance(doc, dict):
        logger.info('syft JSON is not an object for %s', image)
        return None, elapsed
    return doc, elapsed


def docker_image_digest(ref: str, *, timeout: float = _DOCKER_TIMEOUT_S) -> str | None:
    """Resolve ``ref`` to a lowercase hex sha256 via ``docker image inspect``.

    Fail-open: missing docker, missing image, or empty RepoDigests → ``None``.
    """
    raw = (ref or '').strip()
    if not raw:
        return None
    if '@' in raw and _SHA256_PREFIX in raw.split('@', 1)[1]:
        digest = raw.split('@', 1)[1].strip()
        if digest.lower().startswith(_SHA256_PREFIX):
            hex_digest = digest[len(_SHA256_PREFIX) :].strip().lower()
            if len(hex_digest) == 64:
                return hex_digest
    if not shutil.which('docker'):
        logger.info('docker not on PATH; skip digest resolve for %s', raw)
        return None
    try:
        proc = subprocess.run(
            [
                'docker',
                'image',
                'inspect',
                '--format',
                '{{json .RepoDigests}}',
                raw,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.info('docker inspect skip for %s: %s', raw, exc)
        return None
    if proc.returncode != 0:
        logger.info('docker inspect miss for %s', raw)
        return None
    try:
        digests = json.loads(proc.stdout.strip() or '[]')
    except json.JSONDecodeError:
        return None
    if not isinstance(digests, list):
        return None
    for item in digests:
        if not isinstance(item, str) or '@' not in item:
            continue
        digest = item.split('@', 1)[1].strip()
        if digest.lower().startswith(_SHA256_PREFIX):
            hex_digest = digest[len(_SHA256_PREFIX) :].strip().lower()
            if len(hex_digest) == 64:
                return hex_digest
    return None
