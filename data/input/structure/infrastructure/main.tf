terraform {
  required_providers {
    shell = {
      source  = "scottwinkler/shell"
      version = "1.7.10"
    }
  }
}

locals {
  ipfs_transport_compose = "${path.module}/ipfs_transport_compose.yaml"
  # Legacy pidfile from older create scripts that started Kubo via nohup;
  # delete only removes the file — never kills host Kubo (content-store facet).
  host_ipfs_daemon_pidfile = "${path.module}/.host-ipfs-daemon.pid"
  content_store_utils = "${path.module}/content_store_utils.py"
  transport_utils     = "${path.module}/transport_utils.py"
  # infrastructure/ → … → repo root (four levels up).
  cats_repo_root = "${path.module}/../../../.."
  # Pinned so Docker Compose names stay
  # "structure-ipfs_migration-1"/"structure-ipfs_integration-1" (matches
  # TransportContext defaults in transport_utils.py) regardless of which
  # module directory the compose file lives in.
  compose_project_name = "structure"

  # Scratch MinIO (Structure lifetime) — distinct from durable below.
  minio_scratch_compose        = "${path.module}/minio_scratch_compose.yaml"
  minio_scratch_bucket         = "cats-scratch"
  minio_scratch_root_user      = "cats-scratch"
  minio_scratch_root_password  = "cats-scratch-secret"
  # Fixed by compose project/service ("structure-minio_scratch-1").
  minio_scratch_container_name = "${local.compose_project_name}-minio_scratch-1"
  # Scratch ILM soft expire (Structure destroy down -v remains the hard floor).
  minio_scratch_expire_days = 7

  # Durable Entity Relationship MinIO (hard-isolated; Node lifetime).
  minio_durable_compose        = "${path.module}/minio_durable_compose.yaml"
  minio_durable_bucket         = "cats-durable"
  minio_durable_root_user      = "cats-durable"
  minio_durable_root_password  = "cats-durable-secret"
  minio_durable_container_name = "${local.compose_project_name}-minio_durable-1"
}

resource "shell_script" "host_ipfs_daemon" {
  # InfraStructure content-store facet: sole Order-submitted ContentStore.ensure
  # during Structure TF (à la carte; bare terraform apply can start host Kubo).
  # Executor InfraStructure.apply only asserts is_ready after apply — it does
  # not call ensure. Does not kill host Kubo on destroy — content store
  # outlives Structure T&D (Docker peers / MinIO) and Plant.
  lifecycle_commands {
    create = <<-EOF
      #!/bin/bash
      set -e
      REPO_ROOT="$(cd "${local.cats_repo_root}" && pwd)"
      SCRIPT="${local.content_store_utils}"
      if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
        "$REPO_ROOT/.venv/bin/python" "$SCRIPT" ensure
      elif command -v uv >/dev/null 2>&1; then
        (cd "$REPO_ROOT" && uv run python "$SCRIPT" ensure)
      else
        python3 "$SCRIPT" ensure
      fi
    EOF
    delete = <<-EOF
      #!/bin/bash
      # Content-store facet: leave host Kubo running for Order/BOM CIDs and
      # the next demo/Node session. Only clear a legacy pidfile if present.
      rm -f "${local.host_ipfs_daemon_pidfile}"
    EOF
  }
}

