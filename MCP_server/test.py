import subprocess
import psutil
from pathlib import Path
from getpass import getpass
import json
from ruamel.yaml import YAML
import os
import re

KB = 1024**2
B  = 1024**3

BASE_DIR = Path(__file__).resolve().parent
# Move up 1 folder
PROJECT_ROOT = BASE_DIR.parent
OPENTOFU_DIR = PROJECT_ROOT / "OpenTofu"
GEMINI_FILE = PROJECT_ROOT / "GEMINI.md"
GUIDE_FILE = PROJECT_ROOT / "Kubespray_VM_Provisioning_Guide.md"
KUBESPRAY_DIR = PROJECT_ROOT / "kubespray"
NETWORK_PLUGIN = KUBESPRAY_DIR / "inventory" / "mycluster" / "group_vars" / "k8s_cluster" / "k8s-cluster.yml"
WEB_SERVER = PROJECT_ROOT / "web_server"

VAR_FILE = OPENTOFU_DIR / "terraform.tfvars.json"

KUBESPRAY_VENV = KUBESPRAY_DIR / ".venv"
env = os.environ.copy()
env["VIRTUAL_ENV"] = KUBESPRAY_VENV
env["PATH"] = f"{KUBESPRAY_VENV}/bin:{env['PATH']}"
env.pop("PYTHONHOME", None)
def _run_command(args: list, path = None, environment= None, timeout=None) -> subprocess.CompletedProcess:
    return subprocess.run(
    args,
    cwd=path,
    env=environment,
    capture_output=True,   
    text=True,
    check=True,
    timeout=timeout
    )

# def vms_config() -> str:
#     """Collect OpenTofu configuration files and return them with file headers."""
#     contents  = []
#     files = []

#     for d in (OPENTOFU_DIR, OPENTOFU_DIR / "config"):
#         for path in sorted(d.glob("*")):
#             if path.is_file() and path.suffix in [".tofu", ".py", ".yaml", ".tftpl", ".json"]:
#                 file_header = f"---START OF FILE: {path.relative_to(PROJECT_ROOT)}---"
#                 contents.append(f"{file_header}\n{path.read_text(encoding='utf-8')}\n")
#                 files.append(file_header)
            
            
#     return "\n".join(files)

def read_info() -> str:
    """Collect information for provisioning VMs and creating cluster."""                   
    return GUIDE_FILE.read_text(encoding="utf-8")

#print(read_info())

# print(vms_config())
def list_vms() -> dict:
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
#print(list_vms())

def start_and_stop_vms(start: bool = False, shutoff: bool = False) -> dict:

    try:
        cmd = _run_command(["virsh", "list", "--all"]) 
        for line in cmd.stdout.splitlines():
            if start:
                #print(line)
                match_name = re.search(r"(\w+-\d+)\s+shut off", line)
                if match_name: 
                    #print(match_name.group(1))
                    _run_command(["virsh", "start", match_name.group(1)])
            elif shutoff:
                match_name = re.search(r"(\w+-\d+)\s+running", line)
                if match_name: 
                    #print(match_name.group(1))
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
#print(start_and_stop_vms(start=True))     
           
def check_machine_specs() -> dict:
    """check the machine current availability."""
  
    ram  = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    cpus = psutil.cpu_count(logical=True)

    return {
        "Ram total":      f"{round(ram.total / B)}GB",
        "Disk total":     f"{round(disk.total / B)}GB",
        "cpus available": f"{cpus} cores" 
    }
#print(check_machine_specs())

