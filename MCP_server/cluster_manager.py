import json
from fastmcp import FastMCP, Context
import subprocess
from pathlib import Path
from vms_manager import _run_command
import os
import re
from ruamel.yaml import YAML

mcp = FastMCP(
    "k8s/libvirt",
    instructions="Provides tools for working with cluster and apps deployment. "
        "Start with GEMINI.md to get the overview of the structure."
    )

# define the working folder of this file
BASE_DIR = Path(__file__).resolve().parent
# Move up 1 folder
PROJECT_ROOT = BASE_DIR.parent
KUBESPRAY_DIR = PROJECT_ROOT / "kubespray"
OPENTOFU_DIR = PROJECT_ROOT / "OpenTofu"
VAR_FILE = OPENTOFU_DIR / "terraform.tfvars.json"
NETWORK_PLUGIN = KUBESPRAY_DIR / "inventory" / "mycluster" / "group_vars" / "k8s_cluster" / "k8s-cluster.yml"
INVENTORY = KUBESPRAY_DIR / "inventory" / "mycluster" / "inventory.yaml"

KUBESPRAY_VENV = KUBESPRAY_DIR / ".venv"
env = os.environ.copy()
env["VIRTUAL_ENV"] = KUBESPRAY_VENV
env["PATH"] = f"{KUBESPRAY_VENV}/bin:{env['PATH']}"
env.pop("PYTHONHOME", None)

def get_nodes() -> dict:
    try: 
        cluster = _run_command(["kubectl", "get", "nodes"])
        count_m = 0
        count_w = 0
        for line in cluster.stdout.splitlines():
            master = re.search(r"master-\d+", line)
            worker = re.search(r"worker-\d+", line)
            if master:
                count_m += 1
            if worker:
                count_w += 1
    except subprocess.CalledProcessError as e:
        return 
    return {
        "master-nodes-count": count_m,
        "worker-nodes-count": count_w
    }

def handling_ansible_error(error: str) -> dict:
        error_dict = {}
        count = 1
        Task_error = False
        for line in error.stdout.splitlines():
            target_node = re.search(r"(fatal:\s)(\D+\d\D+!)", line)
            msg = re.search(r"(msg\"\:\s)(\"\D+\d|\D+)",line)
            task = re.search(r"(TASK\s)(\D+[^\s*])", line)
            if target_node:
                error_dict[f"node-{count}"] = target_node.group(2)
                Task_error = True
            if task:
                error_dict[f"TASK-{count}"] = task.group(2)
            if msg and Task_error:
                error_dict[f"msg-{count}"] = msg.group(2)
                count +=1

        return {
            "status": "fail",
            "command": error.cmd,
            "error code": error.returncode,
            "cause": error_dict
        }

@mcp.resource("infra://inventory")
def read_rules() -> str:
    """INVENTORY FILE after provisioned vms"""
    return INVENTORY.read_text(encoding="utf-8")

@mcp.tool(timeout=30.0)
def check_connection(ctx: Context) -> dict: 
    """
    Check connection each vms in inventory file.
    """
    ctx.info("Checking connection to cluster nodes...")
    try:
        _run_command(["ansible", "all", "-i", "inventory/mycluster/inventory.yaml", "-m", "ping"], path=KUBESPRAY_DIR, environment=env, timeout=10)
    except subprocess.TimeoutExpired as t:
        return {
            "status": "fail",
            "command": t.cmd,
            "cause": "Timeout error"
        }
    except subprocess.SubprocessError as e:
        return handling_ansible_error(e)
    
    return {
        "status": "Successfully connected to all cluster nodes"
    }

@mcp.tool(timeout=3600.0)
def deploy_cluster(ctx: Context, network: str) -> dict:
    """
    Create cluster using kubespray.
    Choose from one of this network plugin: cacilo, cilium, flannel.
    """
    ctx.info("Prepare to deploy cluster...")

    #uid_gid = f"{os.getuid()}:{os.getgid()}"
    yaml = YAML()
    yaml.preserve_quotes = True

    with open(NETWORK_PLUGIN, "r") as file:
        data = yaml.load(file)

    data["kube_network_plugin"] = network
    with open(NETWORK_PLUGIN, "w") as file:
        yaml.dump(data, file)

    try:
        ctx.info("Deploying cluster...")
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "cluster.yml"], path=KUBESPRAY_DIR, environment=env)
        ctx.info("Add config to host machie...")
        if network == "cilium":
            ctx.info("fixing clilium error...")
            _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/cilium_error_fix.yml"], path=KUBESPRAY_DIR, environment=env)

        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/setup_kubeconfig.yml"], path=KUBESPRAY_DIR, environment=env)

        # _run_command(["sudo", "chown", uid_gid, "home/msi/.kube/config"])
    except subprocess.CalledProcessError as e:
        return handling_ansible_error(e)
    
    return {
        "status": "Succesfully created cluster"
        }

