terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  name_prefix = "${var.project_id}-${var.environment_id}"
  common_tags = {
    "aegis:managed"     = "true"
    "aegis:cloud"       = "aws"
    "aegis:project"     = var.project_id
    "aegis:environment" = var.environment_id
    "aegis:ephemeral"   = tostring(var.ephemeral)
    "aegis:ttl_hours"   = tostring(var.ttl_hours)
  }
}

module "vpc" {
  source      = "../../modules/vpc"
  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "ec2" {
  source               = "../../modules/ec2_hardened"
  name_prefix          = local.name_prefix
  instance_type        = var.instance_type
  subnet_id            = module.vpc.private_subnet_id
  security_group_id    = module.vpc.security_group_id
  enable_nitro_enclave = var.enable_confidential_compute
  tags                 = local.common_tags
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = "aegis-artifacts-${local.name_prefix}"
  force_destroy = var.ephemeral
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = module.ec2.kms_key_arn
    }
  }
}

variable "project_id" {
  type    = string
  default = "edge-gateway"
}
variable "environment_id" {
  type    = string
  default = "pr-501-aws"
}
variable "region" {
  type    = string
  default = "us-east-1"
}
variable "instance_type" {
  type    = string
  default = "m7i.xlarge"
}
variable "enable_confidential_compute" {
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

output "vpc_id" { value = module.vpc.vpc_id }
output "instance_id" { value = module.ec2.instance_id }
output "s3_bucket" { value = aws_s3_bucket.artifacts.id }
