output "admin_ansible_host" {
  description = "Admin VM host for Ansible"
  value = {
    host = "192.168.86.171"
    user = "root"
    port = 22
  }
}
