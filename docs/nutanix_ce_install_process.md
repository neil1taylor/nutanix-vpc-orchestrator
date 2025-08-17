# Nutanix CE  Installation Guide

This guide describes the Nutanix Community Edition installation. The standard install involves:

1. Downloading the Nutanix ISO.
2. Using a utility such as Rufus to write to a CD-ROM or USB.
3. Use the CD-ROM/USB as a boot device.
4. Use the graphical installer, Nutanix Community Edition Installer, to enter the parameters:
   * Select Hypervisor: AHV or ESXi.
   * Select Hypervisor Boot disk.
   * Select CVM Boot disk.
   * Select Data disks.
   * Host IP Address.
   * CVM IP Address.
   * Subnet Mask.
   * Gateway.
   * DNS Server.
   * Create single-node cluster: Y/N.
   * Accept the EULA.
5. SSH to the CVM appliance created and complete the setup.

## Nutanix and Linux Boot Terminology Terms

This section explains all the key terms used in the Nutanix CE iPXE installation.

### **Kernel**
- **What it is**: The core of the Linux operating system
- **Purpose**: Manages hardware, memory, processes, and system resources
- **In our context**: The `vmlinuz` or `kernel` file that boots the Nutanix installer
- **Location**: `/boot/kernel` in the Nutanix ISO
- **Example**: When iPXE downloads the kernel, it's getting the bootable Linux core

### **initrd (Initial RAM Disk)**
- **What it is**: A compressed filesystem loaded into RAM during boot
- **Purpose**: Contains drivers and tools needed before the main filesystem is mounted
- **In our context**: Contains the Nutanix installer scripts and drivers
- **Why we modified it**: To add HTTP download capability for squashfs.img
- **File format**: Compressed cpio archive (like a .tar.gz file)

### **SquashFS**
- **What it is**: A compressed, read-only filesystem format
- **Purpose**: Packages entire operating systems into a single compressed file
- **In our context**: `squashfs.img` contains the complete Nutanix installer environment
- **Benefits**: High compression (50-90% size reduction), fast random access
- **Usage**: Live CDs, embedded systems, and installers use this format

### **AHV (Acropolis Hypervisor)**
- **What it is**: Nutanix's own hypervisor based on KVM/Linux
- **Purpose**: Virtualizes hardware to run virtual machines
- **Alternative to**: VMware ESXi, Microsoft Hyper-V
- **In our context**: The `hyp_type: "kvm"` in arizona.cfg installs AHV
- **File**: `AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso`

### **CVM (Controller Virtual Machine)**
- **What it is**: Special VM that runs Nutanix storage and management software
- **Purpose**: Provides distributed storage services and cluster management
- **Architecture**: Runs on each physical node, forms distributed storage system
- **In our context**: Gets IP address `svm_ip` in arizona.cfg
- **Access**: Prism web interface runs on CVM at port 9440

### **Phoenix**
- **What it is**: Nutanix's installation and imaging framework
- **Components**: 
    - Shell scripts for hardware detection and preparation
    - Python application for main installation logic
    - Web-based GUI for configuration
- **In our context**: The main installer that arizona.cfg configures
- **Execution**: Launched after initrd boots and prepares environment

### **Arizona**
- **What it is**: Nutanix's automation framework for unattended installations
- **Purpose**: Allows scripted, non-interactive deployments
- **File format**: JSON configuration file
- **In our context**: `arizona.cfg` contains all installation parameters
- **Benefits**: Enables factory installations, PXE deployments, mass rollouts

### **Foundation**
- **What it is**: Nutanix's cluster deployment and management tool
- **Purpose**: Deploys and configures multi-node Nutanix clusters
- **Relationship**: Arizona is Foundation's automation backend
- **In our context**: Parameters like `FOUND_IP` refer to Foundation server

### **iPXE**
- **What it is**: Enhanced network boot firmware/software
- **Purpose**: Boots computers over network instead of local storage
- **Capabilities**: HTTP/HTTPS downloads, scripting, advanced protocols
- **In our context**: Downloads and boots Nutanix installer over network
- **Advantage**: More flexible than traditional PXE

### **PXE (Preboot Execution Environment)**
- **What it is**: Industry standard for network booting
- **Protocol**: Uses DHCP + TFTP for boot process
- **Limitations**: Only TFTP, no scripting, basic functionality
- **Relationship**: iPXE is an enhanced, modern replacement for PXE

