# Understanding PXE Boot Components for Nutanix CE

This document explains how the various components work together to enable automated network booting and installation of Nutanix CE on IBM Cloud VPC bare metal servers.

## Overview of the Boot Process

The automated boot process follows this sequence:

1. **BIOS/UEFI** → **iPXE** → **Kernel (vmlinuz)** → **Initial Ramdisk (initrd)** → **Foundation Service** → **Nutanix CE Installation**

## Component Breakdown

### 1. iPXE Script

**Purpose**: iPXE is the network boot firmware that handles the initial boot process over the network in IBM Cloud VPC bare metal servers.

**IBM Cloud VPC Integration**:
IBM Cloud VPC expects the `user_data` field to contain either:
- **A single URL** pointing to an iPXE script (recommended)
- **The actual iPXE script content** as text

**What it does**:
- Configures network interface (DHCP)
- Downloads the Foundation kernel and initial ramdisk from your PXE server
- Passes boot parameters to the Foundation kernel
- Initiates the Foundation boot process

**IBM Cloud VPC Implementation**:

**Option 1: URL Method (Recommended)**
```python
# When creating bare metal server via IBM Cloud VPC SDK
user_data = "http://<PXE_CONFIG_SERVER_IP>/boot/ipxe/server-001"
```

**Option 2: Inline Script Method**
```python
user_data = """#!ipxe
echo Starting Nutanix Foundation deployment...
:retry_dhcp
dhcp || goto retry_dhcp
sleep 2
set base-url http://<PXE_CONFIG_SERVER_IP>/pxe
kernel ${base-url}/images/vmlinuz-foundation console=tty0 console=ttyS0,115200
initrd ${base-url}/images/initrd-foundation.img
imgargs vmlinuz-foundation node_id=${ip} operation=cluster_creation mgmt_ip=${ip}
boot || goto error
:error
echo Boot failed, retrying...
sleep 10
goto retry_dhcp
"""
```

**Key iPXE Script Functions**:
```ipxe
dhcp                                                        # Get IP address from DHCP server
kernel http://<PXE_CONFIG_SERVER_IP>/vmlinuz-foundation     # Download Foundation kernel
initrd http://<PXE_CONFIG_SERVER_IP>/initrd-foundation.img  # Download Foundation initrd
boot                                                        # Start the Foundation kernel
```

**Foundation Boot Parameters**:
- `node_id`: Unique identifier for the node (server name or IP)
- `operation`: Type of operation (cluster_creation, node_addition)
- `mgmt_ip`: Management IP address for configuration retrieval
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

**Purpose**: The core service that performs automated Nutanix CE installation and cluster configuration.

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

#### Cluster Operations
- Creates new clusters (first node)
- Joins existing clusters (additional nodes)
- Validates cluster topology
- Configures inter-node communication

## How They Work Together

### Step-by-Step Process

1. **Bare Metal Server Provisioning**
   - IBM Cloud VPC bare metal server created with `user_data` containing iPXE script URL or content
   - Server configured for network boot in BIOS/UEFI

2. **Initial Boot Process**
   - Server boots and IBM Cloud's PXE environment reads `user_data`
   - If URL: IBM Cloud fetches iPXE script from the specified URL
   - If inline: IBM Cloud uses the provided iPXE script content directly

3. **iPXE Execution**
   ```
   Server → DHCP Request → IBM Cloud DHCP
   Server ← IP Address ← IBM Cloud DHCP
   Server → Fetch iPXE Script ← Your PXE Server (if URL method)
   Server → Download vmlinuz-foundation ← Your PXE Server
   Server → Download initrd-foundation.img ← Your PXE Server
   ```

3. **Foundation Kernel Boot**
   - vmlinuz-foundation loads and initializes hardware
   - initrd-foundation.img mounts as temporary root filesystem
   - Kernel passes control to Foundation service

4. **Configuration Retrieval**
   - Foundation service initializes network
   - Downloads configuration from: `GET /boot/server/<management_ip>`
   - Parses JSON configuration for node settings

5. **Automated Installation**
   - Partitions storage drives according to configuration
   - Installs Nutanix software stack (AOS, AHV, CVM)
   - Configures network, storage, and cluster settings
   - Joins or creates Nutanix cluster

6. **System Initialization**
   - Foundation service completes deployment
   - System reboots into Nutanix CE environment
   - Cluster services start and validate configuration

## Network Flow Diagram

