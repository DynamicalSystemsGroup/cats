import importlib.util
import json
import os
import re
import stat
import sys

from cats.utils import subproc_run

APPLIED_STRUCTURE_MARKER = '.applied-structure.id'
LEGACY_APPLIED_STRUCTURE_MARKER = '.applied-structure.cid'
TF_STATE_LOCK_INFO = '.terraform.tfstate.lock.info'


def _load_transport_utils_module(structure_home):
    """Load Order-submitted infrastructure/transport_utils.py."""
    path = os.path.join(
        structure_home, 'infrastructure', 'transport_utils.py'
    )
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(
        'infrastructure_transport_utils', path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _applied_structure_marker_path(structure_home):
    return os.path.join(structure_home, APPLIED_STRUCTURE_MARKER)


def _legacy_applied_structure_marker_path(structure_home):
    return os.path.join(structure_home, LEGACY_APPLIED_STRUCTURE_MARKER)


def _read_marker_file(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as marker_file:
        return marker_file.read().strip() or None


def read_applied_structure_id(structure_home):
    """Return the structure id this Structure's Terraform state currently
    reflects, or None if nothing has been successfully applied yet.

    Prefers ``.applied-structure.id``; falls back to legacy
    ``.applied-structure.cid`` for one migration cycle.
    """
    value = _read_marker_file(_applied_structure_marker_path(structure_home))
    if value is not None:
        return value
    return _read_marker_file(_legacy_applied_structure_marker_path(structure_home))


def write_applied_structure_id(structure_home, structure_id):
    """Record the structure id Terraform state now reflects, so a later
    CAT execution with an unchanged (content-addressed) Structure can
    reconcile in place instead of destroying and rebuilding the Plant.

    Writes only ``.applied-structure.id``; removes legacy
    ``.applied-structure.cid`` when present.
    """
    with open(
        _applied_structure_marker_path(structure_home), 'w', encoding='utf-8'
    ) as marker_file:
        marker_file.write(structure_id or '')
    legacy = _legacy_applied_structure_marker_path(structure_home)
    try:
        os.remove(legacy)
    except FileNotFoundError:
        pass


def terraform_bin(runtime):
    # `.venv` is uv's managed venv (see docs/DEPS.md).
    path = os.path.join(runtime.CATS_HOME, '.venv', 'bin', 'terraform')
    return path if os.path.isfile(path) else 'terraform'


def _add_exec_bit(path):
    if os.access(path, os.X_OK):
        return
    mode = os.stat(path).st_mode
    os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ensure_provider_binaries_executable(tf_data_dir):
    """Terraform provider binaries (and, occasionally, the directories
    extracted alongside them) have been observed to lose their executable
    bit under this workspace (root cause not fully understood - not
    reproducible when the same `terraform init` extracts outside the
    project directory), which makes every subsequent `plan`/`apply`/
    `destroy`/`init` fail with "permission denied". Directories need
    +x to even be traversed into, so fix each directory just before
    `os.walk` descends into it - fixing only leaf files isn't enough
    if an ancestor directory also lost +x.
    """
    providers_dir = os.path.join(tf_data_dir, 'providers')
    if not os.path.isdir(providers_dir):
        return
    _add_exec_bit(providers_dir)
    for root, dirs, files in os.walk(providers_dir, topdown=True):
        for name in dirs:
            _add_exec_bit(os.path.join(root, name))
        for name in files:
            if 'terraform-provider' in name:
                _add_exec_bit(os.path.join(root, name))


def configure_terraform_data_dir(structure_home):
    # TF_DATA_DIR must not equal the module root; that breaks backend state loading.
    # Always absolute: terraform resolves relative TF_DATA_DIR against its cwd
    # (structure_home), while this helper may run with a different process cwd.
    tf_data_dir = os.path.abspath(os.path.join(structure_home, '.terraform-data'))
    os.makedirs(tf_data_dir, exist_ok=True)
    os.environ['TF_DATA_DIR'] = tf_data_dir
    ensure_provider_binaries_executable(tf_data_dir)
    return tf_data_dir


def ensure_integration_cache_env(runtime):
    # Docker Compose bind mounts require an absolute host path; relative paths
    # are treated as named volumes and fail with "undefined volume".
    cache = os.path.abspath(runtime.INTEGRATION_INPUT_DATA_CACHE)
    os.makedirs(cache, exist_ok=True)
    os.environ['INTEGRATION_INPUT_DATA_CACHE'] = cache
    return cache


def _parse_lock_providers(lock_path):
    providers = []
    current = None
    with open(lock_path, encoding='utf-8') as lock_file:
        for line in lock_file:
            provider_match = re.match(
                r'\s*provider\s+"registry\.terraform\.io/([^"]+)"',
                line,
            )
            if provider_match:
                current = provider_match.group(1)
                continue
            if current:
                version_match = re.match(r'\s*version\s*=\s*"([^"]+)"', line)
                if version_match:
                    providers.append((current, version_match.group(1)))
                    current = None
    return providers


def _provider_binary_present(platform_path):
    for name in os.listdir(platform_path):
        path = os.path.join(platform_path, name)
        if os.path.isfile(path) and os.access(path, os.X_OK) and 'terraform-provider' in name:
            return True
    return False


def providers_cached(structure_home):
    lock_path = os.path.join(structure_home, '.terraform.lock.hcl')
    tf_data_dir = os.path.join(structure_home, '.terraform-data')
    if not os.path.isfile(lock_path) or not os.path.isdir(tf_data_dir):
        return False

    required = _parse_lock_providers(lock_path)
    if not required:
        return False

    for provider, version in required:
        version_dir = os.path.join(
            tf_data_dir,
            'providers',
            'registry.terraform.io',
            provider,
            version,
        )
        if not os.path.isdir(version_dir):
            return False
        if not any(
            _provider_binary_present(os.path.join(version_dir, platform))
            for platform in os.listdir(version_dir)
            if os.path.isdir(os.path.join(version_dir, platform))
        ):
            return False
    return True


def modules_installed(structure_home):
    """True when TF module cache dirs exist for every entry in modules.json.

    After local module ``source`` path changes (e.g. ``modules/plant`` →
    ``plant``), providers may still be cached while the module cache is
    stale; ``terraform destroy``/``apply`` then fail with "Module not
    installed". ``initialize`` must re-run ``init`` in that case.
    """
    modules_json = os.path.join(
        structure_home, '.terraform-data', 'modules', 'modules.json'
    )
    if not os.path.isfile(modules_json):
        return False
    try:
        with open(modules_json, encoding='utf-8') as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False
    modules = payload.get('Modules') or []
    if not modules:
        return False
    for entry in modules:
        rel = entry.get('Dir') or '.'
        if rel in ('', '.'):
            continue
        if not os.path.isdir(os.path.join(structure_home, rel)):
            return False
    return True


def _terraform_state_resources(runtime, structure_home):
    configure_terraform_data_dir(structure_home)
    proc = subproc_run(
        f'{terraform_bin(runtime)} state list',
        cwd=structure_home,
    )
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _path_has_open_holders(path):
    """True when ``lsof`` reports a live process holding ``path`` open."""
    if not path or not os.path.exists(path):
        return False
    proc = subproc_run(f'lsof -t -- {path}')
    if proc.returncode != 0:
        return False
    return bool(proc.stdout.strip())


def heal_stale_terraform_state_lock(structure_home):
    """Drop a local Terraform state lock left by an interrupted apply/destroy.

    Ctrl-C during ``terraform apply`` often leaves
    ``.terraform.tfstate.lock.info`` behind; the next ``destroy``/``apply``
    then fails with "Error acquiring the state lock". When no process still
    holds the lock info or ``terraform.tfstate`` open, the lock is stale and
    safe to remove (same heal class as ContentStore stale ``repo.lock``).
    """
    lock_path = os.path.join(structure_home, TF_STATE_LOCK_INFO)
    if not os.path.isfile(lock_path):
        return
    state_path = os.path.join(structure_home, 'terraform.tfstate')
    if _path_has_open_holders(lock_path) or _path_has_open_holders(state_path):
        return
    try:
        os.unlink(lock_path)
    except OSError:
        return
    print(
        f'Removed stale Terraform state lock at {lock_path} '
        f'(no live holder for this Structure home).'
    )


def _terraform_output(runtime, structure_home, name):
    proc = subproc_run(
        f'{terraform_bin(runtime)} output -raw {name}',
        cwd=structure_home,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


