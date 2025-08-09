# Reverse Engineering Nutanix CE ISO for iPXE Automation

## Overview
This document describes the process of extracting and analyzing a Nutanix Community Edition (CE) ISO to understand its boot parameters and JSON configuration format for automated iPXE deployment.

## Initial Challenge
- Goal: Automate Nutanix CE deployment on IBM Cloud VPC bare metal servers via iPXE
- Problem: No official documentation for automating CE installation
- Constraint: No IPMI access on IBM Cloud VPC bare metal servers

## Step 1: ISO Examination

### 1.1 Mount and Explore the ISO
```bash
# Mount the CE ISO
mount -o loop nutanix-ce.iso /mnt

# Initial exploration
ls /mnt
# Output: EFI  boot  boot.catalog  images  make_iso.sh  phoenix_version  squashfs.img  templates

# Check version
cat /mnt/phoenix_version
# Output: phoenix-5.6.1_8c4d61fc
```

**Finding**: The CE ISO is Phoenix-based (version 5.6.1)

### 1.2 Examine Boot Configuration
```bash
# Check BIOS boot config
cat /mnt/boot/isolinux/isolinux.cfg

# Check UEFI boot config  
cat /mnt/EFI/BOOT/grub.cfg
```

**Key Discovery**: 
- Uses `init=/ce_installer` instead of standard Phoenix's `init=/installer`
- Includes parameter `IMG=squashfs`
- Has standard hypervisor parameters (intel_iommu=on, kvm-intel.nested=1, etc.)

## Step 2: Extract Boot Files for iPXE

### 2.1 Kernel and Initrd Extraction
```bash
# Extract kernel and initrd for PXE booting
cp /mnt/boot/kernel /var/www/pxe/images/vmlinuz-phoenix
cp /mnt/boot/initrd /var/www/pxe/images/initrd-modified.img
```

## Step 3: Analyze the Squashfs Image

### 3.1 Mount Squashfs
```bash
mkdir /tmp/squash
mount -o loop /mnt/squashfs.img /tmp/squash
ls -la /tmp/squash/
```

**Finding**: Squashfs contains the root filesystem but not the installer

### 3.2 Search for Installer
```bash
# Look for installer files
find /tmp/squash -name "*install*" -o -name "*phoenix*" 2>/dev/null

# Check for automation parameters
grep -r "AZ_CONF_URL" /tmp/squash 2>/dev/null
```

**Result**: No installer or automation parameters found in squashfs

## Step 4: Analyze the Initrd

### 4.1 Extract Initrd Contents
```bash
mkdir /tmp/initrd
cd /tmp/initrd
zcat /mnt/boot/initrd | cpio -idm 2>/dev/null
```

### 4.2 Locate Key Files
```bash
# Find installer files
find /tmp/initrd -name "ce_installer" -o -name "*installer*" 2>/dev/null
```

**Critical Discoveries**:
- `/tmp/initrd/ce_installer` - CE-specific installer
- `/tmp/initrd/do_ce_installer.sh` - CE installer wrapper
- `/tmp/initrd/phoenix/` - Phoenix framework directory

### 4.3 Analyze Init Process
```bash
# Check init script
cat /tmp/initrd/init
```

**Understanding**: 
- Init script parses `init=` from kernel cmdline
- Dispatches to specified script (e.g., `/ce_installer`)

## Step 5: Discover Automation Parameters

### 5.1 Search for Configuration Parameters
```bash
# Look for automation parameters
grep -r "FOUND_IP\|AZ_CONF_URL\|AUTO" /tmp/initrd 2>/dev/null
```

**Key Findings**:
- `FOUND_IP` - IP address of Foundation/configuration server
- `AZ_CONF_URL` - URL to fetch JSON configuration
- Both parameters ARE supported in CE installer

### 5.2 Trace Configuration Flow
```bash
# Check CE installer wrapper
cat /tmp/initrd/do_ce_installer.sh

# Examine network configuration handling
grep -r "host_net_info\|cvm_net_info" /tmp/initrd/
```

**Discovery**: CE installer sets `COMMUNITY_EDITION=1` environment variable

## Step 6: Understand JSON Configuration Format

### 6.1 Analyze JSON Loading
```bash
# Check how JSON is loaded
grep -B5 -A10 "json.load\|json.loads" /tmp/initrd/phoenix/arizona.py
```

**Finding**: 
```python
conf = json.load(urlopen(confurl, context=ctx))
for k, v in six.iteritems(conf):
    param_list.__dict__[k] = sub_node_serial(v)
```

JSON keys are directly mapped to param_list attributes

### 6.2 Identify Expected Parameters
```bash
# Check parameter list class
grep "class param_list" /tmp/initrd/phoenix/param_list.py

# Find DNS handling
grep -A5 -B5 "dns_servers" /tmp/initrd/phoenix/*.py | grep "split"
```

**DNS Format Discovery**: Multiple DNS servers use comma-separated format

## Step 7: Final Configuration Format

### 7.1 Determined JSON Structure
Based on analysis, the CE installer expects a flat JSON structure:

```json
{
  "hypervisor_ip": "10.240.0.10",
  "cvm_ip": "10.240.0.101",
  "cluster_name": "ce-cluster",
  "cvm_gb_ram": 48,
  "cvm_num_vcpus": 16,
  "cvm_gateway": "10.240.0.1",
  "cvm_netmask": "255.255.255.0",
  "cvm_dns_servers": "161.26.0.7,161.26.0.8",
  "dns_ip": "161.26.0.7,161.26.0.8",
  "hypervisor_nameserver": "161.26.0.7,161.26.0.8",
  "hypervisor": "kvm"
}
```

### 7.2 iPXE Boot Configuration
```ipxe
#!ipxe
kernel http://${next-server}:8080/images/vmlinuz-phoenix 
  init=/ce_installer 
  intel_iommu=on 
  iommu=pt 
  kvm-intel.nested=1 
  kvm.ignore_msrs=1 
  kvm-intel.ept=1 
  vga=791 
  net.ifnames=0 
  mpt3sas.prot_mask=1 
  IMG=squashfs 
  console=tty0 
  console=ttyS0,115200 
  FOUND_IP=${next-server} 
  AZ_CONF_URL=http://${next-server}:8080/configs/${net0/mac}.json

initrd http://${next-server}:8080/images/initrd-modified.img
boot
```

## Key Learnings

### What Worked
1. **Systematic exploration** - Starting from ISO structure, then squashfs, then initrd
2. **Following the boot chain** - Understanding init → ce_installer flow
3. **Code analysis** - Reading Python/shell scripts to understand parameter handling
4. **Pattern recognition** - Identifying Phoenix framework patterns in CE

### Critical Discoveries
1. CE uses `/ce_installer` not `/installer`
2. CE supports `FOUND_IP` and `AZ_CONF_URL` automation parameters
3. JSON configuration uses flat structure, not nested Phoenix format
4. DNS servers use comma-separated format
5. `COMMUNITY_EDITION=1` environment variable is set

### Differences from Commercial Phoenix
- Simpler JSON structure (flat vs nested)
- Different installer entry point (`ce_installer` vs `installer`)
- Limited automation features but core parameters still work

## Tools Used
- Standard Linux tools: mount, grep, find, cat, file
- cpio for initrd extraction
- Python/shell script analysis

## Conclusion
Through systematic analysis of the ISO structure, boot configuration, and installer scripts, we successfully identified:
1. The correct boot parameters for iPXE
2. The expected JSON configuration format
3. The automation capabilities of the CE installer

This enables fully automated Nutanix CE deployment via iPXE without console interaction.
```