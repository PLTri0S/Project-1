# Cloud-init configuration for VM1
resource "libvirt_cloudinit_disk" "vm_init" {
  name  = "vm${count.index + 1}-cloudinit.iso"
  count = var.num_of_master + var.num_of_worker
  # User-data: Configure root password, enable SSH, install packages
  user_data = templatefile(var.user_data_file, {ssh_key = file("~/.ssh/id_ed25519.pub")})


  # Meta-data: Instance identification
  meta_data = <<-EOF
    instance-id: vm${count.index + 1}
    local-hostname: ubuntu-vm${count.index + 1}
  EOF

  # Network config: Use DHCP (default behavior)
  network_config = file(var.network_config_file)
  
}

# Upload cloud-init ISO for VM1 to a volume
resource "libvirt_volume" "vm_cloudinit" {
  name  = "vm${count.index + 1}-cloudinit.iso"
  pool  = "default"
  count = var.num_of_master + var.num_of_worker
  # Format will be auto-detected as "iso"
  create = {
    content = {
      url = libvirt_cloudinit_disk.vm_init[count.index].path
    }
  }
}

