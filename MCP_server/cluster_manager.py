from fastmcp import FastMCP
import subprocess
from pathlib import Path
from vms_manager import _run_command
# Will implement later
# load_dotenv()
# TOKEN = os.getenv("TOKEN")

mcp = FastMCP(
    "k8s/libvirt",
    instructions="Provides tools for working with cluster and apps deployment. "
        "Start with /home/msi/Vscode/Ansible/My-project/GEMINI.md to get the overview of the structure."
    )

# define the working folder of this file
BASE_DIR = Path(__file__).resolve().parent
# Move up 1 folder
PROJECT_ROOT = BASE_DIR.parent
OPENTOFU_DIR = PROJECT_ROOT / "OpenTofu"
VAR_FILE = OPENTOFU_DIR / "terraform.tfvars.json"
KUBESPRAY_DIR = PROJECT_ROOT / "kubespray"

@mcp.tool()
def create_cluster() -> str:
    """Create cluster using kubespray"""
    try:
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/cluster.yml"], path=KUBESPRAY_DIR)
    except subprocess.CalledProcessError as e:
        return (f"FAIL: {e}\n"
                f"Stdout: {e.stdout}\n"
                f"Stderr: {e.stderr}"
                )
    return "Succesfully created cluster."

if __name__ == "__main__":
    mcp.run()