# install
# SDKs: cod

terraform {
  required_providers {
    shell = {
      source  = "scottwinkler/shell"
      version = "1.7.10"
    }
    kind = {
      source  = "tehcyx/kind"
      version = "0.5.1"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "2.15.0"
    }
    docker = {
      source  = "kreuzwerker/docker"
      version = "3.0.2"
    }
    local = {}
  }
}

locals {
  #  KUBE_CONFIG_PATH = pathexpand(var.KUBE_CONFIG_PATH)
  k8s_config_path = pathexpand("~/.kube/config")
  docker_host     = pathexpand("unix:///var/run/docker.sock")
}

provider "shell" {
  sensitive_environment = {
    KUBE_CONFIG_PATH = local.k8s_config_path
  }
  interpreter        = ["/bin/sh", "-c"]
  enable_parallelism = false
}

provider "docker" {
  host = local.docker_host
}

provider "kind" {
  # Configuration options
}

provider "helm" {
  kubernetes {
    config_context_cluster = "kind-cats"
    config_path            = local.k8s_config_path
  }
}

# InfraStructure (IaaS): supports the provisioning of dynamically scaled
# infrastructure for maintaining a Plant - the IPFS/Docker transport layer
# used to move content-addressed data in and out of the Plant.
module "infrastructure" {
  source = "./modules/infrastructure"
}

# Plant (SaaS): the dynamically scaled execution environment of Function
# (FaaS) - the kind cluster plus the Helm releases (KubeRay + Ray cluster)
# that actually run CAT Processes.
module "plant" {
  source = "./modules/plant"

  kubeconfig_path = local.k8s_config_path

  # module.plant declares its own local "kubernetes" provider config (so it
  # can be deferred until kind_cluster.default is created - see its
  # main.tf), which makes it a "legacy module" that Terraform forbids
  # calling with depends_on. Threading this otherwise-unused output through
  # as an input variable creates the same ordering via normal data-flow
  # dependency instead.
  infrastructure_ready = module.infrastructure.docker_compose_ipfs_transport_id
}

# module.infrastructure's MinIO publishes its S3 port straight to the
# host; Ray pods reach it via the kind Docker network's gateway IP
# through ordinary pod egress routing (verified empirically against a
# live cluster: a raw TCP connect from inside a Ray pod to that gateway
# on an arbitrary port returned ECONNREFUSED, not a routing failure - the
# packet reached the Docker host), not through any in-cluster Service.
# That gateway only exists once module.plant has created the "kind"
# network, so depends_on defers this data source even though it
# references no attribute of module.plant directly.
data "docker_network" "kind" {
  name       = "kind"
  depends_on = [module.plant]
}

# Preserves existing Terraform state (no destroy/recreate) for anyone who
# already applied this Structure before it was split into modules.
moved {
  from = shell_script.host_ipfs_daemon
  to   = module.infrastructure.shell_script.host_ipfs_daemon
}

moved {
  from = shell_script.docker_compose_ipfs_transport
  to   = module.infrastructure.shell_script.docker_compose_ipfs_transport
}

moved {
  from = kind_cluster.default
  to   = module.plant.kind_cluster.default
}

moved {
  from = helm_release.kuberay-operator
  to   = module.plant.helm_release.kuberay-operator
}

moved {
  from = helm_release.ray-cluster
  to   = module.plant.helm_release.ray-cluster
}
