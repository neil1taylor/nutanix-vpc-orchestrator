# iPXE boot process

## Overview of the Boot Process

The automated boot and Nutanix install process follows this sequence:

1. Server boots: initial iPXE gets second iPXE: node_id, mgmt_ip, ahv_ip, cvm_ip, config_server.
2. Foundation starts: reads parameters from kernel command line.
3. Foundation calls the PXE/Config Server API: uses GET {pxe_config_server}:8080/boot/server/{mgmt_ip} to get the storage configuration.
4. PXE/Config Server API: returns the storage config based on server profile.
5. Foundation: configures node with combined parameters + storage config.

The bare metal server is now considered to be `ready nutanix node` and can be selected for cluster creation:

- For a single node cluster, the PXE server uses SSH to connect to the CVM to configure the cluster.
- For a standard cluster, a minimum of three `ready nutanix nodes` are required. The PXE server uses the Prism API on any of the CVMs (this deployment uses the first CVM) to configure a standard cluster
    - PXE Server → https://<cvm_ip>:9440 (CVM IP)
        - Creates cluster using all CVM IPs: <cvm_ip_1>, <cvm_ip_2>, <cvm_ip_3>

## Boot sequence

The diagram below shows the detailed boot sequence:

```
IBM Cloud VPC Bare Metal         PXE/Config Server
┌─────────────────────────┐    ┌──────────────────────────┐
│                         │    │                          │
│  1. Boot with user_data │    │                          │
│     iPXE URL            │    │                          │
│                         │    │                          │
│  2. Fetch iPXE script   │───▶│  /boot/config            │
│                         │    │                          │
│  3. Download vmlinuz    │───▶│  vmlinuz-foundation      │
│     -foundation         │    │                          │
│                         │    │                          │
│  4. Download initrd     │───▶│  initrd-foundation.img   │
│     -foundation.img     │    │                          │
│                         │    │                          │
│  5. Boot Foundation     │    │                          │
│                         │    │                          │
│  6. Download config     │───▶│  /boot/server/<mgmt_ip>  │
│     JSON                │    │                          │
│                         │    │                          │
│  7. Install Nutanix CE  │    │                          │
│                         │    │                          │
│  8. Reboot to Nutanix   │    │                          │
└─────────────────────────┘    └──────────────────────────┘
```

**Step 1: Boot with user_data iPXE URL**
- IBM Cloud handles PXE boot via user_data

**Step 2: Fetch iPXE script**
Bare Metal Server (<management_ip>) → PXE Server
- Downloads iPXE script from PXE server
- Includes:
    - node_id: <node_hostname> (hostname)
    - mgmt_ip: <management_ip> (existing IBM Cloud interface)
    - ahv_ip: <ahv_ip> (Foundation will configure)
    - cvm_ip: <cvm_ip> (Foundation will configure)
    - config_server: pxe/config server

**Step 3: vmlinuz-foundation**
Bare Metal Server (<management_ip>) → PXE Server
- Downloads vmlinuz-foundation from PXE server

**Step 4: initrd-foundation.img**
Bare Metal Server (<management_ip>) → PXE Server
- Downloads initrd-foundation.img from PXE server

**Step 5: Boot Foundation**
- Boots Foundation with mgmt_ip=<management_ip>

**Step 6: Download config JSON**
Foundation → GET /boot/server/<management_ip> → PXE Server
- Returns JSON config with storage configuration:

**Step 7: Install Nutanix CE**
Foundation configures additional network interfaces:
- Keeps management interface: <management_ip> (IBM Cloud managed)
- Configures AHV hypervisor: <ahv_ip> (on same/additional interface)
- Configures Controller VM: <cvm_ip> (virtual interface for CVM)
- Configures the storage

**Step 8: Reboot to Nutanix**
Node reboots and when available is considered to be in a `ready` state. Ready for cluster configuration.

## Component Breakdown

### 1. iPXE Script

**Purpose**: iPXE is the network boot firmware that handles the initial boot process over the network in IBM Cloud VPC bare metal servers.

**IBM Cloud VPC Integration**:
IBM Cloud VPC expects the `user_data` field to contain either:
- **A single URL** pointing to an iPXE script (recommended)
- **The actual iPXE script content** as text

**Initial iPXE** is passed to the server via the IBM Cloud automation, the URL is sent to to IBM Cloud in the userdata files in the bare metal provisioning by the PXE/Config server.
`http://<pxe_server_dns>:8080/boot/config?node_id=<node_id>&mgmt_ip=<management_ip>`


**What it does**:
- Configures network interface (DHCP)
- Runs the initial iPXE script (the single URL), which tells the server to request the PXE/Config server
- PXE/Config server sends the second iPXE script, which is dynamically generated based on the node configuration in the database

