import os
import re
import stat

from cats.utils import subproc_run
from cats.network.ipfs_docker import MIGRATION_CONTAINER, INTEGRATION_CONTAINER

KIND_CLUSTER_NAME = "cats"
KIND_CLUSTER_RESOURCE = "module.plant.kind_cluster.default"
# Resources in module.plant that depend on kind_cluster.default and thus
# can't be reconciled (or even refreshed) once its cluster is gone from the host.
KIND_DEPENDENT_RESOURCES = (
    "module.plant.helm_release.ray-cluster",
    "module.plant.helm_release.kuberay-operator",
)
DOCKER_COMPOSE_IPFS_TRANSPORT_RESOURCE = "module.infrastructure.shell_script.docker_compose_ipfs_transport"
APPLIED_STRUCTURE_MARKER = '.applied-structure.cid'


def _applied_structure_marker_path(structure_home):
    return os.path.join(structure_home, APPLIED_STRUCTURE_MARKER)


def read_applied_structure_cid(structure_home):
    """Return the structure_cid this Structure's Terraform state currently
    reflects, or None if nothing has been successfully applied yet."""
    marker_path = _applied_structure_marker_path(structure_home)
    if not os.path.isfile(marker_path):
        return None
    with open(marker_path, encoding='utf-8') as marker_file:
        return marker_file.read().strip() or None


def write_applied_structure_cid(structure_home, structure_cid):
    """Record the structure_cid Terraform state now reflects, so a later
    CAT execution with an unchanged (content-addressed) Structure can
    reconcile in place instead of destroying and rebuilding the Plant."""
    with open(_applied_structure_marker_path(structure_home), 'w', encoding='utf-8') as marker_file:
        marker_file.write(structure_cid or '')


def terraform_bin(service):
    # `.venv` is uv's managed venv (see docs/DEPS.md).
    path = os.path.join(service.CATS_HOME, '.venv', 'bin', 'terraform')
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
    tf_data_dir = os.path.join(structure_home, '.terraform-data')
    os.makedirs(tf_data_dir, exist_ok=True)
    os.environ['TF_DATA_DIR'] = tf_data_dir
    ensure_provider_binaries_executable(tf_data_dir)
    return tf_data_dir


def ensure_integration_cache_env(service):
    # Docker Compose bind mounts require an absolute host path; relative paths
    # are treated as named volumes and fail with "undefined volume".
    cache = os.path.abspath(service.INTEGRATION_INPUT_DATA_CACHE)
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


def _terraform_state_resources(service, structure_home):
    configure_terraform_data_dir(structure_home)
    proc = subproc_run(
        f'{terraform_bin(service)} state list',
        cwd=structure_home,
    )
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _kind_cluster_names():
    proc = subproc_run('kind get clusters')
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _docker_container_running(container):
    proc = subproc_run(
        f"docker ps --format '{{{{.Names}}}}' | grep -qx '{container}'"
    )
    return proc.returncode == 0


def cleanup_orphan_kind_cluster(service, structure_home):
    """Remove a leftover kind cluster when it exists on the host but not in state."""
    clusters = _kind_cluster_names()
    if KIND_CLUSTER_NAME not in clusters:
        return

    state = _terraform_state_resources(service, structure_home)
    if KIND_CLUSTER_RESOURCE in state:
        return

    print(
        f'Removing orphan kind cluster "{KIND_CLUSTER_NAME}" '
        f'({KIND_CLUSTER_RESOURCE} is not in Terraform state)'
    )
    proc = subproc_run(f'kind delete cluster --name {KIND_CLUSTER_NAME}')
    if proc.returncode != 0:
        raise RuntimeError(
            f'Failed to delete orphan kind cluster "{KIND_CLUSTER_NAME}": {proc.stderr.strip()}'
        )
    if proc.stdout.strip():
        print(proc.stdout.strip())


def cleanup_stale_kind_cluster_state(service, structure_home):
    """Remove state entries for the kind cluster (and Helm releases that
    depend on it) when Terraform state believes the cluster still exists
    but the host does not have it - e.g. after a Docker Desktop restart or
    reset wiped its containers out from under Terraform. Left alone, the
    next `apply` fails during its automatic refresh with something like
    "could not locate any control plane nodes for cluster named 'cats'"
    before it ever gets a chance to recreate anything."""
    state = _terraform_state_resources(service, structure_home)
    if KIND_CLUSTER_RESOURCE not in state:
        return

    clusters = _kind_cluster_names()
    if KIND_CLUSTER_NAME in clusters:
        return

    stale_resources = [
        resource for resource in (*KIND_DEPENDENT_RESOURCES, KIND_CLUSTER_RESOURCE)
        if resource in state
    ]
    print(
        f'Terraform state has "{KIND_CLUSTER_RESOURCE}" but no kind cluster named '
        f'"{KIND_CLUSTER_NAME}" exists on the host; removing stale state for: '
        f'{", ".join(stale_resources)}'
    )
    proc = subproc_run(
        f'{terraform_bin(service)} state rm {" ".join(stale_resources)}',
        cwd=structure_home,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f'Failed to remove stale Terraform state for "{KIND_CLUSTER_NAME}": '
            f'{proc.stderr.strip()}'
        )
    if proc.stdout.strip():
        print(proc.stdout.strip())


