terraform {
  required_providers {
    shell = {
      source  = "scottwinkler/shell"
      version = "1.7.10"
    }
  }
}

locals {
  ipfs_transport_compose   = "${path.module}/ipfs_transport_compose.yaml"
  host_ipfs_daemon_pidfile = "${path.module}/.host-ipfs-daemon.pid"
  host_ipfs_daemon_logfile = "${path.module}/.host-ipfs-daemon.log"
  # Pinned so container names (and ipfs_connect_peers.sh's defaults) stay
  # "structure-ipfs_migration-1"/"structure-ipfs_integration-1" regardless of
  # which module directory the compose file lives in.
  compose_project_name = "structure"
}

resource "shell_script" "host_ipfs_daemon" {
  # Idempotent: probes with `ipfs id` (the daemon's live API) rather than
  # the repo.lock file, since a stale lock can outlive a crashed daemon.
  # Only starts `ipfs daemon` - and only ever kills it again on destroy -
  # when this resource is the one that started it, so a daemon already
  # running from outside Terraform is never disturbed and never hit with
  # a second `ipfs daemon` (which would fail with "someone else has the
  # lock").
  lifecycle_commands {
    create = <<-EOF
      #!/bin/bash
      set -e
      if ipfs id >/dev/null 2>&1; then
        echo "Host IPFS daemon already running; not starting another one."
        exit 0
      fi
      nohup ipfs daemon >"${local.host_ipfs_daemon_logfile}" 2>&1 &
      echo $! > "${local.host_ipfs_daemon_pidfile}"
      for i in $(seq 1 30); do
        ipfs id >/dev/null 2>&1 && exit 0
        sleep 1
      done
      echo "Timed out waiting for host IPFS daemon to become ready" >&2
      exit 1
    EOF
    delete = <<-EOF
      #!/bin/bash
      if [ -f "${local.host_ipfs_daemon_pidfile}" ]; then
        kill "$(cat "${local.host_ipfs_daemon_pidfile}")" 2>/dev/null || true
        rm -f "${local.host_ipfs_daemon_pidfile}"
      fi
    EOF
  }
}

resource "shell_script" "docker_compose_ipfs_transport" {
  lifecycle_commands {
    create = <<-EOF
      #!/bin/bash
      set -e
      mkdir -p "$INTEGRATION_INPUT_DATA_CACHE"
      export INTEGRATION_INPUT_DATA_CACHE="$(cd "$INTEGRATION_INPUT_DATA_CACHE" && pwd)"
      docker-compose -p ${local.compose_project_name} -f ${local.ipfs_transport_compose} up --scale ipfs_migration=1 --scale ipfs_integration=1 -d --wait
      bash ${path.module}/ipfs_connect_peers.sh
    EOF
    delete = <<-EOF
      #!/bin/bash
      docker-compose -p ${local.compose_project_name} -f ${local.ipfs_transport_compose} down || true
    EOF
  }
  depends_on = [
    shell_script.host_ipfs_daemon
  ]
}
