terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(var.tags, { Name = "vpc-${var.name_prefix}" })
}

resource "aws_subnet" "private_a" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.private_subnet_cidr
  map_public_ip_on_launch = false
  tags                    = merge(var.tags, { Name = "snet-${var.name_prefix}-priv-a" })
}

resource "aws_security_group" "hardened_compute" {
  name        = "sg-${var.name_prefix}-compute"
  description = "Zero-trust SG: deny internet SSH/RDP, allow HTTPS from corporate CIDR"
  vpc_id      = aws_vpc.this.id
  tags        = var.tags

  ingress {
    description = "HTTPS from corporate range"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.allowed_https_cidr]
  }

  egress {
    description = "Outbound HTTPS for SSM and package mirrors"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

variable "name_prefix" { type = string }
variable "vpc_cidr" {
  type    = string
  default = "10.50.0.0/16"
}
variable "private_subnet_cidr" {
  type    = string
  default = "10.50.1.0/24"
}
variable "allowed_https_cidr" {
  type    = string
  default = "10.0.0.0/8"
}
variable "tags" {
  type    = map(string)
  default = {}
}

output "vpc_id" { value = aws_vpc.this.id }
output "private_subnet_id" { value = aws_subnet.private_a.id }
output "security_group_id" { value = aws_security_group.hardened_compute.id }
