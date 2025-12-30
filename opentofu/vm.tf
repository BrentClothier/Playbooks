module "homeassistant_vm" {
  source = "./modules/vm"

  hostname   = "ha-vm01"
  node       = var.pve_node
  cores      = 2
  memory     = 4096
  disk_size  = "32G"
  storage    = var.storage
  net_bridge = "vmbr0"

  # VMID of the template (you said it's 114)
  template_vmid = 114

  # must be list(string)
  ssh_public_keys = var.ssh_public_keys

  ipconfig0 = "ip=192.168.86.170/24,gw=192.168.86.1"

  usb0 = "host=1-7"
}