def provision_vms(
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
    Only provided values will be changed; others remain at their current state.
    Input are all in GB.

    Validation and flow:
    1. validate master/worker counts
    2. estimate RAM, cpu and disk requirements
    3. run tofu init, plan, apply, output
    """
    ram_free  = round(psutil.virtual_memory().available / B)
    disk_free = round(psutil.disk_usage('/').free / B)
    cpus_free = psutil.cpu_count(logical=True)

    config = json.loads(VAR_FILE.read_text(encoding="utf-8"))

    config["volume_config"]["size"]  = disk_size *B
    config["Master_config"]["nodes"] = master_nodes 
    config["Master_config"]["ram"]   = master_ram * KB
    config["Master_config"]["vcpu"]  = master_vcpu
    config["Worker_config"]["nodes"] = worker_nodes
    config["Worker_config"]["ram"]   = worker_ram *KB
    config["Worker_config"]["vcpu"]  = worker_vcpu

    if master_nodes % 2 == 0 :
        return {
            "status": "Fail to provision VMs",
            "ERROR": "Control plane must be an odd number"
        }

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

    try:
        _run_command(["tofu", "init", "-no-color"], path=OPENTOFU_DIR)
        _run_command(["tofu", "plan", "-no-color"], path=OPENTOFU_DIR)
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
               
#print(provision_vms(disk_size=10, worker_nodes=2, worker_ram=2, master_ram=3, master_nodes=1, master_vcpu=2, worker_vcpu=2))

def destroy_vms(confirm: bool = False) -> str:
    """Destroy OpenTofu-managed VMs if confirmation is provided."""
    if not confirm:
        return "Cancelled"

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
        "status": "Destroy Successfully"
    }

#print(destroy_vms(confirm=True))

def update_vms(
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
    ram_free  = round(psutil.virtual_memory().available / B)
    disk_free = round(psutil.disk_usage('/').free / B)
    cpus_free = psutil.cpu_count(logical=True)

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
    
    if vm_specs["m_nodes"] % 2 == 0:
        return {
            "status": "Fail to provision VMs",
            "ERROR": "Control plane must be an odd number"
        }

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

    try:
        _run_command(["tofu", "init", "-no-color"], path=OPENTOFU_DIR)
        _run_command(["tofu", "plan", "-no-color"], path=OPENTOFU_DIR)
        _run_command(["tofu", "apply", "-auto-approve", "-no-color"], path=OPENTOFU_DIR)
        ips = _run_command(["tofu", "output", "-json"], path=OPENTOFU_DIR)
    except subprocess.CalledProcessError as e:
        # Run again to reset the uuid to each vms in order to work
        try: 
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

#print(update_vms(worker_nodes=2, worker_ram=2, worker_vcpu=2, master_nodes=1, master_ram=3, master_vcpu=2))    

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

def handling_ansible_error(error: str) -> dict:
        error_dict = {}
        count = 1
        for line in error.stdout.splitlines():
            target_node = re.search(r"(fatal:\s)(\D+\d\D+!)|\D+\d\D+!", line)
            msg = re.search(r"(msg\"\:\s)(\"\D+\d|\D+)",line)
            task = re.search(r"(TASK\s)(\D+[^\s*])", line)
            Task_error = False

            if target_node:
                error_dict[f"node-{count}"] = target_node.group(2) or target_node.group()
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
def deploy_cluster(network: str) -> dict:
    """
    Create cluster using kubespray.
    Running playbook required in kubespray environment
    Choose network plugin (cilium, calico, kube-ovn or flannel. Use cni for generic cni plugin).
    """
    #uid_gid = f"{os.getuid()}:{os.getgid()}"

    yaml = YAML()
    yaml.preserve_quotes = True

    with open(NETWORK_PLUGIN, "r") as file:
        data = yaml.load(file)

    data["kube_network_plugin"] = network
    with open(NETWORK_PLUGIN, "w") as file:
        yaml.dump(data, file)

    try:
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "cluster.yml"], path=KUBESPRAY_DIR, environment=env)
        # Only run this command if using cilium network plugin
        if network == "cilium":
            _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/cilium_error_fix.yml"], path=KUBESPRAY_DIR, environment=env)
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "playbooks/setup_kubeconfig.yml"], path=KUBESPRAY_DIR, environment=env)

        # _run_command(["sudo", "chown", uid_gid, "home/msi/.kube/config"])
    except subprocess.CalledProcessError as e:
        return handling_ansible_error(e)
    
    return {
        "status": "Succesfully created cluster"
        }
#print(deploy_cluster(network="calico"))

def get_nodes() -> dict:
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
    return {
        "master-nodes-count": count_m,
        "worker-nodes-count": count_w
    }

def scale(master: int, worker: int, network: str) -> dict:
    """
    Scale cluster by adding more master nodes using cluster.yml or worker nodes using Kubespray scale.yml.

    The inventory must already include the new worker hosts.
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
        if master_c + master > config["Master_config"]["nodes"] or master_c + master < config["Master_config"]["nodes"]:
            return {
                "Status": "Fail",
                "Cause": f"Need {master_c + master - config["Master_config"]["nodes"]} more master Vms to scale up cluster, currently {config["Master_config"]["nodes"]} master"
            }
        try:
            _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "cluster.yml"], path=KUBESPRAY_DIR, environment=env)
        except subprocess.CalledProcessError as e:
            return handling_ansible_error(e)
        
    return {
        "status": "success",
        "scale_up_master": master,
        "scale_up_worker": worker,
        "detail": "Scale up finished successfully"
    }
