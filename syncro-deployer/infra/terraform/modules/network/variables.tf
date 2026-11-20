variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "vnet_cidr" {
  type    = string
  default = "10.40.0.0/16"
}
variable "aks_subnet_cidr" {
  type    = string
  default = "10.40.1.0/24"
}
variable "pe_subnet_cidr" {
  type    = string
  default = "10.40.2.0/24"
}
variable "allowed_https_cidr" {
  type    = string
  default = "10.0.0.0/8"
}
variable "tags" {
  type    = map(string)
  default = {}
}

output "vnet_id" { value = azurerm_virtual_network.this.id }
output "aks_subnet_id" { value = azurerm_subnet.aks.id }
output "private_endpoints_subnet_id" { value = azurerm_subnet.private_endpoints.id }
