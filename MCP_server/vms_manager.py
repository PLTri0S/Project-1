from fastmcp import FastMCP, Context
import subprocess
import psutil
from pathlib import Path
import json
import re
import os

mcp = FastMCP(
    "k8s/libvirt",
    instructions="Provides tools for provisioning VMs. "
        "Start with GEMINI.md to get the overview of the structure."
    )

# define the working folder of this file
BASE_DIR = Path(__file__).resolve().parent
# Move up 1 folder
PROJECT_ROOT = BASE_DIR.parent
GEMINI_FILE  = PROJECT_ROOT / "GEMINI.md"
SPECS_FILE = PROJECT_ROOT / "Vms_specs.md"
KNOWN_ISSUE_FILE  = PROJECT_ROOT / "Kubespray_VM_Provisioning_Guide"
OPENTOFU_DIR = PROJECT_ROOT / "OpenTofu"
VAR_FILE = OPENTOFU_DIR / "terraform.tfvars.json"
KUBESPRAY_DIR = PROJECT_ROOT / "kubespray"

KB = 1024**2
B  = 1024**3
#helper function
def _run_command(args: list, path = None, environment = None, timeout=None) -> subprocess.CompletedProcess:
    return subprocess.run(
    args,
    cwd=path,
    env=environment,
    capture_output=True,
    text=True,
    check=True, 
    timeout=timeout
    )

#function to check the machine's specs of the host machine
@mcp.tool()
def check_machine_specs(ctx: Context) -> dict:
    """check the machine current availability."""
  
    ram  = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    cpus = psutil.cpu_count(logical=True)

    ctx.info("Getting host specs...")
    
    return {
        "Status": "Complete",
        "Ram total": f"{round(ram.total / B)}GB",
        "Ram available": f"{round(ram.available / B)}GB",
        "Disk total": f"{round(disk.total / B)}GB",
        "Disk free": f"{round(disk.free / B)}GB",
        "cpus available": f"{cpus} cores"
    }

@mcp.resource("internal://rules")
def read_rules() -> str:
    """Read the following GEMINI.md"""
    return GEMINI_FILE.read_text(encoding="utf-8")



@mcp.resource("infra://vm-provisioning")
def read_info() -> str:
    """Collect information vms specs to create vms for creating cluster later."""                   
    return SPECS_FILE.read_text(encoding="utf-8")

@mcp.resource("infra://known-issue")
def read_issue() -> str:
    """Collect information for know issue and possible fix."""                   
    return KNOWN_ISSUE_FILE.read_text(encoding="utf-8")

@mcp.tool()
def check_current_vms_specs():
    """Collect information about current vms specs."""                   
    return json.loads(VAR_FILE.read_text(encoding="utf-8"))

@mcp.tool()
def list_vms() -> dict:
    """List all Vms to check their state"""
    count_run = 0
    count_off = 0
    try:
        status = _run_command(["virsh", "list", "--all"])
        for line in status.stdout.splitlines():
            match_run = re.search(r"running", line)
            match_off = re.search(r"shut off", line)
            if match_run:
                count_run += 1
            elif match_off:
                count_off += 1
        return {
            "Status": "Success",
            "State": {
                "running": count_run,
                "shut off": count_off
            }
        }
            
    except subprocess.CalledProcessError as e:
        return {
            "Status": "Failed",
            "Error code": e.returncode,
            "Causes": e.stderr
        }
   
@mcp.tool()
def start_and_stop_vms(start: bool = False, shutoff: bool = False) -> dict:
    """If there are any shut off or running vms, ask the user if they want to start it or shut off it"""
    try:
        cmd = _run_command(["virsh", "list", "--all"]) 
        for line in cmd.stdout.splitlines():
            if start:
                #print(line)
                match_name = re.search(r"(\w+-\d+)\s+shut off", line)
                if match_name: 
                    _run_command(["virsh", "start", match_name.group(1)])
            elif shutoff:
                match_name = re.search(r"(\w+-\d+)\s+running", line)
                if match_name: 
                    _run_command(["virsh", "shutdown", match_name.group(1)])
        return {
            "Status": "Success"
        }
    except subprocess.CalledProcessError as e:
        return {
            "Status": "Failed",
            "Error code": e.returncode,
            "Causes": e.stderr
        }

