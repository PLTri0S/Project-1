# Download Ubuntu 22.04 (Jammy) cloud image
# Ubuntu cloud images have excellent cloud-init support
resource "libvirt_volume" "ubuntu_base" {
  name   = "ubuntu-noble-base.qcow2"
  pool   = "default"
  target = {
    format = {
      type = "qcow2"
    }
  }

  create = {
    content = {
      # Ubuntu 22.04 LTS (Jammy Jellyfish) cloud image
      url = "${path.module}/cloud_image/noble-server-cloudimg-amd64.img"
    }
  }
}

# Create boot disk for VM1 (uses base image as backing store)
resource "libvirt_volume" "master_disk" {
  name   = "master-${count.index + 1}-disk.qcow2"
  pool   = "default"
  count  = var.Master_config.nodes
  target = {
    format = {
      type = "qcow2"
    }
  }

  capacity = var.volume_config.size 

  backing_store = {
    path   = libvirt_volume.ubuntu_base.path
    format = {
      type = "qcow2"
    }
  }
}

resource "libvirt_volume" "worker_disk" {
  name   = "worker-${count.index + 1}-disk.qcow2"
  pool   = "default"
  count  = var.Worker_config.nodes
  target = {
    format = { type = "qcow2" }
  }
  capacity = var.volume_config.size

  backing_store = {
    path   = libvirt_volume.ubuntu_base.path
    format = { type = "qcow2" }
  }
}
