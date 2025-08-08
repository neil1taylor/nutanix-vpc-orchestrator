# Nutanix CE iPXE Automated Installation Guide

This guide covers the complete process for automated Nutanix Community Edition installation on IBM Cloud VPC Bare Metal servers using iPXE and HTTP boot.

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

## Architecture

```
IBM Bare Metal Server (iPXE) → HTTP Server → Automated Installation
                ↓
1. Boot kernel + initrd via HTTP
2. Download squashfs.img (root filesystem)  
3. Download arizona.cfg (automation config)
4. Download AOS installer + AHV ISO
5. Automated installation based on config
```

## Step 1: Extract Files from Nutanix CE ISO

### 1.1 Mount the ISO
```bash
sudo mkdir /mnt/nutanix
sudo mount -o loop nutanix-ce-installer.iso /mnt/nutanix
```

### 1.2 Extract Boot Files
```bash
# Create web server directory structure
sudo mkdir -p /var/www/html/boot

# Extract kernel and initrd
sudo cp /mnt/nutanix/boot/kernel /var/www/html/boot/
sudo cp /mnt/nutanix/boot/initrd /var/www/html/boot/

# Extract squashfs root filesystem
sudo cp /mnt/nutanix/squashfs.img /var/www/html/
```

### 1.3 Extract AOS Installer Package
```bash
# Copy split installer parts
sudo cp /mnt/nutanix/images/svm/nutanix_installer_package.tar.p* /var/www/html/

# Reconstruct complete installer
cd /var/www/html
sudo cat nutanix_installer_package.tar.p* > nutanix_installer_package.tar.gz
sudo rm nutanix_installer_package.tar.p*
```

### 1.4 Extract AHV Hypervisor ISO
```bash
# Copy AHV ISO
sudo cp "/mnt/nutanix/images/hypervisor/kvm/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso" /var/www/html/
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
gunzip -c /var/www/html/boot/initrd | cpio -idmv
```

### 2.2 Modify livecd.sh
Edit `/tmp/nutanix-initrd/livecd.sh` and replace the `find_squashfs_in_iso_ce()` function:

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
find . | cpio -o -H newc | gzip > /var/www/html/boot/initrd-modified
```

## Step 3: Create Arizona Configuration

Create `/var/www/html/arizona.cfg` with your automation parameters:

### 3.1 Single Node Configuration
```json
{
  "hyp_type": "kvm",
  "node_position": "A",
  "svm_installer_url": {
    "url": "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/nutanix_installer_package.tar.gz",
    "md5sum": "your_actual_md5_checksum_here"
  },
  "hypervisor_iso_url": {
    "url": "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso",
    "md5sum": "ahv_iso_md5_checksum_here"
  },
  "nodes": [
    {
      "node_position": "A",
      "hyp_ip": "10.240.0.100",
      "hyp_netmask": "255.255.255.0",
      "hyp_gateway": "10.240.0.1",
      "svm_ip": "10.240.0.101",
      "svm_netmask": "255.255.255.0",
      "svm_gateway": "10.240.0.1"
    }
  ],
  "dns_servers": "8.8.8.8,8.8.4.4",
  "ntp_servers": "pool.ntp.org",
  "skip_hypervisor": false,
  "install_cvm": true
}
```

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

Create `/var/www/html/nutanix-ce-autoinstall.ipxe`:

```bash
#!ipxe

# Set timeouts for large file downloads
set net-timeout 300000
set http-timeout 300000

# Boot Nutanix CE with automated installation
kernel http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/kernel init=/ce_installer intel_iommu=on iommu=pt kvm-intel.nested=1 kvm.ignore_msrs=1 kvm-intel.ept=1 vga=791 net.ifnames=0 mpt3sas.prot_mask=1 IMG=squashfs LIVEFS_URL=http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/squashfs.img AZ_CONF_URL=http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/arizona.cfg PHOENIX_IP=10.240.0.100 MASK=255.255.255.0 GATEWAY=10.240.0.1 PXEBOOT=true
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

## Step 5: Configure HTTP Server

Ensure your HTTP server is configured and running:

```bash
# Install web server if needed
sudo apt install nginx  # Ubuntu/Debian
# or
sudo yum install httpd  # RHEL/CentOS

# Start and enable service
sudo systemctl start nginx
sudo systemctl enable nginx

# Verify files are accessible
curl -I http://your-server-ip/squashfs.img
curl -I http://your-server-ip/arizona.cfg
```

### 5.1 Required File Structure
```
/var/www/html/
├── boot/
│   ├── kernel
│   └── initrd-modified
├── squashfs.img
├── nutanix_installer_package.tar.gz
├── AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso
├── arizona.cfg
└── nutanix-ce-autoinstall.ipxe
```

## Step 6: Boot Target Server

### 6.1 iPXE Boot Methods

**Option A: Direct iPXE commands**
```bash
# At iPXE prompt
chain http://your-server-ip/nutanix-ce-autoinstall.ipxe
```

**Option B: Direct sanboot (without modification)**
```bash
# At iPXE prompt (requires larger timeouts)
set net-timeout 300000
set http-timeout 300000
sanboot http://your-server-ip/nutanix-ce-installer.iso
```

### 6.2 Installation Process

1. **Network Boot**: Server boots via iPXE
2. **Kernel Load**: Downloads and boots Nutanix kernel
3. **Root FS**: Downloads squashfs.img as root filesystem
4. **Configuration**: Downloads arizona.cfg for automation
5. **Package Download**: Downloads AOS installer and AHV ISO
6. **Installation**: Automated installation based on configuration
7. **Completion**: Server reboots into installed Nutanix CE

## Step 7: Multi-Node Deployment

### 7.1 Node Position Strategy
- **Node A**: First node, cluster leader
- **Node B**: Second node
- **Node C**: Third node, etc.

### 7.2 Multi-Node Arizona Configuration
```json
{
  "hyp_type": "kvm",
  "node_position": "%%NODE_POSITION%%",
  "cluster_name": "nutanix-ce-cluster",
  "cluster_external_ip": "10.240.0.200",
  "nodes": [
    {
      "node_position": "A",
      "hyp_ip": "10.240.0.100",
      "svm_ip": "10.240.0.101"
    },
    {
      "node_position": "B", 
      "hyp_ip": "10.240.0.110",
      "svm_ip": "10.240.0.111"
    },
    {
      "node_position": "C",
      "hyp_ip": "10.240.0.120",
      "svm_ip": "10.240.0.121"
    }
  ]
}
```

### 7.3 Per-Node iPXE Scripts
Create separate iPXE scripts for each node:

**nutanix-nodeA.ipxe:**
```bash
kernel ... AZ_CONF_URL=http://server/arizona.cfg NODE_POSITION=A
```

**nutanix-nodeB.ipxe:**
```bash
kernel ... AZ_CONF_URL=http://server/arizona.cfg NODE_POSITION=B
```

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

## Security Considerations

1. **HTTP vs HTTPS**: Consider using HTTPS for sensitive environments
2. **Network isolation**: Ensure HTTP server is on trusted network
3. **Credential management**: Avoid hardcoding passwords in arizona.cfg
4. **SSH keys**: Use SSH key authentication instead of passwords

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