@mcp.tool()
def provision_vms(
    ctx: Context,
    disk_size: float,
    master_nodes: int,
    master_ram: float,
    master_vcpu: int,
    worker_nodes: int,
    worker_ram: float,
    worker_vcpu: int,
) -> dict:
    """Provision VMs using OpenTofu.
    Provision new VMs.
    Only created if there are currently no VMs in running or shutoff state as list in list_vms tool
    Input are all in GB.

    Validation and flow:
    1. validate master/worker counts
    2. estimate RAM, cpu and disk requirements
    3. run tofu init, plan, apply, output
    """

    config = json.loads(VAR_FILE.read_text(encoding="utf-8"))

    # Convert GB inputs to Bytes (for disk) and KiB (for RAM)
    config["volume_config"]["size"]  = disk_size * B
    config["Master_config"]["nodes"] = master_nodes
    config["Master_config"]["ram"]   = master_ram * KB
    config["Master_config"]["vcpu"]  = master_vcpu
    config["Worker_config"]["nodes"] = worker_nodes
    config["Worker_config"]["ram"]   = worker_ram * KB
    config["Worker_config"]["vcpu"]  = worker_vcpu

    ctx.info("Checking systems requiremnt...")


    if master_nodes % 2 == 0 :
        return {
            "status": "Fail to provision VMs",
            "ERROR": "Control plane must be an odd number"
        }

    ram_free  = round(psutil.virtual_memory().available / B)
    disk_free = round(psutil.disk_usage('/').free / B)
    cpus_free = psutil.cpu_count(logical=True)

    required_ram = master_nodes * master_ram + worker_nodes * worker_ram
    required_cpu = master_nodes * master_vcpu + worker_nodes * worker_vcpu
    required_disk = (master_nodes + worker_nodes) * disk_size
    reserve_ram, reserve_cpu, reserve_disk = 3, 2, 50

    if required_ram + reserve_ram > ram_free:
        return {
            "status": "Fail",
            "error": {
                "Insufficient RAM": f"required {required_ram}GB + reserve {reserve_ram}GB",
                "Available":  f"{ram_free}GB.", 
            },

            "Fix": "Reduce node counts or memory."
        }
    if required_cpu + reserve_cpu > cpus_free:
        return {
            "status": "Fail",
            "error": {
                "Insufficient CPUs": f"required {required_cpu} cores + reserve {reserve_cpu} cores",
                "Available":  f"{cpus_free} cores.", 
            },

            "Fix": "Reduce node counts or cpu cores."
        }
    if required_disk + reserve_disk > disk_free:
        return {
            "status": "Fail",
            "error": {
                "Insufficient disk": f"required {required_disk}GB + reserve {reserve_disk}GB",
                "Available":  f"{disk_free}GB.", 
            },

            "Fix": "Reduce node counts or disk."
        }        

    VAR_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")     

    ctx.info("Prepare to provision VMs")

    try:
        _run_command(["tofu", "init", "-no-color"], path=OPENTOFU_DIR), 
        ctx.info("Provisioning VMs...")
        _run_command(["tofu", "apply", "-auto-approve", "-no-color"], path=OPENTOFU_DIR)
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
        "disk size": f"{disk_size}GB",

        "Master": {
            "nodes count": master_nodes,
            "ram": f"{master_ram}GB",
            "cpus": master_vcpu,
        },

        "Worker": {
            "nodes count": worker_nodes,
            "ram": f"{worker_ram}GB",
            "cpus": worker_vcpu,
        },

        "IPS": json.loads(ips.stdout)["IPS"]["value"]
    }

