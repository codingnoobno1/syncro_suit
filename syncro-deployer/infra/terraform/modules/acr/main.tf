resource "azurerm_container_registry" "this" {
  name                          = "acr${substr(replace(var.name_prefix, "-", ""), 0, 20)}"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  sku                           = "Premium"
  admin_enabled                 = false
  public_network_access_enabled = false
  quarantine_policy_enabled     = true
  trust_policy_enabled          = true
  retention_policy_in_days      = 14
  tags                          = var.tags
}

variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}

output "acr_id" { value = azurerm_container_registry.this.id }
output "acr_login_server" { value = azurerm_container_registry.this.login_server }
