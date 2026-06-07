# output "instructions" {
#   value = <<-EOF

#     Virtual machines have been created!

#     To find IP addresses assigned by DHCP:
#       sudo virsh domifaddr <nameOfVm>

#     Or check the DHCP leases:
#       sudo virsh net-dhcp-leases default

#     To view VM console:
#       sudo virsh console <nameOfVm>

#     inventory.yaml is located at "/home/msi/Vscode/Ansible/My-project/kubespray/inventory/mycluster/inventory.yaml"

#     Note: It may take 30-60 seconds after boot for cloud-init to complete
#           and the SSH server to be available.
#   EOF
# }

data "external" "master_ips" {
  program = ["python3", "${path.module}/config/get_vm_ips.py"]
  query = {
    vm_names = jsonencode(libvirt_domain.Master[*].name)
  }
  # depends_on = [libvirt_domain.Master]
}

data "external" "worker_ips" {
  program = ["python3", "${path.module}/config/get_vm_ips.py"]
  query = {
    vm_names = jsonencode(libvirt_domain.Worker[*].name)
  }
  # depends_on = [libvirt_domain.Worker]
}

output "IPS" {
  value = {
    master_hosts = jsondecode(data.external.master_ips.result.hosts)
    worker_hosts = jsondecode(data.external.worker_ips.result.hosts)
  }
}

# output "worker_hosts" {
#   value = jsondecode(data.external.worker_ips.result.hosts)
# }
