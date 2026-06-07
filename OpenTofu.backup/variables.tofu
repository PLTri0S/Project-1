variable "volume_config" {
    type        = object({
      size     = number
      url      = string
    })
    default = {
      size     = 10737418240
      url      = "/home/msi/Vscode/Ansible/My-project/cloud_image/noble-server-cloudimg-amd64.img"
    }
    
}

variable "Master_config" {
    type   = object({
      #name = string
      ram  = number
      vcpu = number
    })
    default = {
      #name  = "Master-Node-01"
      ram   = 2097152
      vcpu  = 2
    }
}

variable "Worker_config" {
    type   = object({
      #name = string
      ram  = number
      vcpu = number
    })
    default = {
      #name = "Worker-node-01"
      ram  = 1048576
      vcpu = 1
    }  
}

variable "num_of_master" {
  type = number
  default = 1
}

variable "num_of_worker" {
  type    = number
  default = 2
}

variable "user_data_file" {
  type = string
  default = "/home/msi/Vscode/Ansible/My-project/OpenTofu/config/user_data.yaml"
}

variable "network_config_file" {
  type = string
  default = "/home/msi/Vscode/Ansible/My-project/OpenTofu/config/network_config.yaml"
}