### **Node Position**
- **What it is**: Identifier for each server in a cluster (A, B, C, etc.)
- **Purpose**: Determines installation order, cluster roles, and configuration
- **In our context**: `"node_position": "A"` in arizona.cfg
- **Convention**: A = first node/leader, B = second node, etc.
- **Usage**: Maps to physical rack positions in data centers

### **Container (Storage)**
- **What it is**: Nutanix's logical storage pool abstraction
- **Purpose**: Groups storage across cluster nodes for VM storage
- **Not Docker**: Different from Docker containers - this is storage
- **In our context**: Created after installation for VM storage
- **Management**: Configured via Prism web interface

### **Prism**
- **What it is**: Nutanix's web-based management interface
- **Purpose**: Cluster management, VM creation, monitoring, configuration
- **Access**: `https://<cvm_ip>:9440`
- **In our context**: Used after installation to manage the cluster
- **Features**: Dashboard, VM management, storage configuration, monitoring

### **CPIO**
- **What it is**: Archive format similar to tar
- **Purpose**: Packages multiple files into single archive
- **In our context**: initrd files are cpio archives
- **Commands**: `cpio -i` (extract), `cpio -o` (create)
- **Usage**: Common in Linux boot processes and embedded systems

### **MD5Sum**
- **What it is**: Cryptographic hash for file integrity verification
- **Purpose**: Ensures downloaded files aren't corrupted
- **In our context**: arizona.cfg includes MD5 hashes for all downloaded files
- **Format**: 32-character hexadecimal string
- **Example**: `"md5sum": "a1b2c3d4e5f6..."`

### **Split Archives (.p00, .p01)**
- **What it is**: Large files split into smaller chunks
- **Purpose**: Makes large files easier to handle and transfer
- **In our context**: AOS installer is split into `.tar.p00` and `.tar.p01`
- **Reconstruction**: `cat file.tar.p* > file.tar.gz`
- **Reason**: Filesystem or transfer limitations for large files

### **LIVEFS_URL**
- **What it is**: Kernel parameter pointing to root filesystem
- **Purpose**: Tells installer where to download squashfs.img
- **In our context**: Our HTTP URL serving the root filesystem
- **Format**: `LIVEFS_URL=http://server/squashfs.img`
- **Usage**: Alternative to local storage or CD/DVD

### **AZ_CONF_URL**
- **What it is**: Kernel parameter pointing to Arizona configuration
- **Purpose**: Tells Phoenix where to get automation settings
- **In our context**: Our HTTP URL serving arizona.cfg
- **Format**: `AZ_CONF_URL=http://server/arizona.cfg`
- **Result**: Enables completely automated installation

### **init Process**
- **What it is**: First process started by Linux kernel
- **Purpose**: Starts all other system processes
- **In our context**: `init=/ce_installer` tells kernel to run CE installer
- **Normal**: Usually `/sbin/init` or systemd
- **Override**: We override to run Nutanix installer instead

### **Screen Session**
- **What it is**: Terminal multiplexer that persists sessions
- **Purpose**: Keeps processes running even if connection drops
- **In our context**: Phoenix installer runs in screen session
- **Benefits**: Can reconnect to installer if SSH connection fails
- **Commands**: `screen -r` to reconnect to session

### **Switch Root**
- **What it is**: Linux mechanism to change root filesystem
- **Purpose**: Transitions from initrd to main filesystem
- **In our context**: Switches from initrd to squashfs.img
- **Process**: Mounts new root, moves processes, switches context
- **Result**: System now runs from squashfs environment

## Why initrd and a squashfs

### **Different Purposes:**

**Initrd (Initial RAM Disk):**
- **Minimal boot environment** - Just enough to get the system started
- **Hardware detection** - Network drivers, storage drivers, basic utilities
- **Bootstrap logic** - PXE networking, finding and mounting the squashfs
- **Small and fast** - Loads quickly over network/from storage

**Squashfs:**
- **Complete userspace** - Full Python environment, all installation tools
- **Large application payload** - The actual Nutanix installer and dependencies
- **Compressed efficiently** - Much better compression than initrd formats

### **Technical Constraints:**

1. **Size limits** - Initrd has practical size limits for network booting
2. **Memory usage** - Initrd stays in RAM; squashfs can be streamed/cached
3. **Compression** - Squashfs compression is much more efficient than cpio/gzip used in initrd

### **Practical Benefits:**

```bash
┌─────────────┐    ┌──────────────────┐
│   Initrd    │ →  │    Squashfs      │
│ (~50-100MB) │    │   (~500MB-2GB)   │
├─────────────┤    ├──────────────────┤
│ • Drivers   │    │ • Python + libs  │
│ • Busybox   │    │ • Full installer │
│ • Network   │    │ • All packages   │
│ • Basic sh  │    │ • Complete OS    │
└─────────────┘    └──────────────────┘
```

