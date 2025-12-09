module "test_container" {
  source = "./modules/lxc"

  hostname = "test-lxc"
  ip       = "192.168.86.160/24"
  node     = var.pve_node

  ct_root_password   = var.ct_root_password
  ct_ssh_public_keys = var.ct_ssh_public_keys
}

module "web01" {
  source = "./modules/lxc"

  hostname = "web01"
  ip       = "192.168.86.161/24"
  node     = "proxmox3"

  ct_root_password   = var.ct_root_password
  ct_ssh_public_keys = var.ct_ssh_public_keys
}
