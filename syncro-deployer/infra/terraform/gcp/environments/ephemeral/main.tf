terraform {
  required_version = ">= 1.7.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.region
}

locals {
  name_prefix = "${var.project_id}-${var.environment_id}"
  common_labels = {
    aegis_managed     = "true"
    aegis_cloud       = "gcp"
    aegis_project     = replace(var.project_id, "_", "-")
    aegis_environment = replace(var.environment_id, "_", "-")
    aegis_ephemeral   = tostring(var.ephemeral)
    aegis_ttl_hours   = tostring(var.ttl_hours)
  }
}

module "vpc" {
  source      = "../../modules/vpc"
  name_prefix = local.name_prefix
  region      = var.region
}

module "gce" {
  source                      = "../../modules/gce_shielded"
  name_prefix                 = local.name_prefix
  region                      = var.region
  machine_type                = var.machine_type
  subnetwork_id               = module.vpc.subnetwork_id
  enable_confidential_compute = var.enable_confidential_compute
  spot_enabled                = var.spot_enabled
  labels                      = local.common_labels
}

resource "google_storage_bucket" "artifacts" {
  name                        = "aegis-gcs-${local.name_prefix}"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.ephemeral
  labels                      = local.common_labels
}

variable "gcp_project_id" {
  type    = string
  default = "aegisops-devsecops-sim"
}
variable "project_id" {
  type    = string
  default = "ai-inference"
}
variable "environment_id" {
  type    = string
  default = "pr-608-gcp"
}
variable "region" {
  type    = string
  default = "us-central1"
}
variable "machine_type" {
  type    = string
  default = "n2d-standard-4"
}
variable "enable_confidential_compute" {
  type    = bool
  default = true
}
variable "spot_enabled" {
  type    = bool
  default = false
}
variable "ephemeral" {
  type    = bool
  default = true
}
variable "ttl_hours" {
  type    = number
  default = 4
}

output "network_id" { value = module.vpc.network_id }
output "instance_name" { value = module.gce.instance_name }
output "gcs_bucket" { value = google_storage_bucket.artifacts.name }