@mcp.tool(timeout=3600.0)
def scale_up(master: int, worker: int, network: str) -> dict:
    """
    Scale cluster by adding more master nodes using cluster.yml or worker nodes.
    """
    ## current 2 vms -> scale up 2 nodes -> need 1 more vms
    ## if scale up but no available vms -> Fail -> need to create vms first then scale up node
    config = json.loads(VAR_FILE.read_text(encoding="utf-8"))
    worker_c = get_nodes()["worker-nodes-count"]
    master_c = get_nodes()["master-nodes-count"]

    if worker:
        if worker_c + worker > config["Worker_config"]["nodes"] or worker_c + worker < config["Worker_config"]["nodes"]:
            return {
                "Status": "Fail",
                "Cause": f"Need {worker_c + worker - config["Worker_config"]["nodes"]} more worker Vms to scale up cluster, currently {config["Worker_config"]["nodes"]} worker."
            }
        
        scale_up_worker = [f"worker-{n}" for n in range(worker_c + 1, worker_c + worker + 1)]
        try:
            _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b","playbooks/facts.yml"], path=KUBESPRAY_DIR, environment=env)
            _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "scale.yml", "--limit=" + ",".join(scale_up_worker)], path=KUBESPRAY_DIR, environment=env)
            if network == "cilium":
                _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/cilium_error_fix.yml"], path=KUBESPRAY_DIR, environment=env)

        except subprocess.CalledProcessError as e:
            return handling_ansible_error(e)
    if master:
        if (master_c + master) % 2 == 0:
            return {
                "status": "Fail to scale up",
                "ERROR": "Control plane must be an odd number"
            }
        if master_c + master > config["Master_config"]["nodes"] or master_c + master < config["Master_config"]["nodes"]:
            return {
                "Status": "Fail",
                "Cause": f"Need {master_c + master - config["Master_config"]["nodes"]} more master Vms to scale up cluster, currently {config["Master_config"]["nodes"]} master"
            }

        try:
            _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "cluster.yml"], path=KUBESPRAY_DIR, environment=env)
            if network == "cilium":
                _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/cilium_error_fix.yml"], path=KUBESPRAY_DIR, environment=env)
        except subprocess.CalledProcessError as e:
            return handling_ansible_error(e)
        
    return {
        "status": "success",
        "scale_up_master": master,
        "scale_up_worker": worker,
        "detail": "Scale up finished successfully"
    }

@mcp.tool(timeout=3600.0) 
def scale_down(master: int, worker: int) -> dict:
    """
    Scale down cluster by remove master nodes using cluster.yml or worker nodes.

    """

    config = json.loads(VAR_FILE.read_text(encoding="utf-8"))
    worker_c = get_nodes()["worker-nodes-count"]
    master_c = get_nodes()["master-nodes-count"]

    if worker:
        scale_down_worker = [f"worker-{n}" for n in range(worker_c, worker_c - worker, -1)]
        try:
            _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "remove_node.yml", "-e", f"node={','.join(scale_down_worker)}" ], path=KUBESPRAY_DIR, environment=env)
        except subprocess.CalledProcessError as e:
            return handling_ansible_error(e)
    if master:
        if (master_c - master) % 2 == 0:
            return {
                "status": "Fail to scale down",
                "ERROR": "Control plane must be an odd number"
            }
        scale_down_master = [f"master-{n}" for n in range(master_c, master_c - master, -1)]
        try:
            _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "remove_node.yml", "-e", f"node={','.join(scale_down_master)}" ], path=KUBESPRAY_DIR, environment=env)
        except subprocess.CalledProcessError as e:
            return handling_ansible_error(e)

    return {
        "status": "success",
        "scale_down_master": master,
        "scale_down_worker": worker,
        "detail": "Scale down finished successfully"
    }

@mcp.tool(timeout=3600.0)
def remove_cluster(ctx: Context, confirm: bool=False) -> dict:
    """
    Remove cluster, only for removing cluster, if detroy/remove a vms entirely then use detroy_vms tool.
    """
    if not confirm:
        return {
            "status": "fail",
            "cause": "Confirmation required to remove cluster"
        }

    ctx.info("Removing cluster...")
    try:
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "reset.yml", "-e", "reset_confirmation=yes"], path=KUBESPRAY_DIR, environment=env)
    except subprocess.CalledProcessError as e:
        return handling_ansible_error(e)
    
    return {
        "status": "Successfully removed cluster"
    }

if __name__ == "__main__":
    mcp.run()