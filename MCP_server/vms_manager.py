from fastmcp import FastMCP, Context
import subprocess
import psutil
from pathlib import Path
import json

mcp = FastMCP(
    "k8s/libvirt",
    instructions="Provides tools for provisioning VMs. "
        "Start with /home/msi/Vscode/Ansible/My-project/GEMINI.md to get the overview of the structure."
    )

# define the working folder of this file
BASE_DIR = Path(__file__).resolve().parent
# Move up 1 folder
PROJECT_ROOT = BASE_DIR.parent
GEMINI_FILE  = PROJECT_ROOT / "GEMINI.md"
GUIDE_FILE = PROJECT_ROOT / "Kubespray_VM_Provisioning_Guide.md"
OPENTOFU_DIR = PROJECT_ROOT / "OpenTofu"
VAR_FILE = OPENTOFU_DIR / "terraform.tfvars.json"
KUBESPRAY_DIR = PROJECT_ROOT / "kubespray"

to_KB = 1024**2
to_B  = 1024**3
#helper function
def _run_command(args: list, path = None, environment = None) -> subprocess.CompletedProcess:
    return subprocess.run(
    args,
    cwd=path,
    env=environment,
    capture_output=True,
    text=True,
    check=True, 
    )

#function to check the machine's specs of the host machine
def check_machine_specs(ctx: Context) -> dict:
    """check the machine current availability."""
  
    ram  = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    cpus = psutil.cpu_count(logical=True)

    ctx.info("Getting host specs...")

    return {
        "Status": "Complete",
        "Ram total": round(ram.total / to_B),
        "Ram available": round(ram.available / to_B),
        "Disk total": round(disk.total / to_B),
        "Disk available": round(disk.free / to_B),
        "cpus available": cpus
    }

@mcp.resource("internal://rules")
def read_rules() -> str:
    """Read the following GEMINI.md"""
    return GEMINI_FILE.read_text(encoding="utf-8")

@mcp.resource("infra://kubespray-vm-provisioning")
def read_info() -> str:
    """Collect information for provisioning VMs and creating cluster."""                   
    return GUIDE_FILE.read_text(encoding="utf-8")

