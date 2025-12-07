module "test_container" {
  source = "./modules/lxc"

  hostname = "test-lxc"
  ip       = "192.168.86.160/24"
  node     = var.pve_node

  ct_root_password   = var.ct_root_password
  ct_ssh_public_keys = var.ct_ssh_public_keys
}
