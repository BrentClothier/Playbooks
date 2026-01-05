terraform {
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "3.0.2-rc06"
    }
  }
}
variable "ciuser" {
  type        = string
  description = "cloud-init username"
  default     = "ubuntu"
}

variable "cores" {
  type    = number
  default = 2
}

variable "memory" {
  type    = number
  default = 4096
}

variable "disk_size" {
  type    = string
  default = "32G"
}

variable "vlan_tag" {
  type        = number
  description = "0 = none, otherwise VLAN tag"
  default     = 0
}
variable "hostname" { type = string }
variable "node"     { type = string }
variable "storage"  { type = string }

variable "template_name" {
  type        = string
  description = "Template NAME to clone from"
}

variable "ipconfig0" {
  type        = string
  default     = "ip=dhcp"
}

variable "ssh_public_keys" {
  type    = list(string)
  default = []
}

variable "vmid" {
  type    = number
  default = 0
}
variable "net_bridge" {
  type        = string
  description = "Bridge name (e.g. vmbr0)"
  default     = "vmbr0"
}


locals {
  sshkeys_str = length(var.ssh_public_keys) > 0 ? join("\n", var.ssh_public_keys) : null
}

resource "proxmox_vm_qemu" "this" {
  name        = var.hostname
  target_node = var.node

  # IMPORTANT: clone expects NAME here
  clone      = var.template_name
  full_clone = true

  # don’t let the provider try SSH during plan/apply
  define_connection_info = false

  # only set vmid if you provided one
  vmid = var.vmid != 0 ? var.vmid : null

  # Make the VM match your working template expectations
  bios    = "ovmf"
  machine = "q35"
  scsihw  = "virtio-scsi-pci"
  agent   = 1

  cpu {
    cores = var.cores
  }
  memory             = var.memory
  start_at_node_boot = true
  boot               = "order=scsi0"

  # Ensure there IS a boot disk and a cloud-init drive
  disk {
    type    = "disk"
    slot    = "scsi0"
    storage = var.storage
    size    = var.disk_size
  }

  disk {
    type    = "cloudinit"
    slot    = "ide2"
    storage = var.storage
  }

  network {
    model  = "virtio"
    bridge = var.net_bridge
    id     = 0
    tag    = var.vlan_tag
  }

  # cloud-init config
  ipconfig0 = var.ipconfig0
  sshkeys   = local.sshkeys_str
  ciuser = var.ciuser

}




