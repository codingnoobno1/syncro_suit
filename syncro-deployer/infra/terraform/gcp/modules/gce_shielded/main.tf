resource "google_compute_instance" "shielded_vm" {
  name         = "gce-${var.name_prefix}"
  machine_type = var.machine_type
  zone         = "${var.region}-a"
  tags         = ["aegis-hardened"]
  labels       = var.labels

  deletion_protection = var.deletion_protection

  boot_disk {
    initialize_params {
      image = var.image
      size  = var.boot_disk_gb
      type  = "pd-ssd"
    }
  }

  network_interface {
    subnetwork = var.subnetwork_id
    # No access_config block => strictly private IP (CIS GCP 4.9)
  }

  # Enforce Shielded VM with Secure Boot, vTPM, and Integrity Monitoring
  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  confidential_instance_config {
    enable_confidential_compute = var.enable_confidential_compute
  }

  metadata = {
    enable-oslogin         = "TRUE"
    block-project-ssh-keys = "TRUE"
  }

  scheduling {
    on_host_maintenance = var.enable_confidential_compute ? "TERMINATE" : "MIGRATE"
    preemptible         = var.spot_enabled
    provisioning_model  = var.spot_enabled ? "SPOT" : "STANDARD"
  }
}

variable "name_prefix" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "machine_type" {
  type    = string
  default = "n2d-standard-4"
}
variable "subnetwork_id" { type = string }
variable "image" {
  type    = string
  default = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
}
variable "boot_disk_gb" {
  type    = number
  default = 50
}
variable "enable_confidential_compute" {
  type    = bool
  default = true
}
variable "spot_enabled" {
  type    = bool
  default = false
}
variable "deletion_protection" {
  type    = bool
  default = false
}
variable "labels" {
  type    = map(string)
  default = {}
}

output "instance_id" { value = google_compute_instance.shielded_vm.id }
output "instance_name" { value = google_compute_instance.shielded_vm.name }
