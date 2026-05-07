from fastmcp import FastMCP
import subprocess
from pathlib import Path
from vms_manager import _run_command
import os

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
def deploy_cluster() -> str:
    """
    Create cluster using kubespray.
    Running playbook required in kubespray environment.
    """
    uid_gid = f"{os.getuid()}:{os.getgid()}"
    KUBESPRAY_VENV = KUBESPRAY_DIR / ".venv"

    env = os.environ.copy()
    env["VIRTUAL_ENV"] = KUBESPRAY_VENV
    env["PATH"] = f"{KUBESPRAY_VENV}/bin:{env['PATH']}"
    env.pop("PYTHONHOME", None)

    try:
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "cluster.yml"], path=KUBESPRAY_DIR, environment=env)
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/cilium_error_fix.yml"], path=KUBESPRAY_DIR, environment=env)
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/setup_kubeconfig.yml"], path=KUBESPRAY_DIR, environment=env)

        # _run_command(["sudo", "chown", uid_gid, "home/msi/.kube/config"])
    except subprocess.CalledProcessError as e:
        return (f"FAIL: {e}\n"
                f"{e.stdout}\n"
                f"{e.stderr}"
                )
    return "Succesfully created cluster."

if __name__ == "__main__":
    mcp.run()