resource "shell_script" "docker_compose_ipfs_transport" {
  # T&D transport peer containers (create-once). Peering mutate is
  # shell_script.ipfs_transport_peering (every apply) — not Process heal.
  lifecycle_commands {
    create = <<-EOF
      #!/bin/bash
      set -e
      mkdir -p "$INTEGRATION_INPUT_DATA_CACHE"
      export INTEGRATION_INPUT_DATA_CACHE="$(cd "$INTEGRATION_INPUT_DATA_CACHE" && pwd)"
      docker-compose -p ${local.compose_project_name} -f ${local.ipfs_transport_compose} up --scale ipfs_migration=1 --scale ipfs_integration=1 -d --wait
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

resource "shell_script" "ipfs_transport_peering" {
  # Sole Order-submitted peering mutate (TransportContext.ensure_peered).
  # triggers.always = timestamp() ForceNews this resource every terraform apply
  # so swarm is healed every reconcile without recreating Compose.
  # Executor InfraStructure.apply only asserts assert_ready after apply.
  # terraform plan will always show this resource replacing — expected.
  triggers = {
    always = timestamp()
  }
  lifecycle_commands {
    create = <<-EOF
      #!/bin/bash
      set -e
      REPO_ROOT="$(cd "${local.cats_repo_root}" && pwd)"
      SCRIPT="${local.transport_utils}"
      if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
        "$REPO_ROOT/.venv/bin/python" "$SCRIPT" ensure-peered
      elif command -v uv >/dev/null 2>&1; then
        (cd "$REPO_ROOT" && uv run python "$SCRIPT" ensure-peered)
      else
        python3 "$SCRIPT" ensure-peered
      fi
    EOF
    delete = <<-EOF
      #!/bin/bash
      # Swarm links are ephemeral; do not tear down Compose peers.
      true
    EOF
  }
  depends_on = [
    shell_script.docker_compose_ipfs_transport
  ]
}

# Scratch MinIO (Structure lifetime): Ray job landing destined for IPFS.
# Published to the host at 127.0.0.1:9000; Ray pods reach it via the kind
# Docker network gateway (see root-level data.docker_network.kind).
resource "shell_script" "docker_compose_minio_scratch" {
  lifecycle_commands {
    create = <<-EOF
      #!/bin/bash
      set -e
      docker-compose -p ${local.compose_project_name} -f ${local.minio_scratch_compose} up -d --wait
      for i in $(seq 1 30); do
        curl -sf http://127.0.0.1:9000/minio/health/ready >/dev/null 2>&1 && break
        sleep 1
      done
      # MinIO's root user already works directly as an S3 access/secret
      # key pair. Bootstrap scratch bucket + ILM expire (soft); Structure
      # destroy down -v remains the hard floor for scratch only.
      # --network container:... attaches to the scratch container's own
      # network namespace, so 127.0.0.1 here resolves to that container
      # regardless of host networking support.
      docker run --rm --network container:${local.minio_scratch_container_name} --entrypoint /bin/sh minio/mc \
        -c "mc alias set local http://127.0.0.1:9000 ${local.minio_scratch_root_user} ${local.minio_scratch_root_password} && mc mb -p local/${local.minio_scratch_bucket} && (mc ilm rule add --expire-days ${local.minio_scratch_expire_days} local/${local.minio_scratch_bucket} || mc ilm add --expiry-days ${local.minio_scratch_expire_days} local/${local.minio_scratch_bucket} || true)"
    EOF
    delete = <<-EOF
      #!/bin/bash
      # -v removes structure_minio_scratch_data so Structure destroy clears
      # parallel-write scratch. Must not touch node_minio_durable_data.
      docker-compose -p ${local.compose_project_name} -f ${local.minio_scratch_compose} down -v || true
    EOF
  }
}

# Durable Entity Relationship MinIO (Node lifetime, hard-isolated).
# Structure destroy must not wipe the volume; leave the daemon up (or
# down without -v) so the next Structure reuses the corpus.
resource "shell_script" "docker_compose_minio_durable" {
  lifecycle_commands {
    create = <<-EOF
      #!/bin/bash
      set -e
      docker-compose -p ${local.compose_project_name} -f ${local.minio_durable_compose} up -d --wait
      for i in $(seq 1 30); do
        curl -sf http://127.0.0.1:9100/minio/health/ready >/dev/null 2>&1 && break
        sleep 1
      done
      docker run --rm --network container:${local.minio_durable_container_name} --entrypoint /bin/sh minio/mc \
        -c "mc alias set local http://127.0.0.1:9000 ${local.minio_durable_root_user} ${local.minio_durable_root_password} && mc mb -p local/${local.minio_durable_bucket}"
    EOF
    delete = <<-EOF
      #!/bin/bash
      # Node-lifetime: do not remove node_minio_durable_data. Leave the
      # durable daemon running so Entity Relationship data and er/current
      # pointers survive Structure destroy / redeploy (create is idempotent).
      true
    EOF
  }
}
