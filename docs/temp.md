# Nutanix CE Configuration JSON Structure

After analyzing the `ParamList` class in `docs/temp.py`, I can determine what a JSON configuration file for Nutanix Community Edition (CE) would look like.

## Key Configuration Parameters

```json
{
  "hyp_type": "kvm",
  "model": "NX-3060-G7",
  "node_position": "A",
  "block_id": "BLOCK-123",
  "node_serial": "SERIAL-456",
  "cluster_id": 1,
  "node_name": "BLOCK-123-A",
  "cluster_name": "CE-Cluster",
  
  "hyp_install_type": "clean",
  "svm_install_type": "clean",
  
  "ce_hyp_boot_disk": "/dev/sda",
  "ce_cvm_boot_disks": ["/dev/sdb"],
  "ce_cvm_data_disks": ["/dev/sdc", "/dev/sdd"],
  "ce_disks": ["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"],
  
  "host_ip": "192.168.1.100",
  "host_subnet_mask": "255.255.255.0",
  "default_gw": "192.168.1.1",
  
  "svm_ip": "192.168.1.101",
  "svm_subnet_mask": "255.255.255.0",
  "svm_default_gw": "192.168.1.1",
  
  "dns_ip": "8.8.8.8",
  "per_node_ntp_servers": "pool.ntp.org,time.google.com",
  
  "svm_gb_ram": 16,
  "svm_num_vcpus": 4,
  
  "create_1node_cluster": true,
  "ce_eula_accepted": true,
  "ce_eula_viewed": true,
}
```

## Critical Configuration Requirements

1. **Basic Node Information**:
   - `hyp_type`: Hypervisor type (typically "kvm" for CE)
   - `model`, `node_position`, `block_id`, `node_serial`: Required identifiers
   - `cluster_id`: Must be a positive integer

2. **CE-Specific Parameters**:
   - `ce_hyp_boot_disk`, `ce_cvm_boot_disks`, `ce_cvm_data_disks`: Disk configurations
   - `ce_eula_accepted` and `ce_eula_viewed`: Must be true
   - `create_1node_cluster`: For single-node deployments

3. **Network Configuration**:
   - Host networking (`host_ip`, `host_subnet_mask`, `default_gw`): All three must be provided together
   - CVM networking (`svm_ip`, `svm_subnet_mask`, `svm_default_gw`): All three must be provided together
   - IPs cannot be in the 192.168.5.x network (reserved)

4. **Resource Allocation**:
   - `svm_gb_ram`: RAM for CVM (in GB)
   - `svm_num_vcpus`: vCPUs for CVM

The configuration is validated through the `ce_validate()` method which enforces these requirements.

# Nutanix CE Parameters Reference

Based on the `ParamList` class in `docs/temp.py`, here's a comprehensive list of parameters used for Nutanix CE installation, their purpose, and accepted values.

## Core Community Edition Parameters

| Parameter | Purpose | Accepted Values | Notes |
|-----------|---------|----------------|-------|
| `ce_hyp_boot_disk` | Hypervisor boot disk | Device path (e.g., `/dev/nvme0n1`) | Required for CE |
| `ce_cvm_boot_disks` | CVM boot disks | List of device paths | Required for CE |
| `ce_cvm_data_disks` | CVM data disks | List of device paths | Required for CE |
| `ce_eula_accepted` | EULA acceptance flag | `true` or `false` | Must be `true` for installation to proceed |
| `ce_eula_viewed` | EULA viewed flag | `true` or `false` | Must be `true` for installation to proceed |
| `create_1node_cluster` | Create single-node cluster | `true` or `false` | Cannot be used with `compute_only=true` |
| `ce_disks` | All disks used by CE | List of device paths | Used for disk management |

## Network Configuration Parameters

| Parameter | Purpose | Accepted Values | Notes |
|-----------|---------|----------------|-------|
| `host_ip` | Hypervisor IP address | Valid IPv4 address | Cannot be in 192.168.5.x network |
| `host_subnet_mask` | Hypervisor subnet mask | Valid IPv4 subnet mask | Required if `host_ip` is provided |
| `default_gw` | Hypervisor default gateway | Valid IPv4 address | Required if `host_ip` is provided |
| `svm_ip` | CVM IP address | Valid IPv4 address | Cannot be in 192.168.5.x network |
| `svm_subnet_mask` | CVM subnet mask | Valid IPv4 subnet mask | Required if `svm_ip` is provided |
| `svm_default_gw` | CVM default gateway | Valid IPv4 address | Required if `svm_ip` is provided |
| `dns_ip` | DNS server IP | Valid IPv4 address | Required for 1-node clusters |
| `per_node_ntp_servers` | NTP servers | Comma-separated list of NTP servers | Defaults to predefined NTP_SERVERS |

