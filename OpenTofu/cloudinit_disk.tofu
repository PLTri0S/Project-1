# Cloud-init configuration for VM1
resource "libvirt_cloudinit_disk" "master_init" {
  name  = "master-${count.index + 1}-cloudinit.iso"
  count = var.Master_config.nodes
  # User-data: Configure root password, enable SSH, install packages
  user_data = templatefile("${path.module}/config/user_data.yaml", {ssh_key = file("~/.ssh/id_ed25519.pub")})

  # Meta-data: Instance identification
  meta_data = <<-EOF
    instance-id: vm${count.index + 1}
    local-hostname: ubuntu-vm${count.index + 1}
  EOF

  # Network config: Use DHCP (default behavior)
  network_config = file("${path.module}/config/network_config.yaml")
  
}

# Upload cloud-init ISO for VM1 to a volume
resource "libvirt_volume" "master_cloudinit" {
  name  = "master-${count.index + 1}-cloudinit.iso"
  pool  = "default"
  count = var.Master_config.nodes
  # Format will be auto-detected as "iso"
  create = {
    content = {
      url = libvirt_cloudinit_disk.master_init[count.index].path
    }
  }
}

resource "libvirt_cloudinit_disk" "worker_init" {
  name  = "worker-${count.index + 1}-cloudinit.iso"
  count = var.Worker_config.nodes

  user_data = templatefile("${path.module}/config/user_data.yaml", {ssh_key = file("~/.ssh/id_ed25519.pub")})
  meta_data = <<-EOF
    instance-id: worker-node-${count.index + 1}
    local-hostname: ubuntu-worker-${count.index + 1}
  EOF
  network_config = file("${path.module}/config/network_config.yaml")
}

resource "libvirt_volume" "worker_cloudinit" {
  name  = "worker-${count.index + 1}-cloudinit.iso"
  pool  = "default"
  count = var.Worker_config.nodes
  create = {
    content = { url = libvirt_cloudinit_disk.worker_init[count.index].path }
  }
}