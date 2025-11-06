terraform {
  required_providers {
    proxmox = {
      source = "telmate/proxmox"
      version = "~> 2.9" # Use the latest stable version
    }
  }
}

provider "proxmox" {
 pm_api_url   = "https://proxmox.clothiernet.duckdns.org:8006/api2/json"
 pm_user      = "terraform_Svc"
 pm_password  = "ed52c704-d4a7-49b0-9957-aace7545de36"
 pm_tls_insecure = true
}

