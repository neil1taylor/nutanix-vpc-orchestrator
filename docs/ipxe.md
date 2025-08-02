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
dhcp                            # Get IP address from DHCP server
kernel http://server/vmlinuz    # Download and load kernel
initrd http://server/initrd.img # Download initial ramdisk
boot                            # Start the kernel
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

**In our context**:
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
```bash
# Inside initrd, these processes happen:
- Hardware detection
- Network interface initialization
- Download of kickstart file
- Preparation for main installation
- Mounting of installation media
```

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
wget -O /tmp/nutanix-config.json http://server/config.json
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

1. **Server Powers On**
   - BIOS/UEFI configured for network boot
   - PXE ROM requests IP via DHCP
   - DHCP server responds with IP and iPXE script location

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

### PXE Server Directory Structure
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
├── inst.repo=http://server/nutanix-ce/repo
├── inst.ks=http://server/config/kickstart.cfg
├── console=tty0 console=ttyS0,115200
└── ip=dhcp

Kickstart References:
├── wget http://server/config/nutanix-config.json
└── wget http://server/nutanix-ce-installer.tar.gz
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