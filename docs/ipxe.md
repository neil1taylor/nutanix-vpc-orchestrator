# Understanding PXE Boot Components for Nutanix CE

This document explains how the various components work together to enable automated network booting and installation of Nutanix CE on IBM Cloud VPC bare metal servers.

## Overview of the Boot Process

The automated boot process follows this sequence:

1. **BIOS/UEFI** → **iPXE** → **Kernel (vmlinuz)** → **Initial Ramdisk (initrd)** → **Kickstart** → **Full OS Installation**

## Component Breakdown

### 1. iPXE Script

**Purpose**: iPXE is the network boot firmware that handles the initial boot process over the network.

**What it does**:
- Configures network interface (DHCP)
- Downloads the Linux kernel and initial ramdisk from your PXE server
- Passes boot parameters to the kernel
- Initiates the boot process

**Key Functions**:
```ipxe
dhcp                                # Get IP address from DHCP server
kernel http://pxe-server/vmlinuz    # Download and load kernel
initrd http://pxe-server/initrd.img # Download initial ramdisk
boot                                # Start the kernel
```

**Boot Parameters Passed**:
- `inst.repo`: Location of installation repository
- `inst.ks`: Location of kickstart configuration file
- `console`: Console output settings for remote management
- `ip=dhcp`: Network configuration method

### 2. vmlinuz (Linux Kernel)

**Purpose**: The compressed Linux kernel that will run on the target system.

**What it contains**:
- Core operating system kernel
- Essential device drivers
- Memory management
- Process scheduling
- Network stack

**In this context**:
- Extracted from Nutanix CE ISO
- Contains drivers needed for IBM Cloud bare metal hardware
- Includes network drivers for downloading additional components
- Supports the hardware platform (x86_64)

**Boot process**:
1. iPXE downloads vmlinuz from PXE server
2. Kernel is loaded into memory
3. Kernel initializes hardware
4. Kernel mounts the initial ramdisk
5. Control is passed to init system in initrd

### 3. initrd (Initial RAM Disk)

**Purpose**: A temporary root filesystem loaded into memory during boot.

**What it contains**:
- Minimal Linux environment
- Essential utilities and tools
- Network drivers and tools
- Installation programs
- Python/shell scripts for automation

**Key Functions**:
Inside initrd, these processes happen:
- Hardware detection
- Network interface initialization
- Download of kickstart file
- Preparation for main installation
- Mounting of installation media

**Why it's needed**:
- Provides tools needed before the main filesystem is available
- Contains drivers that might not be in the kernel
- Includes installation scripts and utilities
- Handles network-based installations

### 4. Kickstart Configuration (kickstart.cfg)

**Purpose**: Automated installation configuration file that eliminates manual intervention.

**Key Sections Explained**:

#### Installation Settings
```bash
install        # Perform installation (not upgrade)
text           # Use text mode (no GUI)
reboot         # Automatically reboot after installation
```

#### System Configuration
```bash
lang en_US.UTF-8              # System language
keyboard us                   # Keyboard layout
timezone UTC --isUtc          # Time zone setting
rootpw --iscrypted $hash      # Root password (encrypted)
```

#### Network Configuration
```bash
network --bootproto=dhcp --device=eth0 --onboot=yes --noipv6
```
- Uses DHCP for IP assignment
- Configures eth0 as primary interface
- Enables interface at boot
- Disables IPv6

#### Disk Partitioning
```bash
clearpart --all --initlabel                   # Clear all partitions
part /boot --fstype=ext4 --size=500           # Boot partition
part pv.01 --size=1 --grow                    # Physical volume for LVM
volgroup nutanix pv.01                        # Volume group
logvol / --fstype=ext4 --name=root --vgname=nutanix --size=30720
```

#### Package Selection
```bash
%packages --nobase --ignoremissing
@core              # Core system packages
openssh-server     # SSH access
wget               # File download utility
curl               # HTTP client
%end
```

#### Pre-installation Script
```bash
%pre --log=/tmp/kickstart-pre.log
# Downloads configuration files before installation
wget -O /tmp/nutanix-config.json http://pxe-server/config.json
%end
```

#### Post-installation Script
```bash
%post --log=/root/kickstart-post.log
# Runs after OS installation completes
# Downloads and installs Nutanix CE
# Configures the system
%end
```

## How They Work Together

### Step-by-Step Process