### **Why not combine them:**

1. **Boot speed** - Small initrd boots faster over PXE
2. **Modularity** - Can update installer (squashfs) without changing boot logic (initrd)  
3. **Flexibility** - Different squashfs images for different versions/platforms
4. **Network efficiency** - Initrd is downloaded first, then can intelligently fetch the right squashfs
5. **Memory management** - Initrd can be discarded after setting up overlay

**Think of it like:** Initrd is the "bootloader" that gets you to a point where you can load the "real operating system" (squashfs).

This is a common pattern in Linux distributions - even regular Linux uses initrd to load drivers, then mounts the real root filesystem.

## Issues to overcome for IBM Cloud VPC Bare Metal Servers

The following issues need to be overcome:

- The Nutanix CE ISO is designed to be used in a CD-ROM or a virtual CD-ROM, not used for iPXE.
- The installer is hard-coded to look for a block device (CD_ROM) with a label named "PHOENIX".
- The installer is configured to launch into a UI.
- The installer does not have ionic drivers
- The installer does hardware checks which are not suitable for IBM Cloud VPC servers
- The Installer tries to access the ipmi

Note: "The installer" is a collection of `.sh` and `.py` scripts.

## The Nutanix CE ISO

When mounted, the ISO has the following contents

```bash
sudo mkdir /mnt
sudo mount -o loop nutanix-ce.iso /mnt
```

The `/mnt` directory now contains:

```bash
/mnt
├── EFI
│   └── BOOT
│       ├── BOOTX64.EFI
│       ├── grub.cfg
│       └── grubx64.efi
├── boot
│   ├── images
│   │   └── efiboot.img
│   ├── initrd
│   ├── isolinux
│   │   ├── cat.c32
│   │   ├── chain.c32
│   │   ├── cmd.c32
│   │   ├── config.c32
│   │   ├── cpuid.c32
│   │   ├── cpuidtest.c32
│   │   ├── disk.c32
│   │   ├── dmitest.c32
│   │   ├── elf.c32
│   │   ├── ethersel.c32
│   │   ├── gfxboot.c32
│   │   ├── gpxecmd.c32
│   │   ├── hdt.c32
│   │   ├── host.c32
│   │   ├── ifcpu.c32
│   │   ├── ifcpu64.c32
│   │   ├── ifplop.c32
│   │   ├── isolinux.bin
│   │   ├── isolinux.cfg
│   │   ├── kbdmap.c32
│   │   ├── linux.c32
│   │   ├── ls.c32
│   │   ├── lua.c32
│   │   ├── mboot.c32
│   │   ├── meminfo.c32
│   │   ├── menu.c32
│   │   ├── pcitest.c32
│   │   ├── pmload.c32
│   │   ├── pwd.c32
│   │   ├── reboot.c32
│   │   ├── rosh.c32
│   │   ├── sanboot.c32
│   │   ├── sdi.c32
│   │   ├── sysdump.c32
│   │   ├── vesainfo.c32
│   │   ├── vesamenu.c32
│   │   ├── vpdtest.c32
│   │   ├── whichsys.c32
│   │   └── zzjson.c32
│   └── kernel
├── boot.catalog
├── images
│   ├── driver_package.tar.gz
│   ├── hypervisor
│   │   └── kvm
│   │       └── AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso
│   └── svm
│       ├── nutanix_installer_package.tar.p00
│       └── nutanix_installer_package.tar.p01
├── make_iso.sh
├── phoenix_version
├── squashfs.img
└── templates
    ├── grub2.cfg
    └── grub_efi.cfg
```

### Example Bare Metal Server configuration

#### **Boot Disk (RAID)**
- **Device**: `/dev/nvme0n1`
- **Size**: 447 GB (480GB raw)
- **Model**: M.2 NVMe 2-Bay RAID Kit
- **Purpose**: This is the hardware RAID 1 boot array presented as single NVMe device

#### **Storage Pool Disks**
- **Devices**: `/dev/nvme1n1`, `/dev/nvme2n1`, `/dev/nvme3n1`, `/dev/nvme4n1`
- **Size**: 6.99 TiB each (~7.68TB raw)
- **Model**: Micron_7450_MTFDKCC7T6TFR (Enterprise NVMe SSDs)
- **Total Storage**: ~28TB of high-performance NVMe storage

