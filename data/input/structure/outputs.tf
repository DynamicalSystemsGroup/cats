output "plant_kind_cluster_name" {
  value = module.plant.kind_cluster_name
}

output "plant_kubeconfig_context" {
  value = module.plant.kubeconfig_context
}

output "plant_ray_release_name" {
  value = module.plant.ray_release_name
}

output "plant_ray_dashboard_address" {
  value = module.plant.ray_dashboard_address
}

# --- Scratch MinIO (Structure lifetime) ---

output "infrastructure_minio_scratch_endpoint_host" {
  value = module.infrastructure.minio_scratch_endpoint_host
}

output "infrastructure_minio_scratch_endpoint_pod" {
  # Ray pods reach scratch MinIO via the kind Docker network gateway —
  # see data.docker_network.kind in main.tf. Filter IPv4 gateway.
  value = "http://${[
    for cfg in data.docker_network.kind.ipam_config : cfg.gateway
    if !strcontains(cfg.gateway, ":")
  ][0]}:9000"
}

output "infrastructure_minio_scratch_bucket" {
  value = module.infrastructure.minio_scratch_bucket
}

output "infrastructure_minio_scratch_access_key" {
  value     = module.infrastructure.minio_scratch_access_key
  sensitive = true
}

output "infrastructure_minio_scratch_secret_key" {
  value     = module.infrastructure.minio_scratch_secret_key
  sensitive = true
}

# --- Durable Entity Relationship MinIO (Node lifetime) ---

output "infrastructure_minio_durable_endpoint_host" {
  value = module.infrastructure.minio_durable_endpoint_host
}

output "infrastructure_minio_durable_endpoint_pod" {
  # Durable Entity Relationship MinIO on the same kind gateway, port 9100.
  value = "http://${[
    for cfg in data.docker_network.kind.ipam_config : cfg.gateway
    if !strcontains(cfg.gateway, ":")
  ][0]}:9100"
}

output "infrastructure_minio_durable_bucket" {
  value = module.infrastructure.minio_durable_bucket
}

output "infrastructure_minio_durable_access_key" {
  value     = module.infrastructure.minio_durable_access_key
  sensitive = true
}

output "infrastructure_minio_durable_secret_key" {
  value     = module.infrastructure.minio_durable_secret_key
  sensitive = true
}
