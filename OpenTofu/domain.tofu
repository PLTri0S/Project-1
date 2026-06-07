# Virtual Machine 1
resource "libvirt_domain" "Master" {
  name   = "master-${count.index + 1}"
  memory = var.Master_config.ram 
  vcpu   = var.Master_config.vcpu
  type   = "kvm"
  count  = var.Master_config.nodes
  # Boot configuration
  os = {
    type    = "hvm"
    type_arch    = "x86_64"
    type_machine = "q35"
  }

  # Attached disks
  devices = {
    disks = [
      # Main system disk
      {
        source = {
          volume = {
            pool   = libvirt_volume.master_disk[count.index].pool
            volume = libvirt_volume.master_disk[count.index].name
          }
        }
        target = {
          bus = "virtio"
          dev = "vda"
        }
        driver = {
          type = "qcow2"
        }
      },
      # Cloud-init config disk (will be detected automatically)
      {
        device = "cdrom"
        source = {
          volume = {
            pool   = libvirt_volume.master_cloudinit[count.index].pool
            volume = libvirt_volume.master_cloudinit[count.index].name
          }
        }
        target = {
          bus = "sata"
          dev = "sda"
        }
      }
    ]

    # Network interface on default network (DHCP)
    interfaces = [
      {
        wait_for_ip = {
          time = 500
        }
        type  = "network"
        model = { type = "virtio" }
        source = {
          network = {
            network = "default"
          }
        }
      }
    ]
    
    serials = [
      {
        type = "pty"
      }
    ]

    console = [
      {
        type        = "pty"
        target_port = "0"
        target_type = "serial"
      }
    ]
  }

  

  # Start the VM automatically
  running = true
}

# Virtual Machine 2
resource "libvirt_domain" "Worker" {
  name   = "worker-${count.index + 1}"
  memory = var.Worker_config.ram 
  vcpu   = var.Worker_config.vcpu
  type   = "kvm"
  count  = var.Worker_config.nodes

  os = {
    type    = "hvm"
    type_arch    = "x86_64"
    type_machine = "q35"
  }

  devices = {
    disks = [
      {
        source = {
          volume = {
            # Start an disk #1
            pool   = libvirt_volume.worker_disk[count.index].pool
            volume = libvirt_volume.worker_disk[count.index].name
          }
        }
        target = {
          bus = "virtio"
          dev = "vda"
        }
        driver = {
          type = "qcow2"
        }
      },
      {
        device = "cdrom"
        source = {
          volume = {
            pool   = libvirt_volume.worker_cloudinit[count.index].pool
            volume = libvirt_volume.worker_cloudinit[count.index].name
          }
        }
        target = {
          bus = "sata"
          dev = "sda"
        }
      }
    ]

    interfaces = [
      {
        wait_for_ip = {
          time = 500
        }
        type  = "network"
        model = { type = "virtio" }
        source = {
          network = {
            network = "default"
          }
        }
      }
    ]

    serials = [
      {
        type = "pty"
      }
    ]
  
    console = [
      {
        type        = "pty"
        target_port = "0"
        target_type = "serial"
      }
    ]
  }
  running = true
}

resource "local_file" "ansible_inventory" {
  # Save the file as a YAML file
  filename = "${path.module}/../kubespray/inventory/mycluster/inventory.yaml"

  content = templatefile("${path.module}/config/inventory.tftpl", {
    master_ips = split(",", data.external.master_ips.result.ips)
    worker_ips = split(",", data.external.worker_ips.result.ips)
  })
}

