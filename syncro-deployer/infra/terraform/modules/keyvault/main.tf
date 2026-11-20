resource "azurerm_key_vault" "this" {
  name                          = "kv-${substr(replace(var.name_prefix, "-", ""), 0, 18)}"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  tenant_id                     = var.tenant_id
  sku_name                      = "premium"
  enable_rbac_authorization     = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  public_network_access_enabled = false
  tags                          = var.tags

  network_acls {
    default_action             = "Deny"
    bypass                     = "AzureServices"
    virtual_network_subnet_ids = var.allowed_subnet_ids
  }
}

variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "tenant_id" { type = string }
variable "allowed_subnet_ids" {
  type    = list(string)
  default = []
}
variable "tags" {
  type    = map(string)
  default = {}
}

output "key_vault_id" { value = azurerm_key_vault.this.id }
output "key_vault_uri" { value = azurerm_key_vault.this.vault_uri }