1. **Bare Metal Server Powers On**
   - BIOS/UEFI configured for network boot
   - PXE ROM requests IP via DHCP
   - The IBM Cloud DHCP server responds with IP and iPXE script location

2. **iPXE Execution**
   ```bash
   Server → DHCP Request → DHCP Server
   Server ← IP + iPXE Script ← DHCP Server
   Server → Download vmlinuz ← PXE Server
   Server → Download initrd ← PXE Server
   ```

3. **Kernel Boot**
   - vmlinuz loads and initializes hardware
   - initrd mounts as temporary root filesystem
   - Kernel passes control to init process in initrd

4. **Installation Preparation**
   - initrd scripts initialize network
   - Download kickstart.cfg from PXE server
   - Parse kickstart configuration
   - Download installation repository files

5. **Automated Installation**
   - Partition disks according to kickstart
   - Install base operating system
   - Configure network, users, services
   - Execute post-installation scripts

6. **Nutanix CE Installation**
   - Post-install script downloads Nutanix CE installer
   - Runs automated Nutanix installation
   - Configures cluster settings
   - System reboots into Nutanix CE

## Network Flow Diagram

```bash
IBM Cloud Bare Metal Server    PXE Config Server
┌─────────────────────────┐    ┌──────────────────┐
│                         │    │                  │
│  1. DHCP Request        │───▶│  DHCP Response   │
│                         │    │  + iPXE Script   │
│                         │    │                  │
│  2. Download vmlinuz    │───▶│  vmlinuz-nutanix │
│                         │    │                  │
│  3. Download initrd     │───▶│  initrd-nutanix  │
│                         │    │                  │
│  4. Boot kernel+initrd  │    │                  │
│                         │    │                  │
│  5. Download kickstart  │───▶│  kickstart.cfg   │
│                         │    │                  │
│  6. Download repo files │───▶│  /repo/*         │
│                         │    │                  │
│  7. Install OS          │    │                  │
│                         │    │                  │
│  8. Download Nutanix CE │───▶│  nutanix-ce.tar  │
│                         │    │                  │
│  9. Configure cluster   │───▶│  config.json     │
│                         │    │                  │
│ 10. Reboot to Nutanix   │    │                  │
└─────────────────────────┘    └──────────────────┘
```

## File Dependencies

### PXE/Conifg Server Directory Structure
```
/var/www/pxe/
├── configs
├── images
│   ├── initrd-foundation.img
│   ├── nutanix-ce-installer.iso
│   └── vmlinuz-foundation
└── scripts
    ├── foundation-init.sh
    ├── network-config.sh
    └── post-install.sh
```

### Boot Parameter Flow
```bash
iPXE Script Parameters:
├── inst.repo=http://pxe-server/nutanix-ce/repo
├── inst.ks=http://pxe-server/config/kickstart.cfg
├── console=tty0 console=ttyS0,115200
└── ip=dhcp

Kickstart References:
├── wget http://pxe-server/config/nutanix-config.json
└── wget http://pxe-server/nutanix-ce-installer.tar.gz
```

## Security Considerations

### Network Security
- **HTTP vs HTTPS**: Consider using HTTPS for sensitive configuration files
- **Network Isolation**: Ensure PXE server is on trusted network segment
- **Firewall Rules**: Restrict access to PXE server ports (80/443, 69 for TFTP)

### Authentication
- **Encrypted Passwords**: Use `--iscrypted` passwords in kickstart
- **SSH Keys**: Deploy SSH keys instead of passwords where possible
- **Certificate Validation**: Validate downloaded files with checksums

### Access Control
- **File Permissions**: Proper permissions on PXE server files
- **Network ACLs**: Restrict which systems can access PXE resources
- **Audit Logging**: Log all PXE boot attempts and file downloads

## Troubleshooting Common Issues

### Boot Failures
1. **Network Issues**: Check DHCP, routing, firewall rules
2. **Missing Files**: Verify all files exist on PXE server
3. **Permissions**: Ensure web server can read all files
4. **Hardware**: Confirm network boot is enabled in BIOS

### Installation Failures
1. **Kickstart Syntax**: Validate kickstart file syntax
2. **Package Conflicts**: Check for missing or conflicting packages
3. **Disk Issues**: Verify partition scheme matches hardware
4. **Network Timeouts**: Increase timeout values for slow networks

This automated process eliminates manual intervention while providing full control over the installation and configuration of Nutanix CE on IBM Cloud infrastructure.

## Configuration Flow

### 1. **Initial Configuration Storage**
In `node_provisioner.py`, these parameters are stored in the database during provisioning:

