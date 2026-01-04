terraform {
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "3.0.2-rc06"
    }
  }
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

  # cloud-init config
  ipconfig0 = var.ipconfig0
  sshkeys   = local.sshkeys_str

  # (keep the rest of your existing disk/network blocks here)
}
