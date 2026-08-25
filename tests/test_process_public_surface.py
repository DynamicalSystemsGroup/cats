"""Process / InfraFunction public-surface discipline (soft leak 2d)."""
from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESS_PY = (
    REPO_ROOT / 'data' / 'input' / 'function' / 'process' / 'callables.py'
)
INFRAFUNCTION_PY = (
    REPO_ROOT / 'data' / 'input' / 'function' / 'infrafunction' / 'actuator.py'
)

PROCESS_PUBLIC_SURFACE = (
    'ingress',
    'egress',
    'integration_cache',
    'function_0',
    'function_1',
    'process_0',
    'process_1',
)

# Demo, tests, and cats package — places that compose or exercise Function CIDs.
_SCAN_GLOBS = (
    'notebooks/cats_demo.py',
    'notebooks/new_cats_demo.py',
    'tests/**/*.py',
    'cats/**/*.py',
)


def _iter_scanned_files():
    for pattern in _SCAN_GLOBS:
        yield from REPO_ROOT.glob(pattern)


def test_no_star_import_from_process_or_infrafunction():
    """Repo sources must not star-import Process or InfraFunction packages."""
    banned = (
        re.compile(
            r'from\s+data\.input\.function\.process\s+import\s+\*'
        ),
        re.compile(
            r'from\s+data\.input\.function\.infrafunction\s+import\s+\*'
        ),
        re.compile(
            r'from\s+data\.input\.function\s+import\s+\*'
        ),
    )
    offenders = []
    for path in _iter_scanned_files():
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        for pattern in banned:
            if pattern.search(text):
                offenders.append(f'{path.relative_to(REPO_ROOT)}: {pattern.pattern}')
    assert not offenders, 'star-imports forbidden:\n' + '\n'.join(offenders)


def test_process_all_matches_public_surface():
    """process.__all__ matches the locked public surface allowlist."""
    from data.input.function import process as proc

    assert tuple(proc.__all__) == PROCESS_PUBLIC_SURFACE
    for name in PROCESS_PUBLIC_SURFACE:
        assert hasattr(proc, name), name


def test_process_no_runtime_data_package_imports():
    """Ray workers unpickle process by value without repo ``data`` on sys.path."""
    text = PROCESS_PY.read_text(encoding='utf-8')
    # Strip TYPE_CHECKING blocks before scanning runtime imports.
    stripped = re.sub(
        r'if TYPE_CHECKING:.*?(?=\n\S|\n__all__|\ndef |\Z)',
        '',
        text,
        flags=re.DOTALL,
    )
    assert 'from data.' not in stripped
    assert 'import data' not in stripped
    assert 'import ray' not in text
    assert 'JobSubmissionClient' not in text
    assert 'ray.data' not in text


def test_infrafunction_no_ray_job_submission_imports():
    """InfraFunction sources must not import Ray Job Submission / ray.data."""
    text = INFRAFUNCTION_PY.read_text(encoding='utf-8')
    for banned in ('JobSubmissionClient', 'ray.data', 'import ray', 'from ray'):
        assert banned not in text, banned
