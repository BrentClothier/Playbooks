terraform {
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "3.0.2-rc06"
    }
  }
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

variable "template_vmid" {
  type        = string
  description = "Proxmox VM template VMID to clone from (e.g. 114)"
}

resource "proxmox_vm_qemu" "this" {
  name        = var.hostname
  target_node = var.node
  clone       = var.template_vmid
  full_clone  = true


  cpu {
    cores = var.cores
  }
  
  memory  = var.memory

  scsihw = "virtio-scsi-pci"
  start_at_node_boot = true

  # --- Primary disk (multi-block syntax ONLY) ---
disk {
  type    = "disk"
  slot    = "scsi0"
  storage = var.storage
  size    = var.disk_size
}


  # --- Network interface ---
  network {
    model  = "virtio"
    bridge = var.net_bridge
    id     = 0
  }

  ipconfig0 = "ip=dhcp"
  
}

output "vmid" {
  value = proxmox_vm_qemu.this.vmid
}
