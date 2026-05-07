variable "volume_config" {
    type       = object({
      size     = number
      url      = string
    })
    default = {
      size     = 10737418240 #in KB
      url      = "/home/msi/Vscode/Ansible/My-project/cloud_image/noble-server-cloudimg-amd64.img"
    }
    
}

variable "Master_config" {
    type    = object({
      nodes = number
      ram   = number
      vcpu  = number
    })
    default = {
      nodes = 1
      ram   = 2097152 # 2GB
      vcpu  = 2
    }
}

variable "Worker_config" {
    type    = object({
      nodes = number
      ram   = number
      vcpu  = number
    })
    default = {
      nodes = 2
      ram   = 1048576 # 1GB
      vcpu  = 1
    }  
}

variable "user_data_file" {
  type = string
  default = "/home/msi/Vscode/Ansible/My-project/OpenTofu/config/user_data.yaml"
}

variable "network_config_file" {
  type = string
  default = "/home/msi/Vscode/Ansible/My-project/OpenTofu/config/network_config.yaml"
}
