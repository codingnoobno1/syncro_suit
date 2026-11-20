resource "azurerm_kubernetes_cluster" "this" {
  name                              = "aks-${var.name_prefix}"
  location                          = var.location
  resource_group_name               = var.resource_group_name
  dns_prefix                        = "aks-${var.name_prefix}"
  kubernetes_version                = var.kubernetes_version
  private_cluster_enabled           = var.private_cluster_enabled
  oidc_issuer_enabled               = true
  workload_identity_enabled         = true
  role_based_access_control_enabled = true
  local_account_disabled            = true
  azure_policy_enabled              = true
  tags                              = var.tags

  default_node_pool {
    name                        = "system"
    vm_size                     = var.node_vm_size
    node_count                  = var.node_count
    vnet_subnet_id              = var.vnet_subnet_id
    os_disk_type                = "Ephemeral"
    only_critical_addons_enabled = false
    temporary_name_for_rotation = "sysrot"
  }

  identity {
    type = "SystemAssigned"
  }

  azure_active_directory_role_based_access_control {
    azure_rbac_enabled = true
  }

  network_profile {
    network_plugin      = "azure"
    network_policy      = "cilium"
    network_data_plane  = "cilium"
    outbound_type       = "loadBalancer"
  }

  microsoft_defender {
    log_analytics_workspace_id = var.log_analytics_workspace_id
  }
}
