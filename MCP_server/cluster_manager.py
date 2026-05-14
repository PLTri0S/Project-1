from fastmcp import FastMCP, Context
import subprocess
from pathlib import Path
from vms_manager import _run_command
import os
import time

mcp = FastMCP(
    "k8s/libvirt",
    instructions="Provides tools for working with cluster and apps deployment. "
        "Start with /home/msi/Vscode/Ansible/My-project/GEMINI.md to get the overview of the structure."
    )

# define the working folder of this file
BASE_DIR = Path(__file__).resolve().parent
# Move up 1 folder
PROJECT_ROOT = BASE_DIR.parent
KUBESPRAY_DIR = PROJECT_ROOT / "kubespray"

@mcp.tool(timeout=3600.0)
def deploy_cluster(ctx: Context) -> dict:
    """
    Create cluster using kubespray.
    Running playbook required in kubespray environment.
    """
    ctx.info("Prepare to deploy cluster...")
    uid_gid = f"{os.getuid()}:{os.getgid()}"
    KUBESPRAY_VENV = KUBESPRAY_DIR / ".venv"

    env = os.environ.copy()
    env["VIRTUAL_ENV"] = KUBESPRAY_VENV
    env["PATH"] = f"{KUBESPRAY_VENV}/bin:{env['PATH']}"
    env.pop("PYTHONHOME", None)
    
    # wait about 60s to complete setting up the vms
    time.sleep(60)

    try:
        ctx.info("Deploying cluster...")
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "cluster.yml"], path=KUBESPRAY_DIR, environment=env)
        ctx.info("fixing clilium error...")
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/cilium_error_fix.yml"], path=KUBESPRAY_DIR, environment=env)
        ctx.info("Add config to host machie...")
        time.sleep(60) # wait 60s to finish setting up cluster
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/setup_kubeconfig.yml"], path=KUBESPRAY_DIR, environment=env)

        # _run_command(["sudo", "chown", uid_gid, "home/msi/.kube/config"])
    except subprocess.CalledProcessError as e:
        return {
            "status": "fail",
            "command": e.cmd,
            "error code": e.returncode,
            "cause": e.stderr
        }
    
    return {
        "status": "Succesfully created cluster"
        }

def scale_cluster() -> str:
    return

def delete_cluster() -> str:
    return


if __name__ == "__main__":
    mcp.run()