import subprocess
import psutil
from pathlib import Path
from collections import Counter
from passlib.hash import bcrypt
from getpass import getpass
import json
from typing import Optional
import sys
import os

BASE_DIR = Path(__file__).resolve().parent
# Move up 1 folder
PROJECT_ROOT = BASE_DIR.parent
OPENTOFU_DIR = PROJECT_ROOT / "OpenTofu"
GEMINI_FILE = PROJECT_ROOT / "GEMINI.md"
KUBESPRAY_DIR = PROJECT_ROOT / "kubespray"
def _run_command(args: list, path = None) -> subprocess.CompletedProcess:
    return subprocess.run(
    args,
    cwd=path,
    capture_output=True,
    text=True,
    check=True,
    )

def vms_config() -> str:
    """Collect OpenTofu configuration files and return them with file headers."""
    contents  = []
    files = []

    for d in (OPENTOFU_DIR, OPENTOFU_DIR / "config"):
        for path in sorted(d.glob("*")):
            if path.is_file() and path.suffix in [".tofu", ".py", ".yaml", ".tftpl", ".json"]:
                file_header = f"---START OF FILE: {path.relative_to(PROJECT_ROOT)}---"
                contents.append(f"{file_header}\n{path.read_text(encoding='utf-8')}\n")
                files.append(file_header)
            
            
    return "\n".join(files)

# print(vms_config())
def list_all_vms() -> str:
    """
    Lists all virtual machines (running and stopped) on the host.
    Mimics the output of 'virsh list --all'.
    """
    try:
        # Execute the command on the host system
        print(_run_command(["virsh", "list", "--all"]).stdout)
    except subprocess.CalledProcessError as e:
        return {e.stderr}
        

def check_machine_specs() -> dict:
    """check the machine current availability."""
  
    ram  = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    cpus = psutil.cpu_count(logical=True)

    return {
        "Ram total":      ram.total / to_B,
        "Ram available":  ram.available / to_B,
        "Disk total":     disk.total / to_B,
        "Disk available": disk.free / to_B,
        "cpus available": cpus
    }

VAR_FILE = OPENTOFU_DIR / "terraform.tfvars.json"

