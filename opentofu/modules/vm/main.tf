terraform {
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "3.0.2-rc06"
    }
  }
}

variable "usb_host" {
  type        = string
  description = "Optional USB passthrough host (e.g. 1-7 or 10c4:ea60)"
  default     = ""
}


# Make DHCP the safe default
variable "ipconfig0" {
  type        = string
  description = "cloud-init network config (e.g. ip=dhcp OR ip=192.168.86.170/24,gw=192.168.86.1)"
  default     = "ip=dhcp"
}

variable "ssh_public_keys" {
  type        = list(string)
  description = "SSH public keys to inject via cloud-init"
  default     = []
}

variable "hostname" {
  type        = string
  description = "VM hostname"
}

variable "node" {
  type        = string
  description = "Proxmox node to deploy on"
  default     = "proxmox3"
}

variable "cores" {
  type        = number
  description = "Number of CPU cores"
  default     = 2
}

variable "memory" {
  type        = number
  description = "Memory in MB"
  default     = 4096
}

variable "disk_size" {
  type        = string
  description = "Primary disk size"
  default     = "32G"
}

variable "storage" {
  type        = string
  description = "Proxmox storage ID"
  default     = "USB_Storage_Space"
}

variable "net_bridge" {
  type        = string
  description = "Proxmox bridge"
  default     = "vmbr0"
}

# Prefer number for VMID
variable "template_vmid" {
  type        = number
  description = "Proxmox VM template VMID to clone from (e.g. 114)"
}

locals {
  sshkeys_str = length(var.ssh_public_keys) > 0 ? join("\n", var.ssh_public_keys) : null
  usb_host  = var.usb_host != "" ? var.usb_host : null
}

resource "proxmox_vm_qemu" "this" {
  name        = var.hostname
  target_node = var.node

  clone      = tostring(var.template_vmid)
  full_clone = true

  cpu {
    cores = var.cores
  }

  memory             = var.memory
  scsihw             = "virtio-scsi-pci"
  start_at_node_boot = true

  # Primary disk
  disk {
    type    = "disk"
    slot    = "scsi0"
    storage = var.storage
    size    = var.disk_size
  }

  # Cloud-init drive
  disk {
    type    = "cloudinit"
    slot    = "ide2"
    storage = var.storage
  }

  network {
    model  = "virtio"
    bridge = var.net_bridge
    id     = 0
  }
  dynamic "usb" {
  for_each = local.usb_host != "" ? [1] : []
  content {
    id   = 0
    usb3 = true
    # Use the correct field name depending on what your provider expects:
    host = local.usb_host
  }
}








  ipconfig0 = var.ipconfig0
  sshkeys   = local.sshkeys_str
  define_connection_info = false



}

output "vmid" {
  value = proxmox_vm_qemu.this.vmid
}