#### What This Gives You:

**447GB for hypervisor + CVM** - More than enough for both  
**~28TB for Nutanix storage pool** - Massive high-performance storage  
**All NVMe SSDs** - Exceptional performance across the board  
**RAID 1 boot protection** - Hardware redundancy for boot disk  

#### Storage Performance:

These **Micron 7450 enterprise NVMe drives** provide:
- **Sequential Read**: Up to 6.9 GB/s  
- **Sequential Write**: Up to 6.2 GB/s
- **Random Read IOPS**: Up to 1.5M IOPS
- **Random Write IOPS**: Up to 400K IOPS

This will provide Nutanix CE with:
- **Fast boot** from RAID-protected NVMe
- **Massive storage capacity** (28TB)
- **Enterprise-grade performance** 

### Key Configuration Parameters Explained

| Parameter | Purpose | Required |
|-----------|---------|----------|
| `hyp_type` | Hypervisor type (`"kvm"` for AHV) | Yes |
| `node_position` | Node identifier (A, B, C, etc.) | Yes |
| `svm_installer_url` | AOS installer package location | Yes |
| `hypervisor_iso_url` | AHV ISO location (for kvm type) | Yes |
| `nodes[]` | Network configuration for each node | Yes |
| `dns_servers` | DNS server addresses | Recommended |
| `ntp_servers` | NTP server addresses | Recommended |
| `skip_hypervisor` | Whether to skip hypervisor install | No |
| `install_cvm` | Whether to install CVM | No |


### Kernel Parameters Explained

| Parameter | Purpose |
|-----------|---------|
| `init=/ce_installer` | Run Community Edition installer |
| `intel_iommu=on iommu=pt` | Enable IOMMU for virtualization |
| `kvm-intel.nested=1` | Enable nested virtualization |
| `LIVEFS_URL` | URL to download squashfs.img |
| `AZ_CONF_URL` | URL to Arizona configuration file |
| `PHOENIX_IP` | Static IP for installer |
| `PXEBOOT=true` | Indicate PXE boot mode |



## Step 6: Boot Target Server

### 6.1 iPXE Boot Methods

**Option A: Direct iPXE commands**
```bash
# IBM Cloud userdata
http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/config?mgmt_ip=10.240.0.10
```

### 6.2 Installation Process

1. **Network Boot**: Server boots via iPXE
2. **Kernel Load**: Downloads and boots Nutanix kernel
3. **Root FS**: Downloads squashfs.img as root filesystem
4. **Configuration**: Downloads arizona.cfg for automation
5. **Package Download**: Downloads AOS installer and AHV ISO
6. **Installation**: Automated installation based on configuration
7. **Completion**: Server reboots into installed Nutanix CE

## Troubleshooting

### Common Issues

**1. "Failed to find Phoenix ISO"**
- Check LIVEFS_URL parameter is correct
- Verify squashfs.img is accessible via HTTP
- Ensure modified initrd is being used

**2. "Input/output error" during download**
- Increase net-timeout and http-timeout values
- Check network connectivity from target server
- Verify HTTP server is responding

**3. "Failed to download squashfs.img"**
- File too large for network/memory constraints
- Try extracting kernel/initrd method instead
- Check HTTP server timeout settings

**4. Installation hangs or fails**
- Verify all MD5 checksums in arizona.cfg
- Check target server meets minimum requirements
- Review arizona.cfg syntax and required parameters

### Log Locations
- **Installation logs**: `/tmp/phoenix.log`
- **Network logs**: Check DHCP/network configuration
- **HTTP server logs**: Check web server access logs

## Post-Installation

### Access Prism Web Interface
- **URL**: `https://<cvm_ip>:9440`
- **Default credentials**: Check Nutanix documentation
- **Cluster configuration**: Complete via web interface for multi-node

### Next Steps
1. **Configure storage containers** via Prism
2. **Set up VM networks** as needed
3. **Add additional nodes** to form cluster
4. **Configure backup and monitoring** as required


## Nutanix CE Installation Process

The execution flow from `ce_installer` to the main `phoenix` installer  is a multi-step process through several shell scripts and Python programs.

## Execution Flow Diagram

```bash
ce_installer (symlink) 
    ↓
livecd.sh (detects CE mode)
    ↓  
do_ce_installer.sh (sets CE environment)
    ↓
do_installer.sh (prepares and launches)
    ↓
phoenix (Python installer)
```

## Step-by-Step Breakdown

### 1. **ce_installer → livecd.sh**

