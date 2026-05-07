#!/usr/bin/env bash
set -euo pipefail

read -r input
python3 - <<'PY'
import json, sys, subprocess, re
payload = json.loads(sys.stdin.read())
vm_names = payload.get("vm_names", [])
result = []
for vm in vm_names:
    ip = ""
    try:
        output = subprocess.check_output(["virsh", "domifaddr", vm], text=True, stderr=subprocess.DEVNULL)
        for line in output.splitlines():
            m = re.search(r"ipv4\\s+([0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+)", line)
            if m:
                ip = m.group(1)
                break
    except subprocess.CalledProcessError:
        ip = ""
    result.append({"name": vm, "ip": ip})
print(json.dumps({"hosts": result, "ips": [host["ip"] for host in result]}))
PY