```python
'nutanix_config': {
    'ahv_ip': ip_allocation['ahv']['ip_address'],
    'cvm_ip': ip_allocation['cvm']['ip_address'], 
    'cluster_ip': ip_allocation.get('cluster', {}).get('ip_address'),
    'storage_config': node_data['node_config'].get('storage_config', {})
}
```

### 2. **Boot Process Configuration**
In `boot_service.py`, these configs are used to generate the Foundation configuration:

```python
def generate_foundation_config(self, node, is_first_node):
    """Generate Foundation configuration from node data"""
    nutanix_config = node['nutanix_config']
    
    foundation_config = {
        'cluster_config': {
            'cluster_name': cluster_name,
            'cluster_external_ip': str(cluster_ip),
            'redundancy_factor': 1 if is_first_node else 2
        },
        'node_config': {
            'hypervisor': 'ahv',
            'hypervisor_ip': nutanix_config['ahv_ip'],
            'cvm_ip': nutanix_config['cvm_ip']
        }
    }
```

### 3. **Storage Configuration Usage**
In `generate_storage_config()`, your storage drive configuration is applied:

```python
def generate_storage_config(self, node):
    storage_config = {
        'data_devices': [
            '/dev/nvme2n1',
            '/dev/nvme3n1', 
            '/dev/nvme4n1'
        ]
    }
    
    # Adjust based on node's storage config if specified
    if node['nutanix_config'].get('storage_config'):
        user_storage = node['nutanix_config']['storage_config']
        if 'data_drives' in user_storage:
            storage_config['data_devices'] = [
                f"/dev/{drive}" for drive in user_storage['data_drives']
            ]
```

## What Does the Configuration

### **Nutanix Foundation Service**
Foundation service is the primary component that handles cluster creation and node configuration. It validates IP addresses, configures CVM, Host and IPMI addresses, and creates the initial cluster configuration JSON file.

### **Configuration Process**

1. **iPXE Boot**: Server boots from the PXE/Config server with custom iPXE image
2. **Configuration Download**: Foundation downloads the server config from the `/boot/server/<bare_metal_server_mgmt_ip>` endpoint hosted on the PXE/Config server
3. **Foundation Initialization**: Foundation service reads the JSON configuration and applies it
4. **Role Assignment**: Based on `cluster_role`, Foundation configures the node as:
   - `compute-storage` (HCI Node): Full compute + storage capabilities
   - `storage`: Storage-only node that runs AHV but focuses on storage capacity
   - `compute`: Compute-only node with minimal storage, no CVM

4. **Storage Configuration**: Foundation applies the `storage_config.data_drives` to:
   - Configure which NVMe drives are used for the Nutanix storage pool
   - Set up the Storage Pool spanning the specified drives
   - Configure appropriate metadata distribution

### **Implementation**

In `boot_service.py`, the configuration is delivered via:

1. **iPXE Boot Script**: Generated in `generate_cluster_creation_script()` or `generate_node_addition_script()`
2. **Server Config Endpoint**: `/boot/server/<server_ip>` provides the detailed JSON configuration
3. **Foundation Scripts**: The boot scripts (like `foundation-init.sh`) execute Foundation with the provided config

### **Example Configuration Flow**

1. Server boots → iPXE → Your PXE Server
2. iPXE script loads Foundation kernel/initrd  
3. Foundation starts → calls your `/boot/server/<ip>` endpoint
4. Your server returns JSON with:
   ```bash
   {
     "cluster_config": {...},
     "node_config": {
       "hypervisor": "ahv",
       "hypervisor_ip": "10.240.0.51", 
       "cvm_ip": "10.240.0.101"
     },
     "storage_config": {
       "data_devices": ["/dev/nvme2n1", "/dev/nvme3n1", "/dev/nvme4n1"]
     }
   }
   ```
5. Foundation applies configuration:
   - Sets up node role (compute-storage)
   - Configures specified storage drives
   - Joins/creates cluster

### **The Role Impact**

- **`compute-storage`**: Most common HCI node with full processing capacity (CPU), memory (RAM), and data storage capacity. Can run any supported hypervisor and user VMs
- **`storage`**: Storage nodes only use AHV as hypervisor, no user VMs run on these nodes, used to expand storage capacity without additional hypervisor licenses  
- **`compute`**: Compute-only nodes expand computing capacity (CPU and memory) with minimal storage, no CVM running on the node

