# Kubespray & VM Provisioning Guide

This document serves as an internal knowledge resource for the MCP server. It catalogs known issues and their remediations.

---

## 6. VM Provisioning Troubleshooting (OpenTofu + Libvirt)

### Issue 6.1: `tofu apply` Fails on the First Run
* **Symptom:** OpenTofu errors out during the `apply` phase, but a subsequent run might succeed.
* **Root Cause:** Libvirt volume creation or network allocation timeouts can cause intermittent state synchronization issues.
* **Fix:** The `update_vms` script currently has a `try-except` block to retry `apply` once. If this persists, manually inspect Libvirt storage pools to ensure no orphaned volumes are blocking creation: `virsh vol-list default`.

### Issue 6.2: Terraform State Lock
* **Symptom:** Error: `Error acquiring the state lock`.
* **Root Cause:** A previous `deploy_cluster` or `provision_vms` script crashed or was forcefully terminated before it could release the `.terraform.tfstate.lock.info`.
* **Fix:** Run `tofu force-unlock <LOCK_ID>` in the `OpenTofu/` directory, or manually delete the lock file if no other processes are running.

### Issue 6.3: VMs Provisioned but No IP Assigned (DHCP Failure)
* **Symptom:** OpenTofu output shows VMs created, but they lack IP addresses, causing Ansible SSH connections to timeout.
* **Root Cause:** Libvirt's default network `dnsmasq` might have stale leases.
* **Fix:** Restart the default libvirt network: 
    ```bash
    virsh net-destroy default
    virsh net-start default
    ```
### Issue 6.4 virsh volume permission denied error
1. Create dir if no exists: /etc/apparmor.d/abstractions/libvirt-qemu.d
`sudo mkdir -p /etc/apparmor.d/abstractions/libvirt-qemu.d`
2. Create this file /etc/apparmor.d/abstractions/libvirt-qemu.d/override.
`sudo vim /etc/apparmor.d/abstractions/libvirt-qemu.d/override`
3. `/var/lib/libvirt/images/** rwk,`
4. Restart AppAmor
`sudo systemctl restart apparmor`
---

## 7. Cluster Creation Troubleshooting (Kubespray & Ansible)

### Issue 7.1: Ansible SSH Connection Refused/Timeout
* **Symptom:** `deploy_cluster` fails immediately on the `Gathering Facts` step.
* **Root Cause:** The `cluster_manager.py` executes Ansible immediately after `vms_manager.py` finishes. The VMs are powered on but `sshd` has not finished booting.
* **Fix:** Introduce a wait step. Either add a Python `time.sleep(30)` before calling `ansible-playbook`, or add a `wait_for_connection` pre-task in the Ansible playbook to poll port 22.

### Issue 7.2: Cilium Network Plugin Errors
* **Symptom:** Kubespray fails during the `network_plugin/cilium` role.
* **Root Cause:** Kernel compatibility, missing BPF mounts, or unconfigured default routing tables in the VMs.
* **Fix:** This is successfully mitigated by post-provisioning playbook: `playbooks/cilium_error_fix.yml`. Ensure this is always run sequentially if Cilium crashes.

### Issue 7.3: Missing Python Packages in `.venv`
* **Symptom:** Ansible throws an error about missing dependencies like `netaddr` or `jmespath`.
* **Root Cause:** The virtual environment at `kubespray/.venv` is missing required Kubespray dependencies.
* **Fix:** Ensure the Python environment is primed before execution:
    ```bash
    source kubespray/.venv/bin/activate
    pip install -r kubespray/requirements.txt
    ```

### Issue 7.4: Kubeconfig Permission Denied
* **Symptom:** Cluster is created successfully, but running `kubectl get nodes` on the host machine returns a permission error.
* **Root Cause:** Ansible fetches the `admin.conf` as root, leaving it owned by `root:root` in `~/.kube/config`. 
* **Fix:** You currently run `playbooks/setup_kubeconfig.yml`. If that playbook doesn't enforce the `owner/group`, you must re-enable the commented-out `sudo chown` command in `cluster_manager.py`:
    ```python
    _run_command(["sudo", "chown", uid_gid, f"/home/{os.environ.get('USER')}/.kube/config"])
    ```
