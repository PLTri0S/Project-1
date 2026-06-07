variable "volume_config" {
    type       = object({
      size     = number
    })
    default = {
      size     = 10737418240 #in B
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
      nodes = 1
      ram   = 1048576 # 1GB
      vcpu  = 1
    }  
}

