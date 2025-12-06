resource "proxmox_lxc" "test_container" {
  target_node = var.pve_node
  hostname    = "test-lxc"
  ostemplate  = "local:vztmpl/ubuntu-25.04-standard_25.04-1.1_amd64.tar.zst"

  cores  = 2
  memory = 2048  # MB

  unprivileged = true

  start = true
  onboot = true

  password        = var.ct_root_password
  ssh_public_keys = var.ct_ssh_public_keys

  rootfs {
    storage = "USB_Storage_Space"
    size    = "4G"
  }

  network {
  name   = "eth0"
  bridge = "vmbr0"
  ip     = "192.168.86.160/24"
  gw     = "192.168.86.1"
  tag    = 1
}

  features {
    nesting = true
  }
  
}
