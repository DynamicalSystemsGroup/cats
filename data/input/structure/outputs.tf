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

output "infrastructure_minio_endpoint_host" {
  value = module.infrastructure.minio_endpoint_host
}

output "infrastructure_minio_endpoint_pod" {
  # Ray pods reach module.infrastructure's MinIO not via any in-cluster
  # Service, but via ordinary pod egress routing to the kind Docker
  # network's gateway IP - see data.docker_network.kind in main.tf.
  # ipam_config has one entry per IP family (kind's network is dual-stack);
  # filter for the IPv4 gateway specifically since IPv6 ones contain ":".
  value = "http://${[
    for cfg in data.docker_network.kind.ipam_config : cfg.gateway
    if !strcontains(cfg.gateway, ":")
  ][0]}:9000"
}

output "infrastructure_minio_bucket" {
  value = module.infrastructure.minio_bucket
}

output "infrastructure_minio_access_key" {
  value     = module.infrastructure.minio_access_key
  sensitive = true
}

output "infrastructure_minio_secret_key" {
  value     = module.infrastructure.minio_secret_key
  sensitive = true
}