to_KB = 1024**2
to_B  = 1024**3
def provision_vms(
    disk_size: float = None,
    master_nodes: int = None,
    master_ram: float = None,
    master_vcpu: int = None,
    worker_nodes: int = None,
    worker_ram: float = None,
    worker_vcpu: int = None,
):
    """Provision VMs using OpenTofu.
    Provision new VMs.
    Only provided values will be changed; others remain at their current state.

    Validation and flow:
    1. validate master/worker counts
    2. estimate RAM, cpu and disk requirements
    3. run tofu init, plan, apply, output
    """

    if not VAR_FILE.exists():
        return "File not exit"
    try:
        config = json.loads(VAR_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "Warning: file was corrupted."

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
    
    VAR_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Success: Configuration updated securely. New state: {json.dumps(config)}")

    if vm_specs["m_nodes"] % 2 == 0 :
        return "Control plane must be an odd number"

    check = check_machine_specs()
    required_ram = vm_specs["m_nodes"] * (vm_specs["m_ram"] / to_KB) + vm_specs["w_nodes"] * (vm_specs["w_ram"] / to_KB)
    required_cpu = vm_specs["m_nodes"] * vm_specs["m_vcpu"] + vm_specs["w_nodes"] * vm_specs["w_vcpu"]
    required_disk = (vm_specs["m_nodes"] + vm_specs["w_nodes"]) * vm_specs["disk"] / to_B
    reserve_ram, reserve_cpu, reserve_disk = 3, 2, 100

    if required_ram + reserve_ram > check["Ram total"]:
        return (
            f"Insufficient RAM: required {required_ram}GB + reserve {reserve_ram}GB, "
            f"available {check["Ram available"]}GB. Reduce node counts or increase host memory."
        )
    if required_cpu + reserve_cpu > check["cpus available"]:
        return (
            f"Insufficient cpu cores: required {required_cpu} cores + reserve {reserve_cpu} cores, "
            f"available {check['cpus available']} cores. Reduce node counts or increase host cpu cores."
        )
    if required_disk + reserve_disk > check["Disk available"]:
        return (
            f"Insufficient disk: required {required_disk}GB + reserve {reserve_disk}GB, "
            f"available {check['Disk available']}GB. Reduce node counts or increase host disk."
        )
    
    else: 
        try: 
            _run_command(["tofu", "init"], path=OPENTOFU_DIR)
            _run_command(["tofu", "plan"], path=OPENTOFU_DIR)
            _run_command(["tofu", "apply", "-auto-approve"], path=OPENTOFU_DIR)
            output = _run_command(["tofu", "output"], path=OPENTOFU_DIR)
        except subprocess.CalledProcessError as e:
            return (f"FAIL: {e}\n{e.stderr}")
        return output.stdout
            
            
#print(provision_vms(disk_size=12, worker_nodes=1, worker_ram=2, master_ram=2, master_nodes=1, master_vcpu=3))

def destroy_vms(confirm: bool = False) -> str:
    """Destroy OpenTofu-managed VMs if confirmation is provided."""
    if not confirm:
        return "Cancelled"

    try:
        result = _run_command(["tofu", "destroy", "-auto-approve"])
    except subprocess.CalledProcessError as e:
        return (f"FAIL: {e}\n{e.stderr}")


    return result.stdout



#print(destroy_vms(True))

def update_vms(
    master_nodes: int = None,
    master_ram: float = None,
    master_vcpu: int = None,
    worker_nodes: int = None,
    worker_ram: float = None,
    worker_vcpu: int = None,
):
    """
    Updates exit VMs.
    Only provided values will be changed; others remain at their current state.
    """
    if not VAR_FILE.exists():
        return {}
    try:
        config = json.loads(VAR_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("Warning: file was corrupted. Starting with an empty config.")
        return {}
    
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
    
    VAR_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Success: Configuration updated securely. New state: {json.dumps(config)}")

    if vm_specs["m_nodes"] % 2 == 0:
        return "Control plane must be an odd number"

    check = check_machine_specs()
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
        return (
            f"Insufficient RAM: need {delta_ram}GB extra + {reserve_ram}GB reserve, "
            f"only {check['Ram available']}GB free. Reduce nodes or increase host memory."
        )
    if delta_cpu + reserve_cpu > check["cpus available"]:
        return (
            f"Insufficient CPU: need {delta_cpu} cores extra + {reserve_cpu} reserve, "
            f"only {check['cpus available']} cores free. Reduce nodes or increase host CPUs."
        )
    else: 
        try:
            _run_command(["tofu", "init"])
            _run_command(["tofu", "plan"])
            _run_command(["tofu", "apply", "-auto-approve"])
            output = _run_command(["tofu", "output"])
        except subprocess.CalledProcessError as e:
            try: 
                _run_command(["tofu", "apply", "-auto-approve"])
                output = _run_command(["tofu", "output"])
            except subprocess.CalledProcessError as e:
                return (f"FAIL: {e}\n{e.stderr}")

        return output.stdout
#print(update_vms(worker_nodes=1, worker_ram=2, master_ram=2, master_nodes=1, master_vcpu=2))    
# hashed_password = "$2b$13$9TUMcvNscgdeLCNlCRrT..zVbAjzVYDtQh0PpaOTlunU7xertbOCa"
# def verify_access() -> str:
#     """Always ask for password if user want to manage cluster"""
#     tries = 0
#     max_tries = 3
#     while tries < max_tries:
#         password = getpass()
#         if (bcrypt.verify(password, hashed_password)):
#             return "Success"
#         tries += 1
#     return "Too many failed attempts. Access Denied."

# def destroy_vms():
#     verify_access()
#     n = str(input("Are you sure you want to delete all the vms? y/n\n"))
#     if (n.lower() == "y"):
#         try:
#             destroy = subprocess.run(["tofu", "destroy", "-auto-approve"], cwd=OPENTOFU_DIR, check=True)
#         except subprocess.CalledProcessError as e:
#             return e.stderr
#         return destroy.stdout
#     else: return "Cancelled"

# print(destroy_vms())

def create_cluster() -> str:
    """Create cluster using kubespray"""
    try:
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/cluster.yml"], path="/home/msi/Vscode/Ansible/My-project/kubespray/.venv")
    except subprocess.CalledProcessError as e:
        return (f"FAIL: {e}\n"
                f"{e.stdout}\n"
                f"{e.stderr}"
                )
    return "Succesfully created cluster."
print(create_cluster())
