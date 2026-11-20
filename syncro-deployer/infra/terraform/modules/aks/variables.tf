variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "vnet_subnet_id" { type = string }
variable "log_analytics_workspace_id" { type = string }
variable "kubernetes_version" {
  type    = string
  default = "1.30"
}
variable "node_vm_size" {
  type    = string
  default = "Standard_D4s_v5"
}
variable "node_count" {
  type    = number
  default = 2
}
variable "private_cluster_enabled" {
  type    = bool
  default = true
}
variable "tags" {
  type    = map(string)
  default = {}
}

output "aks_id" { value = azurerm_kubernetes_cluster.this.id }
output "aks_name" { value = azurerm_kubernetes_cluster.this.name }
output "oidc_issuer_url" { value = azurerm_kubernetes_cluster.this.oidc_issuer_url }
output "kubelet_identity_object_id" { value = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id }
