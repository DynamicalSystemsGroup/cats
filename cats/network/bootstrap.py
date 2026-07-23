"""Bootstrap (repo-default) ContentStore probe helpers."""
import importlib.util
import os
import sys

def _bootstrap_content_store_utils_path(cats_home):
    """Repo-default content_store_utils.py (not Order-submitted Structure)."""
    if not cats_home:
        return None
    return os.path.join(
        cats_home,
        'data',
        'input',
        'structure',
        'infrastructure',
        'content_store_utils.py',
    )


def _load_bootstrap_content_store_module(cats_home):
    """Load default-tree ContentStore for pre-Structure CID work only.

    Not Order-bound — Order-submitted ensure is TF shell_script.host_ipfs_daemon
    create; InfraStructure.apply only asserts is_ready after terraform apply.
    """
    path = _bootstrap_content_store_utils_path(cats_home)
    if path is None:
        raise RuntimeError('CATS_HOME is required to locate content_store_utils')
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(
        'infrastructure_content_store_utils_bootstrap', path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
