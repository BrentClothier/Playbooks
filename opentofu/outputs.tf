output "ansible_hosts" {
  description = "Hosts for Ansible (consumed by Semaphore playbook)"
  value = {
    ha = {
      host = "192.168.86.170"
      user = "root"
      port = 22
    }
  }
}
