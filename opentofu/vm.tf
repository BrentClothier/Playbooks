module "homeassistant_vm" {
  source = "./modules/vm"

template_name = var.template_name


  hostname   = "ha-vm01"
  node       = var.pve_node
  storage    = var.storage

  # inject keys
  ssh_public_keys = var.ct_ssh_public_keys

  # static IP via cloud-init
  ipconfig0 = "ip=192.168.86.170/24,gw=192.168.86.1"

  # if you want to force an ID:
  vmid = var.vmid
}
