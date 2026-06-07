# k8s project

## What this project does
Automates Kubernetes cluster provisioning using:
- **OpenTofu** (libvirt provider) → provisions KVM/QEMU VMs
- **Kubespray** (Ansible) → installs Kubernetes on those VMs
- **FastMCP server** → exposes everything as tools the AI can call

## Key flow
# 1. List all Vms, then **ASK THE USER** if they want to build from scratch or continue building with the current available vms
# 1.1 If they want to build it from scratch then first destroy all of the vms then go to step 2
# 1.2 If they want to continue working then start all of the current vms first (if they are in shut off state)
# 2. Check the machine's specs
# 3. Provision VMs
*** Use only if there are **ABSOLUTELY NO** VMs have been created ***
*** If user don't specify anything about the specs, then read "infra://vm-provisioning resources" ***
# 3.1 Update VMs
*** Use if there are **MORE THAN 1** VMs have been created ***
*** Can be used for create more vms or delete some vms ***
# 4. Deploy cluster
# 4.1 Check connection
# 4.2 Deploy cluster
*** MUST ask user which network plugin to choose ***
# 4.3 Scale up 
**Use only when to scaling up nodes**
*** IMPORTANT, scale up mean scale n nodes up, not scale to n nodes***

# 4.4 Scale down 
**Use only when to scaling down nodes**
*** ASK THE USER IF THEY WANT SCALE DOWN OR DELETE. If delete the vms entirely then use update_vms ***

## Important conventions
- **IMPORTANT KEY WORD**: nodes = VMs with cluster install on it. VMs is just VMs
- You are NOT ALLOW to use shell or bash commmand unless required by user
- All varibles used in here are in GB
- **MUST ask the user to confirm before destroy vms, scale down nodes or delete cluster**
- **WHEN CHANGING NETWORK PLUGIN, MUST REMOVE_CLUSTER FIRST**

