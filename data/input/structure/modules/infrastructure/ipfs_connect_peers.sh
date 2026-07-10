#!/usr/bin/env bash
# Connect Docker IPFS transport nodes to the host daemon and to each other so
# ipfs get can resolve CIDs created on the host or sibling containers.
set -euo pipefail

MIGRATION_CONTAINER="${MIGRATION_CONTAINER:-structure-ipfs_migration-1}"
INTEGRATION_CONTAINER="${INTEGRATION_CONTAINER:-structure-ipfs_integration-1}"
IPFS_SWARM_PORT="${IPFS_SWARM_PORT:-4001}"

wait_for_ipfs() {
  local container="$1"
  local attempt
  for attempt in $(seq 1 60); do
    if docker exec "$container" ipfs id >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for IPFS daemon in ${container}" >&2
  return 1
}

swarm_connect() {
  local container="$1"
  local multiaddr="$2"
  docker exec "$container" ipfs swarm connect "${multiaddr}" >/dev/null 2>&1 || true
}

host_swarm_connect() {
  local multiaddr="$1"
  ipfs swarm connect "${multiaddr}" >/dev/null 2>&1 || true
}

for container in "${MIGRATION_CONTAINER}" "${INTEGRATION_CONTAINER}"; do
  if ! docker ps --format '{{.Names}}' | grep -qx "${container}"; then
    echo "Container ${container} is not running; skipping IPFS peering." >&2
    exit 0
  fi
done

for container in "${MIGRATION_CONTAINER}" "${INTEGRATION_CONTAINER}"; do
  wait_for_ipfs "${container}"
done

if host_peer="$(ipfs id -f '<id>' 2>/dev/null)"; then
  host_maddr="/dns4/host.docker.internal/tcp/${IPFS_SWARM_PORT}/p2p/${host_peer}"
  echo "Connecting Docker IPFS nodes to host peer ${host_peer}..."
  for container in "${MIGRATION_CONTAINER}" "${INTEGRATION_CONTAINER}"; do
    swarm_connect "${container}" "${host_maddr}"
  done

  for container in "${MIGRATION_CONTAINER}" "${INTEGRATION_CONTAINER}"; do
    ip="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${container}")"
    peer="$(docker exec "${container}" ipfs id -f '<id>')"
    host_swarm_connect "/ip4/${ip}/tcp/${IPFS_SWARM_PORT}/p2p/${peer}"
  done
else
  echo "Host IPFS daemon is not running; skipping host peering." >&2
fi

migration_ip="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${MIGRATION_CONTAINER}")"
migration_peer="$(docker exec "${MIGRATION_CONTAINER}" ipfs id -f '<id>')"
integration_ip="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${INTEGRATION_CONTAINER}")"
integration_peer="$(docker exec "${INTEGRATION_CONTAINER}" ipfs id -f '<id>')"

echo "Connecting migration and integration IPFS nodes..."
swarm_connect "${INTEGRATION_CONTAINER}" "/ip4/${migration_ip}/tcp/${IPFS_SWARM_PORT}/p2p/${migration_peer}"
swarm_connect "${MIGRATION_CONTAINER}" "/ip4/${integration_ip}/tcp/${IPFS_SWARM_PORT}/p2p/${integration_peer}"

echo "IPFS peering complete."
