module "humboldt_data_vm" {
  source = "../modules/vm"

  template_name = var.template_name

  hostname = "humboldt-data01"
  node     = "proxmox2"
  storage  = "USB_Storage_Space"

  cores     = 4
  memory    = 6144
  disk_size = "80G"

  net_bridge = "vmbr0"
  vlan_tag   = 0

  ssh_public_keys = var.ssh_public_keys
  ciuser          = "root"
  ipconfig0       = "ip=192.168.86.173/24,gw=192.168.86.1"
}