@mcp.tool()
def provision_vms(
    ctx: Context,
    disk_size: float = None,
    master_nodes: int = None,
    master_ram: float = None,
    master_vcpu: int = None,
    worker_nodes: int = None,
    worker_ram: float = None,
    worker_vcpu: int = None,
) -> dict:
    """Provision VMs using OpenTofu.
    Provision new VMs.
    Only provided values will be changed; others remain at their current state.
    Input are all in GB.

    Validation and flow:
    1. validate master/worker counts
    2. estimate RAM, cpu and disk requirements
    3. run tofu init, plan, apply, output
    """

    if not VAR_FILE.exists():
        return {
            "Error": "File not exit."
        }
    try:
        config = json.loads(VAR_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "Error": "File was corrupted."
        }
    
    vm_specs = {
        "disk":    config["volume_config"]["size"],
        "m_nodes": config["Master_config"]["nodes"],
        "m_ram":   config["Master_config"]["ram"],
        "m_vcpu":  config["Master_config"]["vcpu"],
        "w_nodes": config["Worker_config"]["nodes"],
        "w_ram":   config["Worker_config"]["ram"],
        "w_vcpu":  config["Worker_config"]["vcpu"],
    }

    if disk_size is not None:    vm_specs["disk"]    = disk_size * to_B
    if master_nodes is not None: vm_specs["m_nodes"] = master_nodes
    if master_ram is not None:   vm_specs["m_ram"]   = master_ram * to_KB 
    if master_vcpu is not None:  vm_specs["m_vcpu"]  = master_vcpu 
    if worker_nodes is not None: vm_specs["w_nodes"] = worker_nodes
    if worker_ram is not None:   vm_specs["w_ram"]   = worker_ram * to_KB
    if worker_vcpu is not None:  vm_specs["w_vcpu"]  = worker_vcpu 

    config["volume_config"]["size"]  = vm_specs["disk"]
    config["Master_config"]["nodes"] = vm_specs["m_nodes"]
    config["Master_config"]["ram"]   = vm_specs["m_ram"]
    config["Master_config"]["vcpu"]  = vm_specs["m_vcpu"]
    config["Worker_config"]["nodes"] = vm_specs["w_nodes"]
    config["Worker_config"]["ram"]   = vm_specs["w_ram"]
    config["Worker_config"]["vcpu"]  = vm_specs["w_vcpu"]

    ctx.info("Checking systems requiremnt...")

    if vm_specs["m_nodes"] % 2 == 0 :
        return {
            "status": "Fail to provision VMs",
            "ERROR": "Control plane must be an odd number"
        }

    check = check_machine_specs(ctx)
    required_ram = vm_specs["m_nodes"] * (vm_specs["m_ram"] / to_KB) + vm_specs["w_nodes"] * (vm_specs["w_ram"] / to_KB)
    required_cpu = vm_specs["m_nodes"] * vm_specs["m_vcpu"] + vm_specs["w_nodes"] * vm_specs["w_vcpu"]
    required_disk = (vm_specs["m_nodes"] + vm_specs["w_nodes"]) * vm_specs["disk"] / to_B
    reserve_ram, reserve_cpu, reserve_disk = 3, 2, 100

    if required_ram + reserve_ram > check["Ram available"]:
        return {
            "status": "Fail",
            "error": {
                "Insufficient RAM": f"required {required_ram}GB + reserve {reserve_ram}GB",
                "Available":  f"{round(check["Ram available"])}GB.", 
            },

            "Fix": "Reduce node counts or memory."
        }
    if required_cpu + reserve_cpu > check["cpus available"]:
        return {
            "status": "Fail",
            "error": {
                "Insufficient CPUs": f"required {required_cpu} cores + reserve {reserve_cpu} cores",
                "Available":  f"{check['cpus available']} cores.", 
            },

            "Fix": "Reduce node counts or cpu cores."
        }
    if required_disk + reserve_disk > check["Disk available"]:
        return {
            "status": "Fail",
            "error": {
                "Insufficient disk": f"required {required_disk}GB + reserve {reserve_disk}GB",
                "Available":  f"{round(check['Disk available'])}GB.", 
            },

            "Fix": "Reduce node counts or disk."
        }        

    VAR_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")     

    ctx.info("Prepare to provision VMs")

    try:
        _run_command(["tofu", "init"], path=OPENTOFU_DIR)
        _run_command(["tofu", "plan"], path=OPENTOFU_DIR)
        ctx.info("Provisioning VMs...")
        _run_command(["tofu", "apply", "-auto-approve"], path=OPENTOFU_DIR)
        ips = _run_command(["tofu", "output", "-json"], path=OPENTOFU_DIR)
    except subprocess.CalledProcessError as e:
        return {
            "status": "fail",
            "command": e.cmd,
            "error code": e.returncode,
            "cause": e.stderr
        }
    
    return {
        "state": "Success",
        "disk size": f"{vm_specs["disk"] / to_B}GB",

        "Master": {
            "nodes count": vm_specs["m_nodes"],
            "ram": f"{vm_specs["m_ram"] / to_KB}GB",
            "cpus": vm_specs["m_vcpu"],
        },

        "Worker": {
            "nodes count": vm_specs["w_nodes"],
            "ram": f"{vm_specs["w_ram"] / to_KB}GB",
            "cpus": vm_specs["w_vcpu"],
        },

        "IPS": json.loads(ips.stdout)["IPS"]["value"]
    }

@mcp.tool()
def destroy_vms(confirm: bool = False) -> dict:
    """Destroy OpenTofu-managed VMs if confirmation is provided."""
    if not confirm:
        return "Cancelled"

    try:
        _run_command(["tofu", "destroy", "-auto-approve"], path=OPENTOFU_DIR)
    except subprocess.CalledProcessError as e:
        return {
            "status": "fail",
            "command": e.cmd,
            "error code": e.returncode,
            "cause": e.stderr
        }

    return {
        "status": "success"
    }

@mcp.tool()
def update_vms(
    ctx: Context,
    master_nodes: int = None,
    master_ram: float = None,
    master_vcpu: int = None,
    worker_nodes: int = None,
    worker_ram: float = None,
    worker_vcpu: int = None,
) -> dict:
    """
    Updates exit VMs.
    Only provided values will be changed; others remain at their current state.
    Input are all in GB.

    """
    if not VAR_FILE.exists():
        return {
            "Error": "File not exit."
        }
    try:
        config = json.loads(VAR_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "Error": "File was corrupted."
        }
    
