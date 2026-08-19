terraform {
  required_providers {
    shell = {
      source  = "scottwinkler/shell"
      version = "1.7.10"
    }
  }
}

locals {
  # Pinned so Docker Compose names stay stable for MinIO facets.
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

# Scratch MinIO (Structure lifetime): Ray job landing destined for CAS/egress.
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
