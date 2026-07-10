variable "kubeconfig_path" {
  type        = string
  description = "Path to the kubeconfig file the kind cluster and Helm releases use."
}

variable "node_image" {
  type        = string
  default     = "kindest/node:v1.26.0"
  description = "Node image for the kind cluster."
}

variable "ray_image_tag" {
  type        = string
  default     = "2.9.0-aarch64"
  description = "Image tag for the ray-cluster Helm release."
}