## Hypervisor Configuration Parameters

| Parameter | Purpose | Accepted Values | Notes |
|-----------|---------|----------------|-------|
| `hyp_type` | Hypervisor type | `kvm`, `esx`, `hyperv` | For CE, typically `kvm` |
| `hyp_install_type` | Hypervisor installation type | `clean` | Must be `clean` for compute-only installations |
| `svm_install_type` | CVM installation type | `clean` or `None` | Must be `None` for compute-only installations |
| `compute_only` | Compute-only installation | `true` or `false` | Only supported on AHV (and ESXi if feature enabled) |

## CVM Resource Parameters

| Parameter | Purpose | Accepted Values | Notes |
|-----------|---------|----------------|-------|
| `svm_gb_ram` | CVM RAM allocation in GB | Positive integer | Required for PXE installations |
| `svm_num_vcpus` | CVM vCPU allocation | Positive integer | Required for PXE installations |

## Node Identification Parameters

| Parameter | Purpose | Accepted Values | Notes |
|-----------|---------|----------------|-------|
| `model` | Hardware model | String (e.g., `NX-3060-G7`) | Required |
| `node_position` | Node position in block | String | Required |
| `block_id` | Block ID | Alphanumeric with `-` and `_` | Required |
| `node_serial` | Node serial number | Alphanumeric with `-` and `_` | Required |
| `cluster_id` | Cluster ID | Positive integer | Required |
| `node_name` | Node name | String | Defaults to `{block_id}-{node_position}` |
| `cluster_name` | Cluster name | String | Defaults to `NTNX` |

## Storage Configuration Parameters

| Parameter | Purpose | Accepted Values | Notes |
|-----------|---------|----------------|-------|
| `storage_passthru` | Enable storage passthrough | `true` or `false` | Defaults to `true` |
| `passthru_nvme_devices` | NVMe devices to pass through | List of device paths | For direct device access |
| `passthru_devs` | Devices to pass through | List of device paths | Used by CE |

## Environment Flags

| Parameter | Purpose | Accepted Values | Notes |
|-----------|---------|----------------|-------|
| `COMMUNITY_EDITION` | CE mode flag | `1` or environment variable | Set to `1` for CE installation |
| `IMG` | Image type | `squashfs` | Specifies the image type |
| `FOUND_IP` | Foundation server IP | Valid IP address | Used for connectivity checks |

## Validation Rules

1. If any host network parameter is provided (`host_ip`, `host_subnet_mask`, `default_gw`), all three must be provided
2. If any CVM network parameter is provided (`svm_ip`, `svm_subnet_mask`, `svm_default_gw`), all three must be provided
3. IP addresses cannot be in the 192.168.5.x network (reserved)
4. EULA must be both viewed and accepted
5. Compute-only installations cannot create a 1-node cluster
6. Compute-only installations must use `hyp_install_type=clean`
7. Compute-only installations are only supported on AHV by default (ESXi requires feature flag)

## Minimal Required Parameters for CE Installation

For a basic CE installation, these parameters are required:
- `ce_hyp_boot_disk`
- `ce_cvm_boot_disks`
- `ce_cvm_data_disks`
- `ce_eula_accepted=true`
- `ce_eula_viewed=true`
- `COMMUNITY_EDITION=1`

For a fully automated installation, add:
- Network parameters for host and CVM
- Node identification parameters
- `create_1node_cluster=true` (if creating a cluster)

## NVMe Configuration Example

For servers with NVMe drives, use device paths like:

```json
{
  "ce_hyp_boot_disk": "/dev/nvme0n1",
  "ce_cvm_boot_disks": ["/dev/nvme1n1"],
  "ce_cvm_data_disks": ["/dev/nvme2n1", "/dev/nvme3n1", "/dev/nvme4n1"]
}
```

The NVMe naming convention follows: `/dev/nvme[controller]n[namespace]p[partition]`

