resource "azurerm_network_interface" "vm" {
  name                = "nic-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.subnet_id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "hardened" {
  name                            = "vm-${var.name_prefix}"
  resource_group_name             = var.resource_group_name
  location                        = var.location
  size                            = var.vm_size
  admin_username                  = "aegisadmin"
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.vm.id]
  secure_boot_enabled             = true
  vtpm_enabled                    = true
  encryption_at_host_enabled      = true
  tags                            = merge(var.tags, { "aegis:vm_sku" = var.vm_size })

  admin_ssh_key {
    username   = "aegisadmin"
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    security_encryption_type = var.confidential_compute ? "VMGuestStateOnly" : null
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  identity {
    type = "SystemAssigned"
  }
}

variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "subnet_id" { type = string }
variable "vm_size" {
  type    = string
  default = "Standard_DC4as_v5"
}
variable "ssh_public_key" {
  type    = string
  default = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAegisOpsPlaceholderKeyForPlanOnly aegis@aegisops.dev"
}
variable "confidential_compute" {
  type    = bool
  default = true
}
variable "tags" {
  type    = map(string)
  default = {}
}

output "vm_id" { value = azurerm_linux_virtual_machine.hardened.id }
output "vm_name" { value = azurerm_linux_virtual_machine.hardened.name }
