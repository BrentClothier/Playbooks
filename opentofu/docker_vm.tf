module "docker_vm" {
  source = "./modules/vm"

  template_name = var.template_name

  hostname = "docker-vm01"
  node     = var.pve_node
  storage  = var.storage

  cores     = 4
  memory    = 8192
  disk_size = "100G"

  net_bridge = "vmbr0"
  vlan_tag   = 0

  ssh_public_keys = var.ssh_public_keys
  ciuser          = "root"
  ipconfig0       = "ip=192.168.86.172/24,gw=192.168.86.1"

  # Uncomment and adjust if you want a fixed Proxmox VMID.
  # vmid = 172
}