#print(scale(master=0, worker=1, network="cilium"))

def remove_node(master: int, worker: int) -> dict:
    """
    Scale down cluster by remove master nodes using cluster.yml or worker nodes using Kubespray scale.yml.

    The inventory must already include the new worker hosts.
    """
    ## current 2 vms -> scale up 2 nodes -> need 1 more vms
    ## if scale up but no available vms -> Fail -> need to create vms first then scale up node
    config = json.loads(VAR_FILE.read_text(encoding="utf-8"))
    running_nodes = get_nodes()
    worker_c = running_nodes["worker-nodes-count"]
    master_c = running_nodes["master-nodes-count"]

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
#print(remove_node(master=0, worker=2))

def remove_cluster(confirm: bool=False) -> dict:
    """
    Remove cluster using kubespray reset.yml playbook.
    """
    if not confirm:
        return {
            "status": "fail",
            "cause": "Confirmation required to remove cluster"
        }
    try:
        _run_command(["ansible-playbook", "-i", "inventory/mycluster/inventory.yaml", "-b", "reset.yml", "-e", "reset_confirmation=yes"], path=KUBESPRAY_DIR, environment=env)
    except subprocess.CalledProcessError as e:
        return handling_ansible_error(e)
    
    return {
        "status": "Successfully removed cluster"
    }
#print(remove_cluster(True))

def check_connection() -> dict: 
    """
    Check connection each vms in inventory file.
    """
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
#print(check_connection())

def network_plugin(network: str) -> dict:
    yaml = YAML()
    yaml.preserve_quotes = True

    with open(NETWORK_PLUGIN, "r") as file:
        data = yaml.load(file)

    data["kube_network_plugin"] = network
    with open(NETWORK_PLUGIN, "w") as file:
        yaml.dump(data, file)

    print("YAML file updated successfully!")
#print(network_plugin("calico"))

def web_server(replicas: int) -> dict:
    """Deploys a basic Nginx service to the cluster."""
    WEB = WEB_SERVER / "nginx-deployment.yaml"
    SERVICE = WEB_SERVER / "nginx-service.yaml"

    yaml = YAML()
    yaml.preserve_quotes = True

    with open(WEB, "r") as file:
        data = yaml.load(file)

    data["spec"]["replicas"] = replicas
    with open(WEB, "w") as file:
        yaml.dump(data, file)

    try:
        _run_command(["kubectl", "apply", "-f", WEB])
        _run_command(["kubectl", "apply", "-f", SERVICE])
        return {"status": "Success", "access": "Nginx is available on NodePort 30080"}
    except subprocess.CalledProcessError as e:
        return {"status": "fail", "error": e.stderr}
print(web_server(3))

def test_server() -> dict:
    output = _run_command(["hey", "-n", "5000", "-c", "100", "http://10.233.0.1:30080/"])
    return output.stdout
#print(test_server())