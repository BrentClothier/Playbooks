terraform {
  required_providers {
    proxmox = {
      source = "telmate/proxmox"
    }
  }
}

variable "storage" {
  type        = string
  description = "Proxmox storage ID to use for the container rootfs"
  default     = "USB_Storage_Space"
}

variable "start" {
  type        = bool
  description = "Whether to start the container immediately after creation"
  default     = true
}

variable "onboot" {
  type        = bool
  description = "Whether the container should start automatically on node boot"
  default     = true
}

variable "cores" {
  type        = number
  description = "Number of CPU cores for this LXC"
  default     = 2
}

variable "memory" {
  type        = number
  description = "Memory in MB for this LXC"
  default     = 2048
}

variable "disk_size" {
  type        = string
  description = "Root disk size (e.g., 15G)"
  default     = "15G"
}

variable "hostname" {
  type        = string
  description = "Hostname of the LXC container"
}

variable "ip" {
  type        = string
  description = "Static IP address with CIDR (e.g. 192.168.86.160/24)"
}

variable "node" {
  type        = string
  description = "Proxmox node to deploy on (e.g. proxmox3)"
}

variable "ct_root_password" {
  type        = string
  description = "Root password for the container"
  sensitive   = true
}

variable "ct_ssh_public_keys" {
  type        = list(string)
  description = "SSH public keys for root in the container"
  default     = []
}

resource "proxmox_lxc" "this" {
  target_node = var.node
  hostname    = var.hostname
  ostemplate  = "local:vztmpl/ubuntu-25.04-standard_25.04-1.1_amd64.tar.zst"

  cores  = var.cores
  memory = var.memory


  unprivileged = false

  start  = var.start
  onboot = var.onboot

  password        = var.ct_root_password
  ssh_public_keys = var.ct_ssh_public_keys

  rootfs {
    storage = var.storage
    size = var.disk_size
  }

  network {
    name   = "eth0"
    bridge = "vmbr0"
    ip     = var.ip
    gw     = "192.168.86.1"
    tag    = 1
  }

  features {
    nesting = true
  }

  lifecycle {
  ignore_changes = [
    ssh_public_keys,
    rootfs[0].acl,
    rootfs[0].quota,
    rootfs[0].replicate,
    rootfs[0].ro,
    rootfs[0].shared,
    network[0].firewall,
    network[0].mtu,
    network[0].rate,
  ]
}

}

output "vmid" {
  value = proxmox_lxc.this.vmid
}