**Second iPXE** the bare metal server requests the second iPXE script which is dynamically generated by the PXE/Config server based on the node configuration in the database. There are two types of scripts generated:

```bash
#!ipxe
echo ===============================================
echo Nutanix CE Cluster Creation
echo ===============================================
echo Node ID: {node_name}
echo Management IP: {management_ip}
echo AHV IP: {ahv_ip}
echo CVM IP: {cvm_ip}
echo ===============================================
echo Starting Nutanix Foundation deployment...

:retry_dhcp
dhcp || goto retry_dhcp
sleep 2
set base-url http://{pxe_server_dns}:8080/boot/images
set node_id {node_name}
set mgmt_ip {management_ip}
set ahv_ip {ahv_ip}
set cvm_ip {cvm_ip}
kernel ${base-url}/vmlinuz-foundation console=tty0 console=ttyS0,115200
initrd ${base-url}/initrd-foundation.img
imgargs vmlinuz-foundation node_id=${node_id} mgmt_ip=${mgmt_ip} ahv_ip=${ahv_ip} cvm_ip=${cvm_ip} config_server=http://{pxe_server_dns}:8080/boot/server/${mgmt_ip}
boot || goto error

:error
echo Boot failed - dropping to shell
shell
```

**What it does**:
- Runs the dynamically generated iPXE script based on node configuration
- Downloads the Foundation kernel and initial ramdisk from the PXE/Config server
- Passes boot parameters to the Foundation kernel
- Initiates the Foundation boot process

**Key iPXE Script Functions**:
```ipxe
dhcp                                            # Get IP address from DHCP server
kernel http://{pxe_server_dns}:8080/boot/images/vmlinuz-foundation     # Download Foundation kernel
initrd http://{pxe_server_dns}:8080/boot/images/initrd-foundation.img  # Download Foundation initrd
boot                                            # Start the Foundation kernel
```
**Foundation Boot Parameters**:
- `node_id`: Unique identifier for the node (server name from database)
- `mgmt_ip`: Primary interface IP address (IBM Cloud assigned, retrieved from database)
- `ahv_ip`: Hypervisor IP address to be configured (retrieved from database)
- `cvm_ip`: Controller VM IP address to be configured (retrieved from database)
- `config_server`: URL to retrieve storage configuration (dynamically generated based on PXE server DNS)
- `console`: Console output settings for remote management

### 2. vmlinuz-foundation (Foundation Linux Kernel)

**Purpose**: The specialized Linux kernel that contains the Foundation service for Nutanix deployment.

**What it contains**:
- Core operating system kernel optimized for Foundation
- Hardware drivers for IBM Cloud bare metal servers
- Network stack for communication with PXE server
- Foundation service initialization code

**In this context**:
- Extracted from Nutanix CE ISO during setup
- Contains drivers needed for IBM Cloud bare metal hardware
- Includes network drivers for downloading configuration
- Supports the hardware platform (x86_64)

**Boot process**:
1. iPXE downloads vmlinuz-foundation from PXE server
2. Kernel is loaded into memory
3. Kernel initializes hardware
4. Kernel mounts the initial ramdisk
5. Control is passed to Foundation service in initrd

### 3. initrd-foundation.img (Foundation Initial RAM Disk)

**Purpose**: A specialized temporary root filesystem containing the Foundation service and tools.

**What it contains**:
- Foundation service executables
- Hardware detection utilities
- Network configuration tools
- Python/shell scripts for Nutanix deployment
- Drivers and kernel modules

**Key Functions**:
Inside initrd-foundation.img, these processes happen:
- Hardware discovery and validation
- Network interface initialization
- Download of node configuration from PXE server
- Foundation service execution
- Nutanix software installation

**Why it's needed**:
- Provides Foundation tools before the main filesystem is available
- Contains specialized drivers for bare metal hardware
- Includes Nutanix-specific installation scripts
- Handles network-based configuration retrieval

### 4. Foundation Service Configuration

**Purpose**: The core service that performs automated Nutanix CE installation configuration.

**Key Responsibilities**:

#### Node Configuration
- Validates and applies IP address assignments (Management, AHV, CVM)
- Configures node role (compute-storage, storage, compute)
- Sets up network interfaces and routing

#### Storage Configuration
- Partitions and formats specified storage drives
- Creates Nutanix storage pools
- Configures metadata distribution
- Sets up Controller VM (CVM) storage
The storage configuration is based on the IBM Cloud server profile. It is requested using `GET /boot/server/<mgmt_ip>` and the API returns configuration in the following format:

