resource "aws_kms_key" "ebs" {
  description             = "CMEK for AegisOps EC2 EBS volumes (${var.name_prefix})"
  deletion_window_in_days = 14
  enable_key_rotation     = true
  tags                    = var.tags
}

resource "aws_instance" "hardened_vm" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [var.security_group_id]
  associate_public_ip_address = false
  ebs_optimized               = true
  monitoring                  = true
  disable_api_termination     = var.disable_api_termination

  # Enforce IMDSv2 strictly (CIS AWS 5.6 / Checkov CKV_AWS_79)
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true
    kms_key_id            = aws_kms_key.ebs.arn
    delete_on_termination = true
  }

  enclave_options {
    enabled = var.enable_nitro_enclave
  }

  tags = merge(var.tags, {
    Name              = "ec2-${var.name_prefix}"
    "aegis:vm_sku"    = var.instance_type
    "aegis:imds"      = "v2-required"
  })
}

variable "name_prefix" { type = string }
variable "ami_id" {
  type    = string
  default = "ami-0c7217cdde317cfec"
}
variable "instance_type" {
  type    = string
  default = "m7i.xlarge"
}
variable "subnet_id" { type = string }
variable "security_group_id" { type = string }
variable "root_volume_gb" {
  type    = number
  default = 50
}
variable "enable_nitro_enclave" {
  type    = bool
  default = false
}
variable "disable_api_termination" {
  type    = bool
  default = false
}
variable "tags" {
  type    = map(string)
  default = {}
}

output "instance_id" { value = aws_instance.hardened_vm.id }
output "kms_key_arn" { value = aws_kms_key.ebs.arn }