```
IBM Cloud VPC Bare Metal     Your PXE/Config Server
┌─────────────────────────┐    ┌──────────────────┐
│                         │    │                  │
│  1. Boot with user_data │    │                  │
│     iPXE URL/script     │    │                  │
│                         │    │                  │
│  2. Fetch iPXE script   │───▶│  /boot/ipxe/     │
│     (if URL method)     │    │  <server_id>     │
│                         │    │                  │
│  3. Download vmlinuz    │───▶│  vmlinuz-        │
│     -foundation         │    │  foundation      │
│                         │    │                  │
│  4. Download initrd     │───▶│  initrd-         │
│     -foundation.img     │    │  foundation.img  │
│                         │    │                  │
│  5. Boot Foundation     │    │                  │
│                         │    │                  │
│  6. Download config     │───▶│  /boot/server/   │
│     JSON                │    │  <mgmt_ip>       │
│                         │    │                  │
│  7. Install Nutanix CE  │    │                  │
│                         │    │                  │
│  8. Configure cluster   │    │                  │
│                         │    │                  │
│  9. Reboot to Nutanix   │    │                  │
└─────────────────────────┘    └──────────────────┘
```

## File Dependencies

### PXE/Config Server Directory Structure
```
/var/www/pxe/
├── boot/
│   └── ipxe/
│       ├── server-001          # iPXE script for server-001
│       ├── server-002          # iPXE script for server-002
│       └── server-N            # iPXE script for server-N
├── configs/
│   └── (dynamic configuration via API endpoints)
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
├── URL Method (Recommended):
│   └── "http://pxe-server.com/boot/ipxe/<server_id>"
│       └── Returns server-specific iPXE script
└── Inline Method:
    └── Raw iPXE script content as string

iPXE Script Parameters:
├── node_id=<server_identifier>
├── operation=cluster_creation|node_addition
├── mgmt_ip=<management_ip_address>
└── console=tty0 console=ttyS0,115200

Foundation Configuration Endpoint:
└── GET /boot/server/<management_ip>
    └── Returns JSON with cluster, node, storage, and network config
```

## Configuration Flow

### 1. **Initial Configuration Storage**
In `node_provisioner.py`, these parameters are stored in the database during provisioning:

```python
'nutanix_config': {
    'ahv_ip': ip_allocation['ahv']['ip_address'],
    'cvm_ip': ip_allocation['cvm']['ip_address'], 
    'cluster_ip': ip_allocation.get('cluster', {}).get('ip_address'),
    'storage_config': node_data['node_config'].get('storage_config', {}),
    'cluster_role': node_data['node_config'].get('cluster_role', 'compute-storage')
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
            'cvm_ip': nutanix_config['cvm_ip'],
            'role': nutanix_config.get('cluster_role', 'compute-storage')
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
    
    return storage_config
```

## Foundation Service Architecture

### **What is Foundation**
Foundation is a specialized Linux distribution that runs entirely in RAM and is responsible for:
- **Hardware Discovery**: Identifying storage drives, network interfaces, memory
- **Network Configuration**: Setting up management, AHV, and CVM IP addresses
- **Storage Setup**: Partitioning and configuring specified storage drives
- **Nutanix Installation**: Installing AOS, AHV hypervisor, and CVM components
- **Cluster Operations**: Creating new clusters or joining existing ones

### **Foundation vs Traditional Kickstart**
Unlike traditional kickstart installations, Foundation:
- Doesn't install a general-purpose OS
- Installs a specialized Nutanix software stack
- Configures cluster-specific settings
- Handles distributed storage configuration
- Manages hypervisor and virtualization setup

### **Configuration Process**

1. **iPXE Boot**: Server boots with Foundation kernel and initrd
2. **Foundation Initialization**: Foundation service starts and discovers hardware
3. **Configuration Download**: Foundation calls `/boot/server/<mgmt_ip>` endpoint
4. **Hardware Validation**: Foundation validates configuration against discovered hardware
5. **Storage Configuration**: Foundation partitions and formats specified drives
6. **Software Installation**: Foundation installs Nutanix CE components
7. **Cluster Configuration**: Foundation creates or joins cluster
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

### **Implementation in PXE Boot Process**

1. **Boot Images**: Foundation images are extracted during setup:
   ```bash
   # In setup.sh
   cp /mnt/boot/kernel /var/www/pxe/images/vmlinuz-foundation
   cp /mnt/boot/initrd /var/www/pxe/images/initrd-foundation.img
   ```

