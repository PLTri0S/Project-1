#!/usr/bin/env python3
import json
import re
import subprocess
import sys

try:
    payload = json.load(sys.stdin)
except json.JSONDecodeError:
    payload = {}

vm_names = payload.get("vm_names", [])

if isinstance(vm_names, str):
    try:
        vm_names = json.loads(vm_names)
    except json.JSONDecodeError:
        vm_names = []
#ips result
result = []
for vm in vm_names:
    ip = ""
    proc = subprocess.run(
        ["virsh", "domifaddr", vm],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            match = re.search(r"ipv4\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", line)
            if match:
                ip = match.group(1)
                break
    result.append({"name": vm, "ip": ip})
# OpenTofu external provider requires all values to be strings

ip_list = [host["ip"] for host in result if host["ip"]]
output = {
    "hosts": json.dumps(result),
    "ips": ",".join(ip_list),
    }
print(json.dumps(output))





