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