def cleanup_stale_docker_compose_ipfs_transport_state(service, structure_home):
    """Remove the state entry for the IPFS transport Docker Compose stack
    when Terraform state believes it's already up but its containers are
    gone from the host - e.g. after a Docker Desktop restart or reset.

    Unlike `shell_script.host_ipfs_daemon`, this resource's `create` script
    isn't idempotent/self-probing, and the `scottwinkler/shell` provider
    has no `read` command to detect this drift on its own - so once this
    resource is in state, plain `apply` never notices the containers are
    missing and never re-runs `create`. Left alone, `ingress`/`egress`
    then fail against a nonexistent container (e.g. "No such container:
    structure-ipfs_migration-1") the next time a CAT executes."""
    state = _terraform_state_resources(service, structure_home)
    if DOCKER_COMPOSE_IPFS_TRANSPORT_RESOURCE not in state:
        return

    if _docker_container_running(MIGRATION_CONTAINER) and _docker_container_running(INTEGRATION_CONTAINER):
        return

    print(
        f'Terraform state has "{DOCKER_COMPOSE_IPFS_TRANSPORT_RESOURCE}" but its '
        f'containers ("{MIGRATION_CONTAINER}", "{INTEGRATION_CONTAINER}") are not '
        f'running on the host; removing stale state so apply recreates them'
    )
    proc = subproc_run(
        f'{terraform_bin(service)} state rm {DOCKER_COMPOSE_IPFS_TRANSPORT_RESOURCE}',
        cwd=structure_home,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f'Failed to remove stale Terraform state for '
            f'"{DOCKER_COMPOSE_IPFS_TRANSPORT_RESOURCE}": {proc.stderr.strip()}'
        )
    if proc.stdout.strip():
        print(proc.stdout.strip())


def _terraform_output(service, structure_home, name):
    proc = subproc_run(
        f'{terraform_bin(service)} output -raw {name}',
        cwd=structure_home,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


class Plant:
    """Composed, read-only accessor over the deployed Plant (`module.plant`
    in main.tf): the kind cluster + Helm releases that constitute the
    dynamically scaled execution environment InfraStructure provisions and
    maintains. Always obtained via `InfraStructure.compose()`, mirroring
    how `InfraFunction.compose()` produces a `Processor`."""

    def __init__(self, infraStructure):
        self.infraStructure = infraStructure
        # Set by Structure.deploy()/redeploy() after each reconcile(), so
        # snapshot() can record whether this reconciliation reused the
        # existing Plant or destroyed and rebuilt it.
        self.rebuilt = None

    def kind_cluster_name(self):
        return _terraform_output(
            self.infraStructure.service, self.infraStructure.INPUT_STRUCTURE_HOME, 'plant_kind_cluster_name'
        )

    def kubeconfig_context(self):
        return _terraform_output(
            self.infraStructure.service, self.infraStructure.INPUT_STRUCTURE_HOME, 'plant_kubeconfig_context'
        )

    def ray_release_name(self):
        return _terraform_output(
            self.infraStructure.service, self.infraStructure.INPUT_STRUCTURE_HOME, 'plant_ray_release_name'
        )

    def snapshot(self):
        """Plain dict describing what this Plant currently is, for
        recording into the CAT's BOM alongside Function's output (see
        Executor.execute() in cats/factory/__init__.py)."""
        return {
            'kind_cluster_name': self.kind_cluster_name(),
            'kubeconfig_context': self.kubeconfig_context(),
            'ray_release_name': self.ray_release_name(),
            'applied_structure_cid': read_applied_structure_cid(self.infraStructure.INPUT_STRUCTURE_HOME),
            'rebuilt': self.rebuilt,
        }


class InfraStructure:
    def __init__(self, service):
        self.service = service
        self.INPUT_STRUCTURE_HOME = self.service.INPUT_STRUCTURE_HOME
        configure_terraform_data_dir(self.INPUT_STRUCTURE_HOME)
        ensure_integration_cache_env(self.service)
        print(
            f"Environment variable INTEGRATION_INPUT_DATA_CACHE is set to:",
            os.environ["INTEGRATION_INPUT_DATA_CACHE"]
        )

    def compose(self):
        return Plant(self)

    def destroy(self):
        print('Destroy Structure!')
        configure_terraform_data_dir(self.INPUT_STRUCTURE_HOME)
        self.service.executeCMD(
            f'{terraform_bin(self.service)} destroy --auto-approve',
            cwd=self.INPUT_STRUCTURE_HOME
        )
        print()
        print()

    def plan(self):
        print('Plan Structure!')
        configure_terraform_data_dir(self.INPUT_STRUCTURE_HOME)
        self.service.executeCMD(
            f'{terraform_bin(self.service)} plan',
            cwd=self.INPUT_STRUCTURE_HOME
        )
        print()
        print()

    def initialize(self):
        print('Initialize Structure!')
        tf_data_dir = configure_terraform_data_dir(self.INPUT_STRUCTURE_HOME)
        if providers_cached(self.INPUT_STRUCTURE_HOME):
            print('Terraform providers already cached; skipping init.')
            print()
            return
        self.service.executeCMD(
            f'{terraform_bin(self.service)} init -input=false',
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
        ensure_integration_cache_env(self.service)
        cleanup_orphan_kind_cluster(self.service, self.INPUT_STRUCTURE_HOME)
        cleanup_stale_kind_cluster_state(self.service, self.INPUT_STRUCTURE_HOME)
        cleanup_stale_docker_compose_ipfs_transport_state(self.service, self.INPUT_STRUCTURE_HOME)
        self.service.executeCMD(
            f'{terraform_bin(self.service)} apply --auto-approve',
            cwd=self.INPUT_STRUCTURE_HOME
        )
        peer_script = os.path.join(
            self.INPUT_STRUCTURE_HOME, 'modules', 'infrastructure', 'ipfs_connect_peers.sh'
        )
        if os.path.isfile(peer_script):
            print('Connect IPFS transport peers...')
            proc = subproc_run(f'bash {peer_script}', cwd=self.INPUT_STRUCTURE_HOME)
            if proc.stdout.strip():
                print(proc.stdout.strip())
            if proc.returncode != 0 and proc.stderr.strip():
                print(proc.stderr.strip())
        print()
        print()