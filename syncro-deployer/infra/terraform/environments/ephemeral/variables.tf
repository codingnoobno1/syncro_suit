variable "project_id" {
  type    = string
  default = "payments-api"
}

variable "environment_id" {
  type    = string
  default = "pr-412"
}

variable "location" {
  type    = string
  default = "eastus2"
}

variable "tenant_id" {
  type    = string
  default = "00000000-0000-0000-0000-000000000000"
}

variable "ephemeral" {
  type    = bool
  default = true
}

variable "ttl_hours" {
  type    = number
  default = 4
}

variable "owner_email" {
  type    = string
  default = "platform-sec@aegisops.dev"
}

variable "node_count" {
  type    = number
  default = 2
}

output "resource_group_name" { value = azurerm_resource_group.env.name }
output "aks_cluster_name" { value = module.aks.aks_name }
output "key_vault_uri" { value = module.keyvault.key_vault_uri }
output "acr_login_server" { value = module.acr.acr_login_server }
