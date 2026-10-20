variable "case" {
  type = string
}

variable "act" {
  type = string
}

variable "execution" {
  type = string
}

variable "expires_at" {
  type = string
}

variable "executor_image" {
  type = string
}

resource "kubernetes_job_v1" "executor" {
  metadata {
    name = var.execution
    labels = {
      case      = var.case
      act       = var.act
      execution = var.execution
    }
  }

  spec {
    backoff_limit = 0

    template {
      metadata {
        labels = {
          execution = var.execution
        }
      }

      spec {
        restart_policy = "Never"

        container {
          name  = "executor"
          image = var.executor_image

          env {
            name  = "CASE"
            value = var.case
          }

          env {
            name  = "ACT"
            value = var.act
          }

          env {
            name  = "EXECUTION"
            value = var.execution
          }

          env {
            name  = "EXPIRES_AT"
            value = var.expires_at
          }
        }
      }
    }
  }
}
