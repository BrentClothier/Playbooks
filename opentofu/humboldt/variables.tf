variable "pm_api_url" {
  type = string
}

variable "pm_api_token_id" {
  type = string
}

variable "pm_api_token_secret" {
  type      = string
  sensitive = true
}

variable "ssh_public_keys" {
  type    = list(string)
  default = []
}

variable "template_name" {
  type    = string
  default = "ubuntu-2504-cloud-uefi-prep"
}