`ce_installer` is actually a **symbolic link** to `livecd.sh`:

```bash
# In the initrd/squashfs
ce_installer -> livecd.sh
```

When `init=/ce_installer` is passed as a kernel parameter, it executes `livecd.sh`.

### 2. **livecd.sh Logic Detection**

In `livecd.sh`, this code detects Community Edition mode:

```bash
ce=0
if [ "${0##*/}" == "ce_installer" ]; then
  ce=1
fi
```

Since the script was called as `ce_installer`, `ce=1` is set, enabling CE-specific behavior.

### 3. **livecd.sh → do_ce_installer.sh**

At the end of `livecd.sh`:

```bash
script=${0##*/}  # script = "ce_installer"

if [ -e "$HOME/do_${script}.sh" ]; then
  . "$HOME/do_${script}.sh"    # Sources do_ce_installer.sh
else
  echo "ERROR: $HOME/do_${script}.sh not found."
  drop_to_shell
fi
```

This **sources** (executes) `do_ce_installer.sh`.

### 4. **do_ce_installer.sh Environment Setup**

`do_ce_installer.sh` sets up Community Edition environment:

```bash
export COMMUNITY_EDITION=1

# Read network info if available
CE_NET_INFO=""
if [ -f /mnt/stage/root/.host_net_info ]; then
  CE_NET_INFO=`cat /mnt/stage/root/.host_net_info`
fi
if [ -f /mnt/stage/root/.cvm_net_info ]; then
  CE_NET_INFO=$CE_NET_INFO" "
  CE_NET_INFO=$CE_NET_INFO`cat /mnt/stage/root/.cvm_net_info`
fi
if [ ! -z "$CE_NET_INFO" ]; then
  export CE_INSTALLED=`echo $CE_NET_INFO`
fi

# Remove any previous install markers
rm -f /mnt/stage/root/.ce_install_success

# Call the main installer
sh /root/do_installer.sh
```

### 5. **do_installer.sh → phoenix**

`do_installer.sh` prepares the Python environment and launches the main installer:

```bash
# Install foundation layout Python package
/usr/bin/easy_install -Z --no-find-links --no-deps /root/phoenix/egg_basket/foundation_layout*.egg 1>/dev/null

# Change to phoenix directory
cd /phoenix

# Apply any patches/updates
./patch_phoenix.py --url $UPDATES_CONFIG_URL

# Install additional components
/phoenix/install_components.py

# Determine the init script name
script=$(grep "init=" /proc/cmdline | sed "s/.*init="'\(\S*\).*/\1/')

# Launch phoenix in screen session for CE
if [[ -e '/etc/redhat-release' && ($(basename $script) = "installer" || $(basename $script) = "ce_installer") ]]; then
 screen -dmSL centos_phoenix ./phoenix $@
else
 ./phoenix $@
fi
```

### 6. **phoenix Python Application**

Finally, `phoenix` (the Python script) runs with the `COMMUNITY_EDITION=1` environment variable set.

In `phoenix` (Python), this environment variable triggers CE-specific behavior:

```python
def main():
  cmdline_args = sysUtil.parse_cmd_line()
  unattended = False

  # ... (Arizona configuration handling)

  elif 'COMMUNITY_EDITION' in os.environ:
    params = gui.get_params(gui.CEGui)  # Launch CE GUI instead of full GUI
  
  # ... (rest of installation logic)
```

## Key Points in the Chain

### **Environment Variables Set:**
- `COMMUNITY_EDITION=1` - Triggers CE mode in Python
- `CE_INSTALLED` - Contains previous network info if available

### **Working Directory Changes:**
- Starts in `/` (root)
- Changes to `/phoenix` before launching Python installer

### **Screen Session:**
- CE installer runs in a `screen` session named `centos_phoenix`
- Allows reconnection if SSH session drops

### **Error Handling:**
- Each step has error checking
- Falls back to shell on failure (`drop_to_shell`)

## Why This Multi-Step Process?

1. **Modularity**: Each script handles a specific phase
2. **Environment Setup**: Gradual environment preparation
3. **Error Recovery**: Multiple checkpoints for debugging
4. **Flexibility**: Same framework supports different installer modes
5. **Legacy Support**: Maintains compatibility with older deployment methods

## Summary

The path is: **Kernel** → **livecd.sh** (with CE detection) → **do_ce_installer.sh** (CE environment) → **do_installer.sh** (Python prep) → **phoenix** (main installer)

Each step builds upon the previous one, ultimately launching the Python-based Nutanix installer with Community Edition settings enabled.

