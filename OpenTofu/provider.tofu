# provider.tf
terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "0.9.7"
    }
    external = {
      source = "opentofu/external"
      version = "2.3.5"
    }
  }
}

# Connect to local libvirt socket
provider "libvirt" {
  uri = "qemu:///system"
}

