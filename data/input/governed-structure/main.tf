terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.49.1"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "2.31.0"
    }
  }
}

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

variable "project" {
  type = string
}

variable "region" {
  type = string
}

variable "zone" {
  type = string
}

variable "machine_type" {
  type = string
}

variable "boot_image" {
  type = string
}

variable "executor_image" {
  type = string
}

provider "google" {
  project = var.project
  region  = var.region
  zone    = var.zone
}

provider "kubernetes" {}

module "infrastructure" {
  source       = "./infrastructure"
  case         = var.case
  act          = var.act
  execution    = var.execution
  expires_at   = var.expires_at
  machine_type = var.machine_type
  boot_image   = var.boot_image
}

module "plant" {
  source         = "./plant"
  case           = var.case
  act            = var.act
  execution      = var.execution
  expires_at     = var.expires_at
  executor_image = var.executor_image
}
