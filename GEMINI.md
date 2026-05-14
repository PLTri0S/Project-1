# k8s project

## What this project does
Automates Kubernetes cluster provisioning using:
- **OpenTofu** (libvirt provider) → provisions KVM/QEMU VMs
- **Kubespray** (Ansible) → installs Kubernetes on those VMs
- **FastMCP server** → exposes everything as tools Claude can call

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
├── OpenTofu.backup/        # safety net if something break
│ 
├── kubespray/                              # Git submodule
│   ├── inventory/mycluster/inventory.yaml  # Auto-generated from tofu outputs
│   ├── playbooks/cluster.yml               # deploy cluster
│   
└── 

## Key flows
1. **MUST Read resources: "internal://rules", "infra://kubespray-vm-provisioning".**
2. Managing vms: Use suitable tools to managing VMs
3. Managing cluster: Use suitable tools to managing cluster

## Important conventions
- DO NOT edit any of the files above unless required by the user
- All varibles used in here is in GB
- project dir: /home/msi/Vscode/Ansible/My-project/
- tofu dir: /home/msi/Vscode/Ansible/My-project/OpenTofu
- kubespray dir: /home/msi/Vscode/Ansible/My-project/kubespray

