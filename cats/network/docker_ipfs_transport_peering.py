import subprocess

MIGRATION_CONTAINER = 'structure-ipfs_migration-1'
INTEGRATION_CONTAINER = 'structure-ipfs_integration-1'
IPFS_GET_TIMEOUT = 600


def _run(cmd, **kwargs):
    kwargs.setdefault('shell', True)
    kwargs.setdefault('capture_output', True)
    kwargs.setdefault('text', True)
    return subprocess.run(cmd, **kwargs)


def _container_ip(container):
    proc = _run(
        "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "
        f"{container}"
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _container_peer_id(container):
    proc = _run(f"docker exec {container} ipfs id -f '<id>'")
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _host_peer_id():
    proc = _run("ipfs id -f '<id>'")
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _swarm_connect(container, multiaddr):
    _run(f"docker exec {container} ipfs swarm connect {multiaddr}")


def ensure_docker_ipfs_peers():
    """Connect transport containers to the host IPFS daemon and to each other."""
    proc = _run(
        f"docker ps --format '{{{{.Names}}}}' | grep -qx '{MIGRATION_CONTAINER}'"
    )
    if proc.returncode != 0:
        return

    host_peer = _host_peer_id()
    if host_peer:
        host_maddr = f"/dns4/host.docker.internal/tcp/4001/p2p/{host_peer}"
        for container in (MIGRATION_CONTAINER, INTEGRATION_CONTAINER):
            _swarm_connect(container, host_maddr)
            ip = _container_ip(container)
            peer = _container_peer_id(container)
            if ip and peer:
                _run(f"ipfs swarm connect /ip4/{ip}/tcp/4001/p2p/{peer}")

    migration_ip = _container_ip(MIGRATION_CONTAINER)
    migration_peer = _container_peer_id(MIGRATION_CONTAINER)
    integration_ip = _container_ip(INTEGRATION_CONTAINER)
    integration_peer = _container_peer_id(INTEGRATION_CONTAINER)

    if migration_ip and migration_peer:
        _swarm_connect(
            INTEGRATION_CONTAINER,
            f"/ip4/{migration_ip}/tcp/4001/p2p/{migration_peer}",
        )
    if integration_ip and integration_peer:
        _swarm_connect(
            MIGRATION_CONTAINER,
            f"/ip4/{integration_ip}/tcp/4001/p2p/{integration_peer}",
        )
