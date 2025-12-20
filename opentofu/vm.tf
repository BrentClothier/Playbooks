module "homeassistant_vm" {
  source = "./modules/vm"

  hostname      = "ha-vm01"
  node          = var.pve_node
  cores         = 2
  memory        = 4096
  disk_size     = "32G"
  storage       = var.storage
  net_bridge    = "vmbr0"

  template_vmid = "ubuntu-2404-cloud-template"
}