```json
{
    "node_config": {
        "node_id": "{node_name}",
        "mgmt_ip": "{management_ip}",
        "ahv_ip": "{ahv_ip}",
        "cvm_ip": "{cvm_ip}"
    },
    "storage_config": {
        "data_drives": ["nvme0n1", "nvme1n1", "nvme2n1", "nvme3n1", "nvme4n1", "nvme5n1", "nvme6n1", "nvme7n1"],
        "boot_drives": ["sda"]
    },
    "cluster_config": {
        "cluster_role": "compute-storage",
        "cluster_name": "nutanix-cluster"
    },
    "server_profile": "cx3d-metal-48x128"
}
```

The storage configuration is dynamically generated based on the server profile information stored in `server_profiles.py` and the node configuration in the database.


## File Dependencies

### PXE/Config Server Directory Structure
```
/var/www/pxe/
├── boot/
│   └── ipxe/
│       ├── (dynamic configuration via API endpoint)
├── configs/
│   └── (dynamic configuration via API endpoint)
├── images/
│   ├── initrd-foundation.img
│   ├── vmlinuz-foundation
│   └── nutanix-ce.iso
└── scripts/
    ├── foundation-init.sh
    ├── network-config.sh
    └── post-install.sh
```
### IBM Cloud VPC Integration Flow
```
IBM Cloud VPC user_data options:
├── URL Method:
    └── "http://<pxe_server_dns>:8080/boot/config?node_id=<node_id>&mgmt_ip=<management_ip>"
        └── Returns server-specific iPXE script based on node configuration in database

iPXE Script Parameters:
├── node_id=<server_identifier> (retrieved from database)
├── mgmt_ip=<primary_interface_ip> (retrieved from database)
├── ahv_ip=<hypervisor_ip> (retrieved from database)
├── cvm_ip=<controller_vm_ip> (retrieved from database)
├── config_server=http://<pxe_server_dns>:8080/boot/server/<mgmt_ip> (dynamically generated)
└── console=tty0 console=ttyS0,115200

Foundation Configuration Methods:
├── Storage config via API call: GET /boot/server/<mgmt_ip>
    ├── data_drives (based on server profile)
    └── boot_drives (to avoid)
```

## Foundation Service Architecture

### **What is Foundation**
Foundation is a specialized Linux distribution that runs entirely in RAM and is responsible for:
- **Hardware Discovery**: Identifying storage drives, network interfaces, memory
- **Network Configuration**: Setting up management, AHV, and CVM IP addresses
- **Storage Setup**: Partitioning and configuring specified storage drives
- **Nutanix Installation**: Installing AOS, AHV hypervisor, and CVM components
- **Node Preparation**: Bringing the node to a "cluster-ready" state
- **Cluster Participation**: Participating in cluster formation when orchestrated (not used in this deployment)

### **Configuration Process**

1. **iPXE Boot**: Server boots with Foundation kernel and initrd
2. **Foundation Initialization**: Foundation service starts and discovers hardware
3. **Configuration Download**: Foundation calls `/boot/server/<mgmt_ip>` endpoint
4. **Hardware Validation**: Foundation validates configuration against discovered hardware
5. **Storage Configuration**: Foundation partitions and formats specified drives
6. **Software Installation**: Foundation installs Nutanix CE components
7. **Cluster Configuration**: Foundation creates or joins cluster (not used in this deployment)
8. **Service Validation**: Foundation validates all services are running correctly

### **Node Role Configuration**
Foundation configures nodes based on the `cluster_role` setting:

- **`compute-storage` (HCI Node)**: 
  - Full compute capacity (CPU and memory for VMs)
  - Storage capacity (participates in distributed storage)
  - Runs Controller VM (CVM) for storage management
  - Can run user VMs on AHV hypervisor

- **`storage`**: 
  - Storage-focused node with AHV hypervisor
  - Runs Controller VM for storage management
  - No user VMs scheduled on this node
  - Used to expand storage capacity without additional compute licenses

- **`compute`**: 
  - Compute-focused node for running user VMs
  - Minimal storage (typically just boot drives)
  - No Controller VM running
  - Used to expand compute capacity

## Architecture Summary

### Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **PXE/Config Server** | Stores configurations, serves boot files, provides REST API for configuration |
| **iPXE** | Network boot loader, downloads and launches Foundation |
| **Foundation Kernel** | Specialized Linux kernel optimized for Nutanix deployment |
| **Foundation Service** | Hardware configuration, software installation, cluster management |
| **Database** | Stores node configurations, IP allocations, deployment status |

### Data Flow Summary

1. **Provisioning**: Node configuration stored in database via `node_provisioner.py`
2. **Boot Request**: Server requests boot configuration via DHCP/PXE
3. **Foundation Boot**: iPXE downloads and launches Foundation environment
4. **Configuration**: Foundation downloads JSON config from `/boot/server/<ip>`
5. **Deployment**: Foundation applies configuration and installs Nutanix CE
6. **Validation**: Foundation validates deployment and reports status

This automated process provides complete control over Nutanix CE deployment while eliminating manual intervention requirements for IBM Cloud bare metal server installations.