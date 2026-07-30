output "docker_compose_ipfs_transport_id" {
  description = "Identifier of the shell_script resource that brings up the IPFS transport containers; used by module.plant's depends_on to sequence after this module."
  value       = shell_script.docker_compose_ipfs_transport.id
}

# --- Scratch MinIO (Structure lifetime) ---

output "minio_scratch_endpoint_host" {
  description = "Scratch MinIO S3 API on the host."
  value       = "http://127.0.0.1:9000"
  depends_on  = [shell_script.docker_compose_minio_scratch]
}

output "minio_scratch_bucket" {
  value = local.minio_scratch_bucket
}

output "minio_scratch_access_key" {
  value     = local.minio_scratch_root_user
  sensitive = true
}

output "minio_scratch_secret_key" {
  value     = local.minio_scratch_root_password
  sensitive = true
}

# --- Durable Entity Relationship MinIO (Node lifetime) ---

output "minio_durable_endpoint_host" {
  description = "Durable Entity Relationship MinIO S3 API on the host."
  value       = "http://127.0.0.1:9100"
  depends_on  = [shell_script.docker_compose_minio_durable]
}

output "minio_durable_bucket" {
  value = local.minio_durable_bucket
}

output "minio_durable_access_key" {
  value     = local.minio_durable_root_user
  sensitive = true
}

output "minio_durable_secret_key" {
  value     = local.minio_durable_root_password
  sensitive = true
}
