# Nutanix CE iPXE Automated Installation Guide

This guide covers the complete process for automated Nutanix Community Edition installation on IBM Cloud VPC Bare Metal servers using iPXE and HTTP boot.

The standard install involes:

1. Downloading the Nutanix ISO.
2. Using a utility such as Rufus to write to a CD-ROM or USB.
3. Use the CD-ROM/USB as a boot device.
4. Use the graphical installer, Nutanix Community Edition Installer, to enter the parameters:
   * Select Hypervisor: AHV or ESXi.
   * Select Hypervisor Boot disk.
   * Select CUM Boot disk.
   * Select Data disks.
   * Host IP Address.
   * CUM IP Address.
   * Subnet Mask.
   * Gateway.
   * DNS Server.
   * Create single-node cluster: Y/N.
   * Accept the EULA.
5. SSH to the CVM appliance created and complete the setup.

## Overview

Instead of using the graphical installer, this method allows completely unattended installation using:
- **iPXE** for network booting
- **Arizona configuration** for automation parameters
- **HTTP server** to serve installation files
- **Modified initrd** to support HTTP-based squashfs.img loading

## Prerequisites

- IBM Cloud VPC Bare Metal server with iPXE boot capability
- HTTP server accessible from the target server
- Nutanix CE ISO file
- Basic understanding of network configuration

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

## Architecture

This solution works because the PXE/Config server is pre-configured with extracted and modified files from the Nutanix CE ISO file:

1. **iPXE** downloads **kernel** and **initrd** over HTTP.
2. **initrd** boots and downloads **squashfs.img** (root filesystem).
3. **Phoenix** installer reads **Arizona** config for automation.
4. Installs **AHV** hypervisor and **CVM** on bare metal.

This results in a node that is ready to be become a single node cluster, or join with other nodes in a standard cluster and be accessible via **Prism**.

```
IBM Bare Metal Server (iPXE) → HTTP Server → Automated Installation
                ↓
1. Boot kernel + initrd via HTTP
2. Download squashfs.img (root filesystem)  
3. Download arizona.cfg (automation config)
4. Download AOS installer + AHV ISO
5. Automated installation based on config
```

To achieve this the following steps are needed on the PXE\Config Server to overcome the following issues:

- The Nutanix CE ISO is designed to be used in a CD-ROM or a virtual CD-ROM, not used for iPXE.
- The installer is hard-coded to look for a block device (CD_ROM) with a label named "PHOENIX".
- The installer is configured to launch into a UI.

The issues above are overcome by mounting the ISO and changing the installer.

## Step 1: Extract Files from Nutanix CE ISO

Mount the ISO so we can access the files

### 1.1 Mount the ISO
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


### 1.2 Extract Boot File and squashfs.img

The boot files `kernel` and `squashfs.img` are copied so that they can be served when requested.

```bash
# Create web server directory structure
sudo mkdir -p /var/www/pxe

# Extract kernel and copy to /var/www/pxe/images (it is renamed for no real reason!)
sudo cp /mnt/boot/kernel /var/www/pxe/images/kernel

# Extract squashfs root filesystem and copy to /var/www/pxe/image
sudo cp /mnt/squashfs.img /var/www/pxe/images
```

### 1.3 Extract AOS Installer Package

Th AOS installer will create the CVM during the install. On the ISO there are two parts to the package, we combine them for ease of use

```bash
# Copy split installer parts
sudo cp /mnt/images/svm/nutanix_installer_package.tar.p* /var/www/pxe/images

# Reconstruct complete installer
cd /var/www/pxe/images
sudo cat nutanix_installer_package.tar.p* > nutanix_installer_package.tar.gz
sudo rm nutanix_installer_package.tar.p*
```

### 1.4 Extract AHV Hypervisor ISO
```bash
# Copy AHV ISO
sudo cp "/mnt/images/hypervisor/kvm/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso" /var/www/pxe/images
```

### 1.5 Generate MD5 Checksums
```bash
echo "=== File Checksums for Arizona Config ==="
echo "AOS Installer:"
md5sum nutanix_installer_package.tar.gz

echo "AHV ISO:"
md5sum AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso

echo "SquashFS:"
md5sum squashfs.img
```

## Step 2: Modify initrd for HTTP Support

The default Nutanix installer looks for a device labeled "PHOENIX". Since we're network booting, we need to modify the installer to download squashfs.img via HTTP.

### 2.1 Extract initrd
```bash
mkdir -p /tmp/nutanix-initrd
cd /tmp/nutanix-initrd
gunzip -c /mnt/boot/initrd | cpio -idmv
```

### 2.2 Modify livecd.sh

The `livecd.sh` is hard-coded to look for a block device with the name  `PHOENIX`. We need to change this so we download `squashfs.img` from the PXE\Config server.

Edit `/tmp/nutanix-initrd/livecd.sh` and replace the `find_squashfs_in_iso_ce()` function, with the following function:

```bash
find_squashfs_in_iso_ce ()
{
  # First try to download squashfs.img directly via HTTP
  if [ -n "$LIVEFS_URL" ]; then
    echo "Attempting to download squashfs.img from $LIVEFS_URL"
    wget "$LIVEFS_URL" -t3 -T60 -O /root/squashfs.img
    if [ $? -eq 0 -a -f /root/squashfs.img ]; then
      echo "Successfully downloaded squashfs.img from HTTP"
      # Verify MD5 if needed
      md5sum /root/squashfs.img | grep $IMG_MD5SUM
      if [ $? -eq 0 ]; then
        return 0
      else
        echo "MD5 checksum mismatch, trying alternative methods"
        rm -f /root/squashfs.img
      fi
    else
      echo "HTTP download failed, trying to find Phoenix ISO device"
    fi
  fi

  # Fall back to original method - look for PHOENIX labeled device
  echo "Looking for device containing Phoenix ISO..."
  for retry in `seq 1 15`; do
    PHX_DEV=$(blkid | grep 'LABEL="PHOENIX"' | cut -d: -f1)
    ret=$?
    if [ $ret -eq 0 -a "$PHX_DEV" != "" ]; then
      mount $PHX_DEV /mnt/iso
      if [ $? -eq 0 ]; then
        if [ -f /mnt/iso/squashfs.img ]; then
          echo -e "\nCopying squashfs.img from Phoenix ISO on $PHX_DEV"
          cp -rf /mnt/iso/squashfs.img /root/
          return 0
        else
          umount /mnt/iso
        fi
      fi
    fi
    echo -en "\r [$retry/15] Waiting for Phoenix ISO to be available ..."
    sleep 2
  done

  echo "Failed to find Phoenix ISO."
  return 1
}
```

### 2.3 Repack initrd
```bash
cd /tmp/nutanix-initrd
find . | cpio -o -H newc | gzip > /var/www/pxe/images/initrd-modified
```

## Step 3: Create Arizona Configuration

The automation parameters are served via the API when called with `/boot/server/<server_ip>`. The PXE\Confog server will respond with a json file an example is shown below. The disk information is retreived from `server_profiles.py`, the IP information is retrieved from the database.

### 3.1 Node Configuration
```json
{
  "hyp_type": "kvm",
  "node_position": "A",
  "svm_installer_url": {
    "url": "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/nutanix_installer_package.tar.gz",
    "md5sum": "actual_md5_checksum_here"
  },
  "hypervisor_iso_url": {
    "url": "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso",
    "md5sum": "actual_ahv_iso_md5_checksum_here"
  },
  "nodes": [
    {
      "node_position": "A",
      "hyp_ip": "10.240.0.10",
      "hyp_netmask": "255.255.255.0",
      "hyp_gateway": "10.240.0.1",
      "svm_ip": "10.240.0.51",
      "svm_netmask": "255.255.255.0",
      "svm_gateway": "10.240.0.1",
      "disk_layout": {
        "boot_disk": "/dev/nvme0n1",
        "cvm_disk": "/dev/nvme0n1",
        "storage_pool_disks": ["/dev/nvme1n1", "/dev/nvme2n1", "/dev/nvme3n1", "/dev/nvme4n1"]
      }
    }
  ],
  "dns_servers": "161.26.0.7,161.26.0.8",
  "ntp_servers": "time.adn.networklayer.com",
  "skip_hypervisor": false,
  "install_cvm": true
}
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

### 3.2 Configuration Parameters Explained

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

## Step 4: Create iPXE Boot Script

The iPXE boot script is served via the API when called with `/boot/config?mgmt_ip=<server_ip>`. The PXE\Confog server will respond with an iPXE file, an example is shown below:

```bash
#!ipxe

# Set timeouts for large file downloads
set net-timeout 300000
set http-timeout 300000

# Boot Nutanix CE with automated installation
kernel http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/kernel init=/ce_installer intel_iommu=on iommu=pt kvm-intel.nested=1 kvm.ignore_msrs=1 kvm-intel.ept=1 vga=791 net.ifnames=0 mpt3sas.prot_mask=1 IMG=squashfs LIVEFS_URL=http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/squashfs.img AZ_CONF_URL=http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/arizona.cfg PHOENIX_IP=10.240.0.10 MASK=255.255.255.0 GATEWAY=10.240.0.1 PXEBOOT=true
initrd http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/initrd-modified
boot
```

### 4.1 Kernel Parameters Explained

| Parameter | Purpose |
|-----------|---------|
| `init=/ce_installer` | Run Community Edition installer |
| `intel_iommu=on iommu=pt` | Enable IOMMU for virtualization |
| `kvm-intel.nested=1` | Enable nested virtualization |
| `LIVEFS_URL` | URL to download squashfs.img |
| `AZ_CONF_URL` | URL to Arizona configuration file |
| `PHOENIX_IP` | Static IP for installer |
| `PXEBOOT=true` | Indicate PXE boot mode |

## Step 5: Verify files are accessible

```bash
curl -I http://your-server-ip/squashfs.img
curl -I http://your-server-ip/arizona.cfg
```

### 5.1 Required File Structure
```bash
/var/www/pxe/images
├── kernel
├── initrd-modified
├── squashfs.img
├── nutanix_installer_package.tar.gz
├── AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso
```

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

## Conclusion

This method provides a completely automated, scriptable way to deploy Nutanix CE on bare metal servers without manual intervention. It's particularly useful for:

- **Cloud environments** like IBM Cloud VPC
- **Mass deployments** of multiple nodes
- **CI/CD integration** for infrastructure as code
- **Factory/OEM installations** requiring automation

The approach leverages Nutanix's built-in Arizona automation framework while adapting it for network boot scenarios where traditional CD/USB media isn't available.
