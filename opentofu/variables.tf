variable "pm_api_url" {
  type        = string
  description = "Proxmox API URL (e.g. https://192.168.86.68:8006/api2/json)"
}

variable "pm_api_token_id" {
  type        = string
  description = "Proxmox API token ID (e.g. terraform_Svc@pam!tf-full OR root@pam!tf-root)"
}

variable "pm_api_token_secret" {
  type        = string
  description = "Proxmox API token secret"
  sensitive   = true
}

# where to deploy
variable "pve_node" {
  type        = string
  description = "Default Proxmox node to deploy on"
  default     = "proxmox2"
}

variable "storage" {
  type        = string
  description = "Proxmox storage ID"
  default     = "USB_Storage_Space"
}

# keep your existing Semaphore env var name
variable "ssh_public_keys" {
  type        = list(string)
  description = "SSH public keys to inject"
  default     = []
}

# optional: let you pin a VMID so it recreates predictably
variable "vmid" {
  type        = number
  description = "Optional VMID to force (e.g. 116). Leave 0 to auto-assign."
  default     = 0
}
variable "template_name" {
  type        = string
  description = "Proxmox VM template name to clone (must match `qm config <id> | grep '^name:'`)"
  default     = "ubuntu-2504-cloud-uefi"
}