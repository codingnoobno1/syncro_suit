terraform {
  required_version = ">= 1.7.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}

locals {
  name_prefix = "${var.project_id}-${var.environment_id}"
  common_tags = {
    "aegis:managed"     = "true"
    "aegis:project"     = var.project_id
    "aegis:environment" = var.environment_id
    "aegis:ephemeral"   = tostring(var.ephemeral)
    "aegis:ttl_hours"   = tostring(var.ttl_hours)
    "aegis:owner"       = var.owner_email
  }
}

resource "azurerm_resource_group" "env" {
  name     = "rg-aegis-${local.name_prefix}"
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_log_analytics_workspace" "sec" {
  name                = "law-${local.name_prefix}"
  location            = azurerm_resource_group.env.location
  resource_group_name = azurerm_resource_group.env.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}

module "network" {
  source              = "../../modules/network"
  name_prefix         = local.name_prefix
  location            = azurerm_resource_group.env.location
  resource_group_name = azurerm_resource_group.env.name
  tags                = local.common_tags
}

module "keyvault" {
  source              = "../../modules/keyvault"
  name_prefix         = local.name_prefix
  location            = azurerm_resource_group.env.location
  resource_group_name = azurerm_resource_group.env.name
  tenant_id           = var.tenant_id
  allowed_subnet_ids  = [module.network.aks_subnet_id]
  tags                = local.common_tags
}

module "acr" {
  source              = "../../modules/acr"
  name_prefix         = local.name_prefix
  location            = azurerm_resource_group.env.location
  resource_group_name = azurerm_resource_group.env.name
  tags                = local.common_tags
}

module "aks" {
  source                     = "../../modules/aks"
  name_prefix                = local.name_prefix
  location                   = azurerm_resource_group.env.location
  resource_group_name        = azurerm_resource_group.env.name
  vnet_subnet_id             = module.network.aks_subnet_id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.sec.id
  node_count                 = var.node_count
  tags                       = local.common_tags
}
