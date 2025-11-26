variable "pm_api_url" {
  type        = string
  description = "Proxmox API URL (e.g. https://proxmox.clothiernet.duckdns.org:8006/api2/json)"
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
