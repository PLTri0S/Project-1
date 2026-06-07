# VM Provisioning Guide
This document serves as an internal knowledge resource for the MCP server. It outlines the minimum hardware requirements for provisioning a Kubernetes cluster
## 1. Minimum Specifications Requirements

When calling `provision_vms` or `update_vms`, the following specifications are required to ensure a stable Kubernetes deployment.

### Control Plane (Master Nodes)
* **Nodes:** Must be an odd number (1, 3, or 5) to maintain etcd quorum.
* **vCPU:** 2 Cores minimum (Kubernetes API server and etcd are CPU intensive).
* **RAM:** 2.5 GB minimum. (2 GB is the absolute hard limit for testing, but etcd will frequently crash out of memory under load) (>=4 GB recommended). **NEVER LESS THAN 2 GB IN ANY CASE**
* **Disk:** 10 GB minimum for the OS, container images, and etcd data.

### Worker Nodes
* **Nodes:** 1 minimum (Recommended 2+ for high availability testing).
* **vCPU:** 1 Cores minimum (2 is recommended). 
* **RAM:** 1.5 GB minimum (2-4 GB recommended). **NEVER LESS THAN 1.5 GB IN ANY CASE**
* **Disk:** 10 GB minimum.

### Host Machine Overhead
As defined in the provisioning manager, the host physical machine must maintain a safety reserve:
* **RAM Reserve:** 3 GB minimum.
* **CPU Reserve:** 2 Cores minimum.
* **Disk Reserve:** 50 GB minimum.