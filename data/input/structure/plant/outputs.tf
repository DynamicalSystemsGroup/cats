output "kind_cluster_name" {
  value = kind_cluster.default.name
}

output "kubeconfig_context" {
  value = "kind-${kind_cluster.default.name}"
}

output "ray_release_name" {
  value = helm_release.ray-cluster.name
}

output "ray_dashboard_address" {
  # Static because kind_cluster.default's extra_port_mappings pins the
  # host side of the NodePort mapping regardless of which NodePort
  # Kubernetes/we assign on the cluster side.
  value = "http://127.0.0.1:8265"
}
