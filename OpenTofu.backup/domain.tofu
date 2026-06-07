# Virtual Machine 1
resource "libvirt_domain" "Master" {
  name   = "Master-Node-0${count.index + 1}"
  memory = var.Master_config.ram # 4 GB in KiB (1024 * 1024)
  vcpu   = var.Master_config.vcpu
  type   = "kvm"
  count  = var.num_of_master

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
            pool   = libvirt_volume.vm_disk[count.index].pool
            volume = libvirt_volume.vm_disk[count.index].name
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
            pool   = libvirt_volume.vm_cloudinit[count.index].pool
            volume = libvirt_volume.vm_cloudinit[count.index].name
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
  name   = "Worker-node-0${count.index + 1}"
  memory = var.Worker_config.ram 
  vcpu   = var.Worker_config.vcpu
  type   = "kvm"
  count  = var.num_of_worker

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
            pool   = libvirt_volume.vm_disk[count.index + var.num_of_master].pool
            volume = libvirt_volume.vm_disk[count.index + var.num_of_master].name
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
            pool   = libvirt_volume.vm_cloudinit[count.index + var.num_of_master].pool
            volume = libvirt_volume.vm_cloudinit[count.index + var.num_of_master].name
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
  filename = "/home/msi/Vscode/Ansible/My-project/inventory.yaml"

  content = templatefile("${path.module}/inventory.tftpl", {
    master_ips = split(",", data.external.master_ips.result.ips)
    worker_ips = split(",", data.external.worker_ips.result.ips)
  })
}