## Parameters for Our NVMe Server Use Case

For our specific server with 1 x 480 GB boot drive and 4 x 7680 GB data drives, the following parameters are needed:

### Kernel Command Line Parameters

```
init=/ce_installer
IMG=squashfs
console=tty0 console=ttyS0,115200
FOUND_IP={Config.PXE_SERVER_DNS}
PHOENIX_IP={node['management_ip']}
MASK={network_info['netmask']}
GATEWAY={network_info['gateway']}
NAMESERVER={network_info['dns']}
ce_hyp_boot_disk=/dev/nvme0n1
ce_cvm_boot_disks=/dev/nvme1n1
ce_cvm_data_disks=/dev/nvme2n1,/dev/nvme3n1,/dev/nvme4n1
ce_eula_accepted=true
ce_eula_viewed=true
create_1node_cluster=true
COMMUNITY_EDITION=1
```

### JSON Configuration

```json
{
  "hyp_type": "kvm",
  "model": "NX-3060-G7",
  "node_position": "A",
  "block_id": "BLOCK-123",
  "node_serial": "SERIAL-456",
  "cluster_id": 1,
  "node_name": "BLOCK-123-A",
  "cluster_name": "CE-Cluster",
  
  "hyp_install_type": "clean",
  "svm_install_type": "clean",
  
  "ce_hyp_boot_disk": "/dev/nvme0n1",
  "ce_cvm_boot_disks": ["/dev/nvme1n1"],
  "ce_cvm_data_disks": ["/dev/nvme2n1", "/dev/nvme3n1", "/dev/nvme4n1"],
  
  "host_ip": "192.168.1.100",
  "host_subnet_mask": "255.255.255.0",
  "default_gw": "192.168.1.1",
  
  "svm_ip": "192.168.1.101",
  "svm_subnet_mask": "255.255.255.0",
  "svm_default_gw": "192.168.1.1",
  
  "dns_ip": "8.8.8.8",
  "per_node_ntp_servers": "pool.ntp.org,time.google.com",
  
  "svm_gb_ram": 48,
  "svm_num_vcpus": 16,
  
  "create_1node_cluster": true,
  "ce_eula_accepted": true,
  "ce_eula_viewed": true
}
```

### Disk Layout

Our server has the following NVMe disk configuration:
- `/dev/nvme0n1`: 480 GB boot drive with partitions (p1-p4)
- `/dev/nvme1n1`: System drive with partitions (p1-p4)
- `/dev/nvme2n1`: 7680 GB data drive
- `/dev/nvme3n1`: 7680 GB data drive
- `/dev/nvme4n1`: 7680 GB data drive

This configuration provides approximately 23 TB of usable storage for Nutanix after accounting for redundancy and overhead.

## Command Line vs. JSON Configuration: Explanation

We included both a command line and JSON configuration in the documentation because they represent two different methods of configuring Nutanix CE, each used at different stages of the installation process:

### Kernel Command Line Parameters

The command line parameters are used during the **initial boot process** when using iPXE/PXE boot. These parameters are passed directly to the Linux kernel and the CE installer via the boot loader. This is what we modified in `boot_service.py` for the automated iPXE boot process.

**When to use**:
- During automated PXE/iPXE network boot
- When you need to pass parameters directly to the installer at boot time
- For unattended installations initiated via network boot

### JSON Configuration

The JSON configuration is used by the **Nutanix Foundation** tool or when the installer reads a configuration file after booting. This structured format is easier to manage, validate, and store.

**When to use**:
- When using the Nutanix Foundation tool for deployment
- When creating configuration files to be read by the installer
- For more complex configurations that are easier to manage in a structured format
- When you want to store and version your configurations

### Relationship Between the Two

In many Nutanix CE deployment scenarios, both methods are used together:

1. The kernel command line contains the minimal parameters needed to boot and locate additional configuration
2. The full JSON configuration is then retrieved by the installer (often via a URL specified in the kernel parameters, like the `AZ_CONF_URL` parameter we discussed)

This two-stage approach allows for a cleaner separation between boot parameters and full configuration, making the system more flexible and maintainable.

For our specific use case with the NVMe server, we might use either approach depending on the deployment method:
- The command line parameters if using iPXE boot (as configured in `boot_service.py`)
- The JSON configuration if using Foundation or a configuration file