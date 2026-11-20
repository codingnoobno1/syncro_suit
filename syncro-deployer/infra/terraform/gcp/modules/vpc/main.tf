terraform {
  required_version = ">= 1.7.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

resource "google_compute_network" "this" {
  name                    = "vpc-${var.name_prefix}"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "private" {
  name                     = "snet-${var.name_prefix}-priv"
  ip_cidr_range            = var.subnet_cidr
  region                   = var.region
  network                  = google_compute_network.this.id
  private_ip_google_access = true
}

resource "google_compute_firewall" "allow_iap_ssh" {
  name    = "fw-${var.name_prefix}-iap-ssh"
  network = google_compute_network.this.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # Identity-Aware Proxy (IAP) range only — never 0.0.0.0/0
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["aegis-hardened"]
}

variable "name_prefix" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "subnet_cidr" {
  type    = string
  default = "10.60.1.0/24"
}

output "network_id" { value = google_compute_network.this.id }
output "subnetwork_id" { value = google_compute_subnetwork.private.id }
