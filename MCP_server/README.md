## Project Structure
My-project/
├── MCP_server/            # FastMCP server (Python)
│   ├── vms_manager.py     # tools for managing vms
│   └── cluster_manager.py # tools for managing cluster
├── OpenTofu/
│   ├── provider.tofu      # OpenTofu configs (libvirt provider)
│   ├── volumes.tf
│   ├── variables.tofu
│   ├── domain.tofu
│   ├── cloudinit_disk.tofu
│   ├── inventory.tftpl     # Converts tofu output to inventory.yaml
│   ├── output.tofu         # Outputs VM IPs for Kubespray inventory
│   ├── terraform.tfvars.json # For config VMs' specs 
│   └── config/
│       └── get_vm_ips.py   # Translate output from Tofu to JSON format
├   
│ 
├── kubespray/                              # Git submodule