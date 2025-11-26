terraform {
  backend "s3" {
    endpoint = "https://minio.clothiernet.duckdns.org"

    bucket = "terraform-state"
    key    = "proxmox/homelab.tfstate"
    region = "us-east-1"

    skip_credentials_validation = true
    skip_region_validation      = true
    use_path_style              = true
  }
}
