# Download Ubuntu 22.04 (Jammy) cloud image
# Ubuntu cloud images have excellent cloud-init support
resource "libvirt_volume" "ubuntu_base" {
  name   = "ubuntu-noble-base.qcow2-${count.index + 1}"
  pool   = "default"
  count  = var.num_of_master + var.num_of_worker
  target = {
    format = {
      type = "qcow2"
    }
  }

  create = {
    content = {
      # Ubuntu 22.04 LTS (Jammy Jellyfish) cloud image
      url = var.volume_config.url
    }
  }
}

# Create boot disk for VM1 (uses base image as backing store)
resource "libvirt_volume" "vm_disk" {
  name   = "vm${count.index + 1}-disk.qcow2"
  pool   = "default"
  count  = var.num_of_master + var.num_of_worker
  target = {
    format = {
      type = "qcow2"
    }
  }

  # Start with 2GB, will grow as needed
  capacity = var.volume_config.size # 2GB in bytes

  backing_store = {
    path   = libvirt_volume.ubuntu_base[count.index].path
    format = {
      type = "qcow2"
    }
  }
}
