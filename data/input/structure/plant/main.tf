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
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "2.31.0"
    }
  }
}

resource "kind_cluster" "default" {
  name            = "cats"
  kubeconfig_path = var.kubeconfig_path
  node_image      = var.node_image
  wait_for_ready  = "true"

  # Statically maps the Ray dashboard's NodePort (below) to a fixed host
  # port, so InfraFunction can dispatch Ray jobs at a known, unchanging
  # address (http://127.0.0.1:8265) instead of one only discoverable after
  # the NodePort is allocated.
  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"

      extra_port_mappings {
        container_port = 30265
        host_port      = 8265
      }
    }
  }
}

# Configured from kind_cluster.default's own (computed) credentials rather
# than a static kubeconfig context. redeploy() destroys and recreates this
# whole module on every Order, which removes and re-adds the "kind-cats"
# kubeconfig context in the same terraform apply - a provider configured by
# static config_path/config_context fails plan-time validation because that
# context doesn't exist yet at plan time. Sourcing it from the resource's
# own attributes instead makes the config "known after apply", so Terraform
# defers this provider (and kubernetes_service.ray_dashboard_nodeport below)
# until kind_cluster.default has actually been created.
provider "kubernetes" {
  host                   = kind_cluster.default.endpoint
  client_certificate     = kind_cluster.default.client_certificate
  client_key             = kind_cluster.default.client_key
  cluster_ca_certificate = kind_cluster.default.cluster_ca_certificate
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
  set {
    # Dashboard binds to localhost inside the head pod by default; without
    # this it's unreachable through the NodePort Service below.
    name  = "head.rayStartParams.dashboard-host"
    value = "0.0.0.0"
    type  = "string"
  }
  set {
    # Chart default is 2G, which only leaves a sliver of headroom once
    # GCS/dashboard/autoscaler/log-monitor overhead (~1.1G) and a job's own
    # driver/actors are accounted for - observed tipping into OOM-kills
    # under InfraFunction's Ray Job dispatch even for small datasets.
    name  = "head.resources.limits.memory"
    value = "3G"
    type  = "string"
  }
  set {
    name  = "head.resources.requests.memory"
    value = "3G"
    type  = "string"
  }
  depends_on = [
    kind_cluster.default,
    helm_release.kuberay-operator
  ]
}

# Exposes the Ray head pod's dashboard (used for Ray Job Submission by
# InfraFunction - see cats/executor/function) on a fixed NodePort, which
# kind_cluster.default's extra_port_mappings maps to a static host port.
# A dedicated Service (rather than the chart's own head service) lets us
# pin an exact node_port instead of accepting Kubernetes' random
# allocation from the NodePort range, which the static extraPortMappings
# above requires knowing in advance.
resource "kubernetes_service" "ray_dashboard_nodeport" {
  metadata {
    name = "raycluster-dashboard-nodeport"
  }
  spec {
    type = "NodePort"
    selector = {
      "app.kubernetes.io/created-by" = "kuberay-operator"
      # The ray-cluster chart names the underlying RayCluster (and thus
      # this label's value) "<release name>-kuberay", not the bare
      # release name - confirmed via `kubectl get rayclusters.ray.io`.
      "ray.io/cluster"   = "${helm_release.ray-cluster.name}-kuberay"
      "ray.io/node-type" = "head"
    }
    port {
      name        = "dashboard"
      port        = 8265
      target_port = 8265
      node_port   = 30265
      protocol    = "TCP"
    }
  }
  depends_on = [
    helm_release.ray-cluster
  ]
}
