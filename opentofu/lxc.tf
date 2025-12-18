# Playbooks/opentofu/lxc.tf
module "homeassistant" {
  source = "./modules/lxc"

  hostname    = "HomeAssistant"
  ip          = "192.168.86.170/24"   # your chosen IP
  node        = "proxmox3"

  disk_size = "32G"
  

  ct_root_password   = var.ct_root_password
  ct_ssh_public_keys = var.ct_ssh_public_keys


}
