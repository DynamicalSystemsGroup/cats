variable "kubeconfig_path" {
  type        = string
  description = "Path to the kubeconfig file the kind cluster and Helm releases use."
}

variable "infrastructure_ready" {
  type        = string
  default     = null
  description = "Unused except to force this module to sequence after module.infrastructure via ordinary data-flow (this module can't use depends_on - see the local kubernetes provider config in main.tf)."
}

variable "node_image" {
  type        = string
  default     = "kindest/node:v1.26.0"
  description = "Node image for the kind cluster."
}

variable "ray_image_tag" {
  type        = string
  # Must match the `ray` version/Python version pinned for this repo (see
  # pyproject.toml) - InfraFunction's Ray Job Submission Client (running
  # locally, at that pinned version) talks directly to this cluster, and
  # cloudpickle's cross-Python-version support is unreliable, so a
  # mismatch here surfaces as opaque (de)serialization errors.
  default     = "2.56.0-py312-aarch64"
  description = "Image tag for the ray-cluster Helm release."
}
