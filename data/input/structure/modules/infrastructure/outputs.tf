output "docker_compose_ipfs_transport_id" {
  description = "Identifier of the shell_script resource that brings up the IPFS transport containers; used by module.plant's depends_on to sequence after this module."
  value       = shell_script.docker_compose_ipfs_transport.id
}

output "minio_endpoint_host" {
  # Static: docker-compose publishes MinIO's S3 API port straight to the
  # host, at a fixed port, regardless of how the container itself is
  # scheduled.
  value      = "http://127.0.0.1:9000"
  depends_on = [shell_script.docker_compose_minio]
}

output "minio_bucket" {
  value = local.minio_bucket
}

output "minio_access_key" {
  value     = local.minio_root_user
  sensitive = true
}

output "minio_secret_key" {
  value     = local.minio_root_password
  sensitive = true
}
