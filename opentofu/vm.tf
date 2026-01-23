module "homeassistant_vm" {
  source = "./modules/vm"

template_name = var.template_name

hostname = "ha-vm01"
node     = var.pve_node
storage  = var.storage

cores     = 2
memory    = 4096
disk_size = "32G"

net_bridge = "vmbr0"

  # IMPORTANT:
  # If your LAN is untagged, set this to 0.
  # If you truly need VLAN 1 tagging, set to 1.
vlan_tag = 0

ssh_public_keys = var.ssh_public_keys
ciuser = "root"
ipconfig0       = "ip=192.168.86.170/24,gw=192.168.86.1"

vmid = var.vmid
}
sadfd