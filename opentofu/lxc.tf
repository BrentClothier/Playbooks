resource "proxmox_lxc" "test_container" {
  target_node = var.pve_node
  hostname    = "test-lxc"
  ostemplate  = "local:vztmpl/ubuntu-25.04-standard_25.04-1.1_amd64.tar.zst"

  cores  = 1
  memory = 512  # MB

  rootfs {
    storage = "local"
    size    = "4G"
  }

  network {
    name   = "eth0"
    bridge = "vmbr0"
    ip     = "dhcp"
  }

  onboot = false
}
