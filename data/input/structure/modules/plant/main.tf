terraform {
  required_providers {
    kind = {
      source  = "tehcyx/kind"
      version = "0.5.1"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "2.15.0"
    }
  }
}

resource "kind_cluster" "default" {
  name            = "cats"
  kubeconfig_path = var.kubeconfig_path
  node_image      = var.node_image
  wait_for_ready  = "true"
}

resource "helm_release" "kuberay-operator" {
  name          = "kuberay-operator"
  repository    = "https://ray-project.github.io/kuberay-helm/"
  chart         = "kuberay-operator"
  version       = "1.1.1"
  wait_for_jobs = "true"
  depends_on = [
    kind_cluster.default
  ]
}

resource "helm_release" "ray-cluster" {
  name          = "raycluster"
  repository    = "https://ray-project.github.io/kuberay-helm/"
  chart         = "ray-cluster"
  version       = "1.1.1"
  wait_for_jobs = "true"
  set {
    name  = "image.tag"
    value = var.ray_image_tag
    type  = "string"
  }
  depends_on = [
    kind_cluster.default,
    helm_release.kuberay-operator
  ]
}