The configuration ensures proper resource allocation and cluster topology based on your specified node roles and storage requirements.

## Foundation in the PXE Boot Process

### 1. **Foundation is Part of the Boot Images**
In `boot_service.py`, Foundation is delivered as part of the iPXE boot process:

```python
def generate_cluster_creation_script(self, node):
    template = f"""#!ipxe
echo Loading Foundation environment...
kernel ${{base-url}}/images/vmlinuz-foundation console=tty0 console=ttyS0,115200
initrd ${{base-url}}/images/initrd-foundation.img

echo Starting cluster creation process...
imgargs vmlinuz-foundation node_id=${{node_id}} operation=${{operation}} mgmt_ip=${{mgmt_ip}} ...
boot || goto error
"""
```

### 2. **Foundation Images in Your Setup**
In `setup.sh`, these Foundation boot files are extracted from the Nutanix CE ISO that is downloaded:

```bash
# Extract boot files from Nutanix ISO
cp /mnt/boot/kernel /var/www/pxe/images/vmlinuz-foundation 2>/dev/null || true
cp /mnt/boot/initrd /var/www/pxe/images/initrd-foundation.img 2>/dev/null || true
```

These contain:
- **`vmlinuz-foundation`**: Linux kernel with Foundation service
- **`initrd-foundation.img`**: Initial RAM disk with Foundation tools and utilities

### 3. **Configuration Delivery Flow**

```
1. Bare Metal server PXE boots → Downloads the iPXE script from the PXE/Config server
2. The iPXE script downloads the Foundation kernel and initrd from he PXE/Config server
3. Foundation boots and receives parameters via kernel command line
4. Foundation calls back to the PXE/Config server: GET /boot/server/<bare_metal_server_mgmt_ip>
5. The PXE/Config server returns JSON configuration
6. Foundation applies the configuration to the bare metal server
```

### 4. **Foundation's Role**

Foundation is essentially a **specialized Linux distribution** that:

- **Boots from network**: Runs entirely in RAM
- **Discovers hardware**: Identifies storage drives, network interfaces, etc.
- **Configures networking**: Sets up management, AHV, and CVM IP addresses
- **Partitions storage**: Configures drives according to your `storage_config`
- **Installs Nutanix**: Downloads and installs AOS, AHV hypervisor, and CVM
- **Joins/Creates cluster**: Either creates new cluster or joins existing one

### 5. **Configuration Integration**

In `boot_service.py`, Foundation receives configuration via:

```python
def get_server_config(self, server_ip):
    # Foundation calls this endpoint to get configuration
    return {
        'server_info': {...},
        'cluster_config': foundation_config['cluster_config'],
        'node_config': foundation_config['node_config'], 
        'storage_config': storage_config,
        'network_config': network_config
    }
```

### 6. **Foundation's Configuration Process**

When Foundation boots on the bare metal server, it:

1. **Reads kernel parameters** (node_id, operation, IP addresses)
2. **Calls your config endpoint**: `GET /boot/server/<management_ip>`
3. **Receives JSON config** with cluster role, storage drives, network settings
4. **Applies configuration**:
   - Partitions and formats the specified NVMe drives (`nvme2n1`, `nvme3n1`, `nvme4n1`)
   - Sets up the node role (`compute-storage`, `storage`, or `compute`)
   - Configures network interfaces with the provided IP addresses
   - Installs and configures Nutanix software stack

### 7. **What Foundation Actually Does**

In `storage_config`:
```json
{
  "data_drives": ["nvme2n1", "nvme3n1", "nvme4n1"],
  "cluster_role": "compute-storage"
}
```

Foundation will:
- Format `/dev/nvme2n1`, `/dev/nvme3n1`, `/dev/nvme4n1` for Nutanix storage pool
- Configure the node as a full HCI node (compute + storage)
- Set up the Controller VM (CVM) to manage storage
- Install AHV hypervisor for running user VMs
- Configure cluster networking and join/create the cluster

### 8. **Foundation vs Your PXE Server**

| Component | Responsibility |
|-----------|----------------|
| **PXE Server** | Stores configurations, serves boot files, tracks deployment status |
| **Foundation** | Actually configures the bare metal server hardware and software |

Foundation is the "installer" that gets downloaded to each server and does all the heavy lifting of configuring Nutanix according to the specifications provided through the PXE/Config server.

The PXE/Config server is the "orchestrator" that tells Foundation what to do, while Foundation is the "worker" that actually makes it happen on each physical server.