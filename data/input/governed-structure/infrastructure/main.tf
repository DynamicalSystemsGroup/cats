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

variable "machine_type" {
  type = string
}

variable "boot_image" {
  type = string
}

resource "google_compute_instance" "machine" {
  name         = var.execution
  machine_type = var.machine_type

  boot_disk {
    initialize_params {
      image = var.boot_image
    }
  }

  network_interface {
    network = "default"
  }

  scheduling {
    automatic_restart           = false
    instance_termination_action = "DELETE"
    termination_time            = var.expires_at
  }

  metadata = {
    case       = var.case
    act        = var.act
    execution  = var.execution
    expires_at = var.expires_at
  }
}
