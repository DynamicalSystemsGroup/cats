import importlib.util
import os
import sys

from cats.executor.structure._tf import (
    _load_transport_utils_module,
    _terraform_output,
    cleanup_stale_docker_compose_ipfs_transport_state,
    configure_terraform_data_dir,
    ensure_integration_cache_env,
    ensure_provider_binaries_executable,
    modules_installed,
    providers_cached,
    terraform_bin,
)
from cats.executor.structure.plant import Plant


class InfraStructure:
    def __init__(self, runtime, structure_cid):
        self.runtime = runtime
        self.structure_cid = structure_cid
        self.INPUT_STRUCTURE_HOME = self.runtime.INPUT_STRUCTURE_HOME
        configure_terraform_data_dir(self.INPUT_STRUCTURE_HOME)
        ensure_integration_cache_env(self.runtime)
        print(
            f"Environment variable INTEGRATION_INPUT_DATA_CACHE is set to:",
            os.environ["INTEGRATION_INPUT_DATA_CACHE"]
        )

    def compose(self):
        return Plant(self)

    def snapshot(self, *, object_store_as_executed_cid: str) -> dict:
        """Infra as-executed pairing (CID refs; widen later beyond ObjectStore).

        Parallel to as-Code ``infrastructure_cid``. Currently records only the
        ObjectStore facet; transport / ContentStore keys may be added later.
        Minted by Executor as ``infrastructure_as_executed_cid``.
        """
        return {
            'object_store_as_executed_cid': object_store_as_executed_cid,
        }

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

        T&D facet for Process port (migrate / stage_for_plant). Peering mutate
        is TF shell_script.ipfs_transport_peering (every apply); apply only
        asserts — not Process heal.
        """
        utils = self._load_transport_module()
        return utils.TransportContext.default(
            structure_home=self.INPUT_STRUCTURE_HOME
        )

    def transport_assert(self):
        """Fail loud if Order-submitted transport peer containers are not up.

        Executor composes à la carte TF (ipfs_transport_peering ensures swarm
        every apply); this only probes container readiness.
        """
        try:
            self.transport_context().assert_ready()
        except RuntimeError as exc:
            raise RuntimeError(
                'InfraStructure transport peers not ready after Structure '
                'terraform apply. TF shell_script.ipfs_transport_peering '
                'should have peered them; heal via '
                'transport_utils.py ensure-peered or re-apply Structure. '
                f'({exc})'
            ) from exc

    def content_store_ensure(self, cwd=None):
        """À la carte Order-submitted ContentStore.ensure (same tree as TF CLI).

        Distinct from ContentMesh bootstrap ensure (repo default tree). Structure
        apply does **not** call this — TF ``shell_script.host_ipfs_daemon``
        create is the sole Order-submitted mutate path; apply only asserts.
        """
        utils = self._load_content_store_module()
        utils.ContentStore.ensure(cwd=cwd)

    def content_store_assert(self):
        """Fail loud if Order-submitted ContentStore is not ready after TF.

        Executor composes à la carte TF (which ensures on host_ipfs_daemon
        create); this only probes readiness.
        """
        utils = self._load_content_store_module()
        if utils.ContentStore.is_ready():
            return
        raise RuntimeError(
            'Host Kubo ContentStore not ready after Structure terraform apply. '
            'TF shell_script.host_ipfs_daemon create should have ensured it; '
            'heal via make content-store-ensure / node ensure, or replace '
            'host_ipfs_daemon so create re-runs.'
        )

    def destroy(self):
        print('Destroy Structure!')
        configure_terraform_data_dir(self.INPUT_STRUCTURE_HOME)
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
        # ContentStore.ensure is à la carte TF (host_ipfs_daemon create), not
        # Python apply — Executor only asserts readiness after terraform apply.
        self.compose()._load_plant_utils().cleanup_stale_plant_state(
            self.INPUT_STRUCTURE_HOME,
            terraform_bin(self.runtime),
            configure_tf_data_dir=configure_terraform_data_dir,
        )
        cleanup_stale_docker_compose_ipfs_transport_state(self.runtime, self.INPUT_STRUCTURE_HOME)
        self._load_obj_store_module().cleanup_stale_obj_store_state(
            self.INPUT_STRUCTURE_HOME,
            terraform_bin(self.runtime),
            configure_tf_data_dir=configure_terraform_data_dir,
        )
        self.runtime.executeCMD(
            f'{terraform_bin(self.runtime)} apply --auto-approve',
            cwd=self.INPUT_STRUCTURE_HOME
        )
        print('Assert InfraStructure content store ready (Order-submitted)...')
        self.content_store_assert()
        # Peering mutate is à la carte TF (ipfs_transport_peering every apply);
        # Executor only asserts containers are up.
        print('Assert InfraStructure transport peers ready (Order-submitted)...')
        self.transport_assert()
        print()
        print()