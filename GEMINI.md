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
# 1.3 Check whether or not the current vms have cluster installed. If not go to step 2, if yes go to next step
# 1.4 Check the current cluster/vms status, specs, their network and ask the user whether to update vms or working with the current cluster.
# 2. Check the machine's specs
# 3. Provision VMs
*** Use only if there are **ABSOLUTELY NO** VMs have been created ***
*** If user don't specify anything about the specs, then read "infra://vm-provisioning resources" ***
# 3.1 Update VMs
*** Use if there are **MORE THAN 1** VMs have been created ***
*** Can be used for create more vms or delete vms ***
# 4. Deploy cluster
# 4.1 Check connection
*** If the there is an connection error then try to update the inventory by reprovision the current vms using update_vms ***
# 4.2 Deploy cluster
*** MUST ask user which network plugin to choose ***
# 4.3 Scale up
**Use only when to scaling more nodes**
*** IMPORTANT, scale up mean scale n nodes up, not scale up to n nodes***

# 4.4 Remove nodes (scale down)
**Use only when to Remove nodes**
*** IMPORTANT, Remove nodes mean remove n nodes, not Remove nodes to n nodes***
*** ASK IF THE USER WANT TO DELETE THE VMS OR JUST REMOVING NODES. IF DELETE VMS THEN USE THE UPDATE VMS TOOL AND KUBECTL_DELETE, ELSE REMOVE NODES AND KEEP VMS ***

# 5. Deploy nginx web server
**Bluepirnt located at: /home/msi/Vscode/Ansible/My-project/web_server**

# 6. Test web server
**You are allow to use shell cmd to run hey**
## Important conventions
- **IMPORTANT KEY WORD**: nodes = VMs with cluster install on it. VMs is just VMs
- You are NOT ALLOW to use shell or bash commmand unless required by user
- All varibles used in here are in GB
- **MUST ask the user to confirm before destroy vms, remove nodes or delete cluster**
- **WHEN CHANGING NETWORK PLUGIN, MUST REMOVE_CLUSTER FIRST**
- **IF the deploy cluster prcocess is taking too long (> 30 min) or unfixable then build from scratch**