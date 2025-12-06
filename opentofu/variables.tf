variable "pm_api_url" {
  type        = string
  description = "Proxmox API URL (e.g. https://192.168.86.68:8006/api2/json)"
}

variable "pm_api_token_id" {
  type        = string
  description = "Proxmox API token ID"
}

variable "pm_api_token_secret" {
  type        = string
  description = "Proxmox API token secret"
  sensitive   = true
}

variable "pve_node" {
  type        = string
  description = "Default Proxmox node to deploy containers/VMs on"
  default     = "proxmox3"
}

variable "ct_root_password" {
  type        = string
  description = "Root password for LXC containers"
  sensitive   = true
}

variable "ct_ssh_public_keys" {
  type        = string
  description = "SSH public keys to add to root's authorized_keys"
}