2. **iPXE Script Generation**: In `boot_service.py`:
   ```python
   def generate_ipxe_script_url(self, server_id):
       """Return URL for server-specific iPXE script (for IBM Cloud user_data)"""
       return f"http://{self.pxe_server_ip}/boot/ipxe/{server_id}"
   
   def generate_server_ipxe_script(self, server_id, mgmt_ip, operation='cluster_creation'):
       """Generate iPXE script for specific server"""
       return f"""#!ipxe
   echo Starting Nutanix Foundation for server {server_id}...
   
   :retry_dhcp
   dhcp || goto retry_dhcp
   sleep 2
   
   set base-url http://{self.pxe_server_ip}/pxe
   
   kernel ${{base-url}}/images/vmlinuz-foundation console=tty0 console=ttyS0,115200
   initrd ${{base-url}}/images/initrd-foundation.img
   
   imgargs vmlinuz-foundation node_id={server_id} operation={operation} mgmt_ip={mgmt_ip}
   
   boot || goto error
   
   :error
   echo Boot failed, retrying...
   sleep 10
   goto retry_dhcp
   """
   
   def create_ibm_cloud_server(self, server_config):
       """Create IBM Cloud VPC bare metal server with iPXE user_data"""
       
       # Generate iPXE script URL for user_data
       ipxe_url = self.generate_ipxe_script_url(server_config['server_id'])
       
       server_response = vpc_client.create_bare_metal_server(
           bare_metal_server_prototype={
               'name': server_config['server_name'],
               'profile': {'name': 'bx2-metal-96x384'},
               'zone': {'name': server_config['zone_name']},
               'vpc': {'id': server_config['vpc_id']},
               'primary_network_interface': {
                   'name': 'eth0',
                   'subnet': {'id': server_config['subnet_id']}
               },
               'user_data': ipxe_url  # URL method - IBM Cloud fetches iPXE script
           }
       )
       
       return server_response
   ```

3. **Configuration Delivery**: Foundation receives configuration via REST API:
   ```python
   def get_server_config(self, server_ip):
       return {
           'server_info': server_info,
           'cluster_config': foundation_config['cluster_config'],
           'node_config': foundation_config['node_config'], 
           'storage_config': storage_config,
           'network_config': network_config
       }
   ```

## Security Considerations

### Network Security
- **HTTPS Configuration**: Use HTTPS for sensitive configuration endpoints
- **Network Isolation**: Ensure PXE server is on trusted network segment
- **Firewall Rules**: Restrict access to PXE server ports (80/443, 69 for TFTP if used)
- **API Authentication**: Implement authentication for configuration endpoints

### Access Control
- **File Permissions**: Proper permissions on PXE server files (644 for files, 755 for directories)
- **Network ACLs**: Restrict which systems can access PXE resources
- **Audit Logging**: Log all boot attempts and configuration downloads
- **IP Validation**: Validate requesting IP addresses against known servers

### Configuration Security
- **Encrypted Passwords**: Use secure password hashing for any stored credentials
- **Certificate Validation**: Validate downloaded files with checksums where possible
- **Configuration Validation**: Validate configuration parameters before applying
- **Secure Defaults**: Use secure default configurations

## Troubleshooting Common Issues

### Boot Failures
1. **Network Issues**: 
   - Check DHCP server configuration and IP allocation
   - Verify routing between servers and PXE server
   - Check firewall rules for HTTP/HTTPS traffic

2. **Missing Files**: 
   - Verify vmlinuz-foundation and initrd-foundation.img exist
   - Check file permissions (should be readable by web server)
   - Validate file integrity with checksums

3. **iPXE Script Issues**:
   - Check iPXE script syntax
   - Verify base-url variable is correctly set
   - Test iPXE script manually if possible

### Foundation Failures
1. **Configuration Issues**: 
   - Validate JSON configuration syntax
   - Check that all required fields are present
   - Verify IP addresses don't conflict

2. **Hardware Issues**: 
   - Confirm specified storage drives exist (`/dev/nvme2n1`, etc.)
   - Verify network interfaces are available
   - Check hardware compatibility with Nutanix CE

3. **Network Timeouts**: 
   - Increase timeout values for slow networks
   - Check network connectivity between nodes
   - Verify DNS resolution if using hostnames

### Storage Configuration Issues
1. **Drive Detection**: 
   - Verify drive naming convention matches system
   - Check that drives are not already in use
   - Validate drive sizes meet minimum requirements

2. **Partition Failures**:
   - Ensure drives are not mounted or in use
   - Check for existing partition tables
   - Verify sufficient free space

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