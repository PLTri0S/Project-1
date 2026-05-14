# Kubespray & VM Provisioning Guide

This document serves as an internal knowledge resource for the MCP server. It outlines the minimum hardware requirements for provisioning a Kubernetes cluster using Kubespray and OpenTofu/Libvirt, and catalogs known issues and their remediations.

## 1. Minimum Specifications Requirements

When calling `provision_vms` or `update_vms`, the following specifications are required to ensure a stable Kubernetes deployment.

### Control Plane (Master Nodes)
* **Nodes:** Must be an odd number (1, 3, or 5) to maintain etcd quorum.
* **vCPU:** 2 Cores minimum (Kubernetes API server and etcd are CPU intensive).
* **RAM:** 2.5 GB minimum. (2 GB is the absolute hard limit for testing, but etcd will frequently crash out of memory under load) (>=4 GB recommended).
* **Disk:** 10 GB minimum for the OS, container images, and etcd data.

### Worker Nodes
* **Nodes:** 1 minimum (Recommended 2+ for high availability testing).
* **vCPU:** 2 Cores minimum (1 Core is possible but leaves very little room for workloads after kubelet and daemonsets).
* **RAM:** 1.5 GB minimum (2-4 GB recommended).
* **Disk:** 10 GB minimum.

### Host Machine Overhead
As defined in the provisioning manager, the host physical machine must maintain a safety reserve:
* **RAM Reserve:** 3 GB minimum.
* **CPU Reserve:** 2 Cores minimum.
* **Disk Reserve:** 100 GB minimum.

---

## 2. VM Provisioning Troubleshooting (OpenTofu + Libvirt)

### Issue 2.1: `tofu apply` Fails on the First Run
* **Symptom:** OpenTofu errors out during the `apply` phase, but a subsequent run might succeed.
* **Root Cause:** Libvirt volume creation or network allocation timeouts can cause intermittent state synchronization issues.
* **Fix:** The `update_vms` script currently has a `try-except` block to retry `apply` once. If this persists, manually inspect Libvirt storage pools to ensure no orphaned volumes are blocking creation: `virsh vol-list default`.

### Issue 2.2: Terraform State Lock
* **Symptom:** Error: `Error acquiring the state lock`.
* **Root Cause:** A previous `deploy_cluster` or `provision_vms` script crashed or was forcefully terminated before it could release the `.terraform.tfstate.lock.info`.
* **Fix:** Run `tofu force-unlock <LOCK_ID>` in the `OpenTofu/` directory, or manually delete the lock file if no other processes are running.

### Issue 2.3: VMs Provisioned but No IP Assigned (DHCP Failure)
* **Symptom:** OpenTofu output shows VMs created, but they lack IP addresses, causing Ansible SSH connections to timeout.
* **Root Cause:** Libvirt's default network `dnsmasq` might have stale leases.
* **Fix:** Restart the default libvirt network: 
    ```bash
    virsh net-destroy default
    virsh net-start default
    ```

---

## 4. Cluster Creation Troubleshooting (Kubespray & Ansible)

### Issue 3.1: Ansible SSH Connection Refused/Timeout
* **Symptom:** `deploy_cluster` fails immediately on the `Gathering Facts` step.
* **Root Cause:** The `cluster_manager.py` executes Ansible immediately after `vms_manager.py` finishes. The VMs are powered on but `sshd` has not finished booting.
* **Fix:** Introduce a wait step. Either add a Python `time.sleep(30)` before calling `ansible-playbook`, or add a `wait_for_connection` pre-task in the Ansible playbook to poll port 22.

### Issue 3.2: Cilium Network Plugin Errors
* **Symptom:** Kubespray fails during the `network_plugin/cilium` role.
* **Root Cause:** Kernel compatibility, missing BPF mounts, or unconfigured default routing tables in the VMs.
* **Fix:** This is successfully mitigated by post-provisioning playbook: `playbooks/cilium_error_fix.yml`. Ensure this is always run sequentially if Cilium crashes.

### Issue 3.3: Missing Python Packages in `.venv`
* **Symptom:** Ansible throws an error about missing dependencies like `netaddr` or `jmespath`.
* **Root Cause:** The virtual environment at `kubespray/.venv` is missing required Kubespray dependencies.
* **Fix:** Ensure the Python environment is primed before execution:
    ```bash
    source kubespray/.venv/bin/activate
    pip install -r kubespray/requirements.txt
    ```

### Issue 3.4: Kubeconfig Permission Denied
* **Symptom:** Cluster is created successfully, but running `kubectl get nodes` on the host machine returns a permission error.
* **Root Cause:** Ansible fetches the `admin.conf` as root, leaving it owned by `root:root` in `~/.kube/config`. 
* **Fix:** You currently run `playbooks/setup_kubeconfig.yml`. If that playbook doesn't enforce the `owner/group`, you must re-enable the commented-out `sudo chown` command in `cluster_manager.py`:
    ```python
    _run_command(["sudo", "chown", uid_gid, f"/home/{os.environ.get('USER')}/.kube/config"])
    ```