# --- capture OLD specs before overwriting ---
    old_specs = {
        "disk":    config["volume_config"]["size"],
        "m_nodes": config["Master_config"]["nodes"],
        "m_ram":   config["Master_config"]["ram"],
        "m_vcpu":  config["Master_config"]["vcpu"],
        "w_nodes": config["Worker_config"]["nodes"],
        "w_ram":   config["Worker_config"]["ram"],
        "w_vcpu":  config["Worker_config"]["vcpu"],
    }

    vm_specs = {
        "disk":    config["volume_config"]["size"],
        "m_nodes": config["Master_config"]["nodes"],
        "m_ram":   config["Master_config"]["ram"],
        "m_vcpu":  config["Master_config"]["vcpu"],
        "w_nodes": config["Worker_config"]["nodes"],
        "w_ram":   config["Worker_config"]["ram"],
        "w_vcpu":  config["Worker_config"]["vcpu"],
    }

    if master_nodes is not None: vm_specs["m_nodes"] = master_nodes
    if master_ram is not None:   vm_specs["m_ram"]   = master_ram * to_KB 
    if master_vcpu is not None:  vm_specs["m_vcpu"]  = master_vcpu 
    if worker_nodes is not None: vm_specs["w_nodes"] = worker_nodes
    if worker_ram is not None:   vm_specs["w_ram"]   = worker_ram * to_KB
    if worker_vcpu is not None:  vm_specs["w_vcpu"]  = worker_vcpu 

    config["Master_config"]["nodes"] = vm_specs["m_nodes"]
    config["Master_config"]["ram"]   = vm_specs["m_ram"]
    config["Master_config"]["vcpu"]  = vm_specs["m_vcpu"]
    config["Worker_config"]["nodes"] = vm_specs["w_nodes"]
    config["Worker_config"]["ram"]   = vm_specs["w_ram"]
    config["Worker_config"]["vcpu"]  = vm_specs["w_vcpu"]
    
    ctx.info("Checking systems requiremnt...")

    if vm_specs["m_nodes"] % 2 == 0:
        return {
            "status": "Fail to provision VMs",
            "ERROR": "Control plane must be an odd number"
        }

    check = check_machine_specs(ctx)
    # --- compute OLD allocation ---
    old_ram  = old_specs["m_nodes"] * (old_specs["m_ram"]  / to_KB) + old_specs["w_nodes"] * (old_specs["w_ram"]  / to_KB)
    old_cpu  = old_specs["m_nodes"] *  old_specs["m_vcpu"] + old_specs["w_nodes"] *  old_specs["w_vcpu"]

    # --- compute NEW allocation ---
    new_ram  = vm_specs["m_nodes"] * (vm_specs["m_ram"]  / to_KB) + vm_specs["w_nodes"] * (vm_specs["w_ram"]  / to_KB)
    new_cpu  = vm_specs["m_nodes"] *  vm_specs["m_vcpu"] + vm_specs["w_nodes"] *  vm_specs["w_vcpu"]

    # --- only the DELTA needs to fit in available headroom ---
    delta_ram  = new_ram  - old_ram
    delta_cpu  = new_cpu  - old_cpu

    reserve_ram, reserve_cpu = 3, 2

    if delta_ram + reserve_ram > check["Ram available"]:
        return {
            "status": "Fail",
            "error": {
                "Insufficient RAM": f"required {delta_ram}GB + reserve {reserve_ram}GB",
                "Available":  f"{round(check["Ram available"])}GB.", 
            },

            "Fix": "Reduce node counts or memory."
        }
    if delta_cpu + reserve_cpu > check["cpus available"]:
        return {
            "status": "Fail",
            "error": {
                "Insufficient CPUs": f"required {delta_cpu} cores + reserve {reserve_cpu} cores",
                "Available":  f"{check['cpus available']} cores.", 
            },

            "Fix": "Reduce node counts or cpu cores."
        }

    VAR_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    ctx.info("Prepare to provision VMs")

    try:
        _run_command(["tofu", "init"], path=OPENTOFU_DIR)
        _run_command(["tofu", "plan"], path=OPENTOFU_DIR)
        _run_command(["tofu", "apply", "-auto-approve"], path=OPENTOFU_DIR)
        ips = _run_command(["tofu", "output", "-json"], path=OPENTOFU_DIR)
    except subprocess.CalledProcessError as e:
        # Run again to reset the uuid to each vms in order to work
        try: 
            ctx.info("Provisioning VMs...")
            _run_command(["tofu", "apply", "-auto-approve"], path=OPENTOFU_DIR)
            ips = _run_command(["tofu", "output", "-json"], path=OPENTOFU_DIR)
        except subprocess.CalledProcessError as e:
            return {
                "status": "fail",
                "command": e.cmd,
                "error code": e.returncode,
                "cause": e.stderr
            }

    return {
        "state": "Success",
        "disk size": f"{vm_specs["disk"] / to_B}GB",

        "Master": {
            "nodes count": vm_specs["m_nodes"],
            "ram": f"{vm_specs["m_ram"] / to_KB}GB",
            "cpus": vm_specs["m_vcpu"],
        },

        "Worker": {
            "nodes count": vm_specs["w_nodes"],
            "ram": f"{vm_specs["w_ram"] / to_KB}GB",
            "cpus": vm_specs["w_vcpu"],
        },

        "IPS": json.loads(ips.stdout)["IPS"]["value"]
    }

if __name__ == "__main__":
    mcp.run()