@mcp.tool()
def destroy_vms(confirm: bool = False) -> dict:
    """Destroy OpenTofu-managed VMs if confirmation is provided."""
    if not confirm:
        return {
            "status": "Failed",
            "Error": "Process was cancelled"
        }

    try:
        _run_command(["tofu", "destroy", "-auto-approve", "-no-color"], path=OPENTOFU_DIR)
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
    config = json.loads(VAR_FILE.read_text(encoding="utf-8"))

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
    if master_ram is not None:   vm_specs["m_ram"]   = master_ram * KB 
    if master_vcpu is not None:  vm_specs["m_vcpu"]  = master_vcpu 
    if worker_nodes is not None: vm_specs["w_nodes"] = worker_nodes
    if worker_ram is not None:   vm_specs["w_ram"]   = worker_ram * KB
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

    ram_free  = round(psutil.virtual_memory().available / B)
    disk_free = round(psutil.disk_usage('/').free / B)
    cpus_free = psutil.cpu_count(logical=True)

    # --- compute OLD allocation ---
    old_ram  = old_specs["m_nodes"] * (old_specs["m_ram"]  / KB) + old_specs["w_nodes"] * (old_specs["w_ram"]  / KB)
    old_cpu  = old_specs["m_nodes"] *  old_specs["m_vcpu"] + old_specs["w_nodes"] *  old_specs["w_vcpu"]

    # --- compute NEW allocation ---
    new_ram  = vm_specs["m_nodes"] * (vm_specs["m_ram"]  / KB) + vm_specs["w_nodes"] * (vm_specs["w_ram"]  / KB)
    new_cpu  = vm_specs["m_nodes"] *  vm_specs["m_vcpu"] + vm_specs["w_nodes"] *  vm_specs["w_vcpu"]

    # --- only the DELTA needs to fit in available headroom ---
    delta_ram  = new_ram  - old_ram
    delta_cpu  = new_cpu  - old_cpu

    reserve_ram, reserve_cpu = 3, 2

    if delta_ram + reserve_ram > ram_free:
        return {
            "status": "Fail",
            "error": {
                "Insufficient RAM": f"required {delta_ram}GB + reserve {reserve_ram}GB",
                "Available":  f"{ram_free}GB.", 
            },

            "Fix": "Reduce node counts or memory."
        }
    if delta_cpu + reserve_cpu > cpus_free:
        return {
            "status": "Fail",
            "error": {
                "Insufficient CPUs": f"required {delta_cpu} cores + reserve {reserve_cpu} cores",
                "Available":  f"{cpus_free} cores.", 
            },

            "Fix": "Reduce node counts or cpu cores."
        }

    VAR_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    ctx.info("Prepare to provision VMs")

    try:
        _run_command(["tofu", "init", "-no-color"], path=OPENTOFU_DIR)
        _run_command(["tofu", "apply", "-auto-approve", "-no-color"], path=OPENTOFU_DIR)
        ips = _run_command(["tofu", "output", "-json"], path=OPENTOFU_DIR)
    except subprocess.CalledProcessError as e:
        # Run again to reset the uuid to each vms in order to work
        try: 
            ctx.info("Provisioning VMs...")
            _run_command(["tofu", "apply", "-auto-approve", "-no-color"], path=OPENTOFU_DIR)
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
        "disk size": f"{vm_specs["disk"] / B}GB",

        "Master": {
            "nodes count": vm_specs["m_nodes"],
            "ram": f"{vm_specs["m_ram"] / KB}GB",
            "cpus": vm_specs["m_vcpu"],
        },

        "Worker": {
            "nodes count": vm_specs["w_nodes"],
            "ram": f"{vm_specs["w_ram"] / KB}GB",
            "cpus": vm_specs["w_vcpu"],
        },

        "IPS": json.loads(ips.stdout)["IPS"]["value"]
    }

if __name__ == "__main__":
    mcp.run()