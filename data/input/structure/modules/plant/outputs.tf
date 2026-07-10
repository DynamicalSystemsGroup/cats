output "kind_cluster_name" {
  value = kind_cluster.default.name
}

output "kubeconfig_context" {
  value = "kind-${kind_cluster.default.name}"
}

output "ray_release_name" {
  value = helm_release.ray-cluster.name
}
