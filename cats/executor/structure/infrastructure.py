import importlib.util
import os
import shutil
import subprocess
import sys

from cats.executor.structure._tf import (
    _load_transport_utils_module,
    _terraform_output,
    configure_terraform_data_dir,
    ensure_integration_cache_env,
    ensure_provider_binaries_executable,
    heal_stale_terraform_state_lock,
    modules_installed,
    providers_cached,
    terraform_bin,
)
from cats.executor.structure.plant import Plant

_DOCKER_REQUIRED = (
    'Docker daemon is not running; Structure apply/destroy needs it for '
    'MinIO scratch and Plant / KubeRay (start Docker Desktop, then retry). '
    'See docs/DEMO.md.'
)


def docker_daemon_ready() -> bool:
    """True when ``docker info`` can reach a running daemon."""
    if shutil.which('docker') is None:
        return False
    try:
        proc = subprocess.run(
            ['docker', 'info'],
            capture_output=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def require_docker_daemon() -> None:
    """Raise if Structure Terraform cannot ping Docker (MinIO / kind)."""
    if not docker_daemon_ready():
        raise RuntimeError(_DOCKER_REQUIRED)


class InfraStructure:
    def __init__(self, runtime, structure_id):
        self.runtime = runtime
        self.structure_id = structure_id
        self.INPUT_STRUCTURE_HOME = self.runtime.INPUT_STRUCTURE_HOME
        configure_terraform_data_dir(self.INPUT_STRUCTURE_HOME)
        ensure_integration_cache_env(self.runtime)
        print(
            f"Environment variable INTEGRATION_INPUT_DATA_CACHE is set to:",
            os.environ["INTEGRATION_INPUT_DATA_CACHE"]
        )

    def compose(self):
        return Plant(self)

    def snapshot(self, *, object_store_as_executed_id: str) -> dict:
        """Infra as-executed pairing (uri-only refs; widen later beyond ObjectStore).

        Parallel to as-Code ``infrastructure`` ref. Currently records only the
        ObjectStore facet; transport / ContentStore keys may be added later.
        Minted by Executor as ``infrastructure_as_executed``.
        """
        from cats.network.cas import set_ref

        out = {}
        set_ref(out, 'object_store_as_executed', object_store_as_executed_id)
        return out

    def _load_obj_store_module(self):
        """Load Order-submitted infrastructure object-store utils."""
        path = os.path.join(
            self.INPUT_STRUCTURE_HOME, 'infrastructure', 'obj_store_utils.py'
        )
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        spec = importlib.util.spec_from_file_location(
            'infrastructure_obj_store_utils', path
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        # Required before exec_module so @dataclass can resolve cls.__module__.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def _load_transport_module(self):
        """Load Order-submitted infrastructure transport utils."""
        return _load_transport_utils_module(self.INPUT_STRUCTURE_HOME)

    def _load_content_store_module(self):
        """Load Order-submitted infrastructure content-store utils."""
        path = os.path.join(
            self.INPUT_STRUCTURE_HOME,
            'infrastructure',
            'content_store_utils.py',
        )
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        spec = importlib.util.spec_from_file_location(
            'infrastructure_content_store_utils_order', path
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def obj_store_context(self):
        """Resolve the deployed object store from terraform outputs via the
        Order-submitted infrastructure utils module (directory model)."""
        utils = self._load_obj_store_module()
        structure_home = self.INPUT_STRUCTURE_HOME
        runtime = self.runtime

        def get_output(name):
            return _terraform_output(runtime, structure_home, name)

        return utils.ObjectStore.from_terraform_outputs(get_output)

    def transport_context(self):
        """Resolve TransportContext from Order-submitted transport_utils.

        CAS migrate / stage_for_plant only (§6s — no Docker peer assert).
        """
        utils = self._load_transport_module()
        return utils.TransportContext.default(
            structure_home=self.INPUT_STRUCTURE_HOME
        )

    def content_store_ensure(self, cwd=None):
        """À la carte Order-submitted ContentStore.ensure (optional operator).

        Distinct from ContentMesh bootstrap soft-probe (repo default tree).
        Structure apply does **not** require this (§6s).
        """
        utils = self._load_content_store_module()
        utils.ContentStore.ensure(cwd=cwd)

    def content_store_assert(self):
        """Soft-probe Order-submitted ContentStore after TF (§6s).

        Does not heal and does not raise — Kubo is optional for CAS-only.
        Operator heal remains ``make content-store-ensure`` / ``node ensure``.
        """
        try:
            utils = self._load_content_store_module()
            if utils.ContentStore.is_ready():
                return
            print(
                'WARNING: host ContentStore API not ready (optional §6s); '
                'run make content-store-ensure or python -m cats.node ensure '
                'if you still need Kubo tooling.',
                flush=True,
            )
        except (RuntimeError, FileNotFoundError, OSError) as exc:
            print(
                f'WARNING: Order-submitted ContentStore probe failed (§6s): {exc}',
                flush=True,
            )

    def _cleanup_stale_structure_state(self):
        """Drop TF state that cannot refresh when host resources are gone.

        Same healers as ``apply`` — required before ``destroy`` too, because
        ``redeploy()`` destroys first. If kind was wiped (Docker Desktop reset)
        while Plant resources remain in state, bare ``terraform destroy`` fails
        on refresh (``could not locate any control plane nodes``). Also clears
        a stale local state lock left by Ctrl-C during apply/destroy.
        """
        heal_stale_terraform_state_lock(self.INPUT_STRUCTURE_HOME)
        self.compose()._load_plant_utils().cleanup_stale_plant_state(
            self.INPUT_STRUCTURE_HOME,
            terraform_bin(self.runtime),
            configure_tf_data_dir=configure_terraform_data_dir,
        )
        self._load_obj_store_module().cleanup_stale_obj_store_state(
            self.INPUT_STRUCTURE_HOME,
            terraform_bin(self.runtime),
            configure_tf_data_dir=configure_terraform_data_dir,
        )

    def destroy(self):
        print('Destroy Structure!')
        configure_terraform_data_dir(self.INPUT_STRUCTURE_HOME)
        ensure_integration_cache_env(self.runtime)
        require_docker_daemon()
        self._cleanup_stale_structure_state()
        self.runtime.executeCMD(
            f'{terraform_bin(self.runtime)} destroy --auto-approve',
            cwd=self.INPUT_STRUCTURE_HOME
        )
        print()
        print()

    def plan(self):
        print('Plan Structure!')
        configure_terraform_data_dir(self.INPUT_STRUCTURE_HOME)
        self.runtime.executeCMD(
            f'{terraform_bin(self.runtime)} plan',
            cwd=self.INPUT_STRUCTURE_HOME
        )
        print()
        print()

    def initialize(self):
        print('Initialize Structure!')
        tf_data_dir = configure_terraform_data_dir(self.INPUT_STRUCTURE_HOME)
        if (
            providers_cached(self.INPUT_STRUCTURE_HOME)
            and modules_installed(self.INPUT_STRUCTURE_HOME)
        ):
            print('Terraform providers and modules already cached; skipping init.')
            print()
            return
        self.runtime.executeCMD(
            f'{terraform_bin(self.runtime)} init -input=false',
            cwd=self.INPUT_STRUCTURE_HOME
        )
        # `init` just (re)extracted provider binaries; make sure they're
        # actually executable before anything tries to run them.
        ensure_provider_binaries_executable(tf_data_dir)
        print()
        print()

    def apply(self):
        print('Apply Structure!')
        configure_terraform_data_dir(self.INPUT_STRUCTURE_HOME)
        ensure_integration_cache_env(self.runtime)
        require_docker_daemon()
        # Host Kubo TF ensure + Docker peer assert retired (§6s). Soft-probe
        # ContentStore only; Process transport is CAS-only.
        self._cleanup_stale_structure_state()
        self.runtime.executeCMD(
            f'{terraform_bin(self.runtime)} apply --auto-approve',
            cwd=self.INPUT_STRUCTURE_HOME
        )
        print('Probe InfraStructure content store (optional §6s)...')
        self.content_store_assert()
        print()
        print()
