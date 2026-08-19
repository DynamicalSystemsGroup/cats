"""Structure / Function tree staging for content-addressed Orders."""
import os
import shutil
import tempfile

# Compose glue CIDed as structure_cid.root_cid (not plant/ or infrastructure/).
STRUCTURE_ROOT_DIRNAME = 'structure-root'
STRUCTURE_ROOT_FILES = (
    'main.tf',
    'outputs.tf',
    '.terraform.lock.hcl',
)


def stage_structure_root(structure_filepath, staging_parent=None):
    """Copy allowlisted Structure root files into a temp ``structure-root/`` dir.

    Returns the staging directory path (basename ``structure-root``) for
    ``put_dir``. Caller must remove the parent temp tree when finished if
    ``staging_parent`` was not supplied.
    """
    structure_filepath = structure_filepath.rstrip('/')
    if staging_parent is None:
        staging_parent = tempfile.mkdtemp(prefix='cats-structure-root-')
    staging_dir = os.path.join(staging_parent, STRUCTURE_ROOT_DIRNAME)
    os.makedirs(staging_dir, exist_ok=True)
    missing = []
    for name in STRUCTURE_ROOT_FILES:
        src = os.path.join(structure_filepath, name)
        if not os.path.isfile(src):
            missing.append(name)
            continue
        shutil.copy2(src, os.path.join(staging_dir, name))
    if missing:
        shutil.rmtree(staging_parent, ignore_errors=True)
        raise FileNotFoundError(
            'Structure root allowlist incomplete under '
            f'{structure_filepath!r}; missing: {missing}'
        )
    return staging_dir


def materialize_structure_root_files(fetched_root_dir, structure_home):
    """Copy allowlisted files from a fetched root CID tree into Structure home.

    Does not delete ``structure_home`` (preserves terraform state / child dirs).
    """
    os.makedirs(structure_home, exist_ok=True)
    # Kubo get may land files at dest/ or nest under structure-root/.
    candidates = [fetched_root_dir]
    nested = os.path.join(fetched_root_dir, STRUCTURE_ROOT_DIRNAME)
    if os.path.isdir(nested):
        candidates.append(nested)
    source_dir = None
    for candidate in candidates:
        if all(
            os.path.isfile(os.path.join(candidate, name))
            for name in STRUCTURE_ROOT_FILES
        ):
            source_dir = candidate
            break
    if source_dir is None:
        # Accept whatever allowlisted files exist at the fetch root.
        for candidate in candidates:
            if any(
                os.path.isfile(os.path.join(candidate, name))
                for name in STRUCTURE_ROOT_FILES
            ):
                source_dir = candidate
                break
    if source_dir is None:
        raise RuntimeError(
            f'Structure root_cid fetch at {fetched_root_dir!r} has none of '
            f'{STRUCTURE_ROOT_FILES}'
        )
    for name in STRUCTURE_ROOT_FILES:
        src = os.path.join(source_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(structure_home, name))


# Function package dirs CIDed as function_cid.process_source_cid /
# infrafunction_source_cid (sibling of structure/ under input/).
FUNCTION_PACKAGE_NAMES = ('process', 'infrafunction')

def resolve_function_package_dirs(structure_filepath):
    """Return ``{process, infrafunction}`` paths beside Structure under ``function/``.

    ``structure_filepath`` is ``…/input/structure`` → packages live at
    ``…/input/function/{process,infrafunction}``.
    """
    structure_filepath = structure_filepath.rstrip('/')
    function_home = os.path.join(os.path.dirname(structure_filepath), 'function')
    paths = {
        name: os.path.join(function_home, name) for name in FUNCTION_PACKAGE_NAMES
    }
    missing = [name for name, path in paths.items() if not os.path.isdir(path)]
    if missing:
        raise FileNotFoundError(
            'Function source packages missing under '
            f'{function_home!r}; missing: {missing}'
        )
    return paths


def stage_function_package(package_dir, staging_parent=None, *, basename=None):
    """Copy a Function package tree excluding ``__pycache__`` / ``*.pyc``.

    Returns the staging directory path (basename matches the package name)
    for ``put_dir``. Caller must remove the parent temp tree when finished if
    ``staging_parent`` was not supplied.
    """
    package_dir = package_dir.rstrip('/')
    if basename is None:
        basename = os.path.basename(package_dir)
    if staging_parent is None:
        staging_parent = tempfile.mkdtemp(prefix='cats-function-pkg-')
    staging_dir = os.path.join(staging_parent, basename)
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)

    def _ignore(directory, names):
        ignored = set()
        for name in names:
            if name == '__pycache__' or name.endswith('.pyc'):
                ignored.add(name)
        return ignored

    shutil.copytree(package_dir, staging_dir, ignore=_ignore)
    return staging_dir
