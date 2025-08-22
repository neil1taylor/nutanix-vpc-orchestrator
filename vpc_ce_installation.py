#!/usr/bin/env python3

"""
Nutanix CE VPC Installation Script - Optimized Production Version

NOTE: This script is designed to use only Python standard library modules
to ensure compatibility with minimal Python environments. Do not add any
external dependencies (like requests, psutil, etc.) that require pip install.
Use urllib instead of requests, and built-in modules whenever possible.

This ensures the script can run in embedded/chroot environments where
only the Python standard library is available.
"""

import sys
import os
import time
import subprocess
import json
import socket
import hashlib
import uuid
import glob
from random import randint
import urllib.request
import urllib.error
import re

# Global variables to store management_ip and config_server
management_ip = None
config_server = None

def drop_to_shell(error_msg):
    """
    Drop to an interactive shell for debugging when a critical error occurs.
    
    Args:
        error_msg: The error message to log before dropping to shell
    """
    log(f"ERROR: {error_msg}")
    
    # Send status update if we have the required information
    if management_ip and config_server:
        log(f"ERROR: {error_msg} - Dropping to shell", phase="error")
    
    log("Dropping to interactive shell for debugging...")
    log("You can now connect via serial console")
    
    # Print a visible separator to make it clear we're entering a shell
    print("\n" + "="*60)
    print(">>> ENTERING INTERACTIVE DEBUG SHELL <<<")
    print("="*60 + "\n")
    
    # Execute an interactive shell
    try:
        # Try to use a more feature-rich shell if available
        for shell_path in ['/bin/bash', '/bin/sh']:
            if os.path.exists(shell_path):
                os.execv(shell_path, [shell_path])
        
        # Fallback to Python's subprocess if exec fails
        subprocess.call(['/bin/sh'])
    except Exception as e:
        log(f"Failed to start debug shell: {e}")
        # If we can't start a shell, at least sleep to keep the process alive
        # so logs can be examined
        while True:
            time.sleep(3600)

def log(message, phase=-1, send_to_api=True):
    """
    Log a message to stdout and optionally send to the status API.
    
    Args:
        message: The message to log
        phase: The installation phase number (default: -1 for general logs)
        send_to_api: Whether to also send the message to the API (default: True)
    """
    global management_ip, config_server
    
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    
    # Send log message to API if requested
    if send_to_api and management_ip and config_server:
        send_status_update(management_ip, phase, message)

def get_management_ip():
    """Get IP address of first interface as management IP"""
    
    try:
        # Get first non-loopback interface
        interfaces = [iface for iface in os.listdir('/sys/class/net/') if iface != 'lo']
        if interfaces:
            first_interface = interfaces[0]
            
            # Get IP address using ip command
            result = subprocess.run([
                'ip', 'addr', 'show', first_interface
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                # Parse IP address from output
                for line in result.stdout.split('\n'):
                    if 'inet ' in line and 'scope global' in line:
                        ip = line.strip().split()[1].split('/')[0]
                        log(f"Node identifier (IP): {ip}")
                        return ip
                        
    except Exception as e:
        log(f"Could not get IP address: {e}")

def get_config_server_from_cmdline():
    """
    Extract config server from kernel command line and clean up the URL
    
    Returns:
        A cleaned URL string with proper formatting, or None if not found
    """
    try:
        with open('/proc/cmdline', 'r') as f:
            cmdline = f.read().strip()
        
        # Look for config_server= parameter
        for param in cmdline.split():
            if param.startswith('config_server='):
                server = param.split('=', 1)[1]
                
                # Special handling for URLs with space between hostname and port
                if ': ' in server:
                    server = server.replace(': ', ':')
                
                # Clean up the URL - remove any remaining spaces
                if ' ' in server:
                    server = server.replace(' ', '')
                
                # Ensure URL has proper format
                if not server.startswith('http://') and not server.startswith('https://'):
                    server = 'http://' + server
                
                log(f"Config server from cmdline: {server}")
                return server
    except Exception as e:
        log(f"Error reading cmdline: {e}")

def download_node_config(config_server, management_ip):
    """Download node-specific configuration"""
    log(f"Downloading configuration for node: {management_ip}")
    
    if not config_server:
        log("Error: Config server URL is empty or invalid")
        return None
    
    url = f"{config_server}/boot/server/{management_ip}"
    
    try:
        log(f"Downloading config from: {url}")
        
        result = subprocess.run([
            'curl', '-s', '--connect-timeout', '10',
            '--max-time', '30', url
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.returncode == 0:
            if result.stdout.strip():
                try:
                    config = json.loads(result.stdout)
                    log(f"Configuration downloaded successfully")
                    return config
                except json.JSONDecodeError as e:
                    log(f"Invalid JSON from {url}: {e}")
            else:
                log("Empty response from server")
        else:
            log(f"Failed to download from {url}")
            
    except Exception as e:
        log(f"Error downloading from {url}: {e}")
    
    log("Could not download any configuration")
    return None

def validate_config(config):
    """Validate configuration completeness"""
    log("Validating configuration...")
    
    required_sections = ['hardware', 'resources', 'network']
    
    for section in required_sections:
        if section not in config:
            log(f"Missing required config section: {section}")
            return False
    
    # Validate critical fields
    critical_fields = [
        ('hardware', 'boot_disk'),
        ('hardware', 'cvm_data_disks'),
        ('resources', 'cvm_memory_gb'),
        ('network', 'cvm_ip'),
        ('network', 'cvm_netmask'),
        ('network', 'cvm_gateway'),
        ('network', 'dns_servers')
    ]
    
    for section, field in critical_fields:
        if field not in config[section]:
            log(f"Missing required field: {section}.{field}")
            return False
    
    log("Configuration validation passed")
    return True

def test_connectivity():
    """Test network connectivity"""
    try:
        # Try to connect to Google DNS
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex(('8.8.8.8', 53))
        sock.close()
        return result == 0
    except:
        return False

def download_packages(config_server):
   """Download required installation packages"""
   log("Downloading installation packages...")
   
   if not config_server:
       log("Error: Config server URL is empty or invalid")
       return False
   
   # Ensure we have network connectivity
   if not test_connectivity():
       log("No network connectivity for package download")
       return False
   
   # Define required packages
   package_downloads = [
       (f"{config_server}/boot/images/nutanix_installer_package.tar.gz",
        '/tmp/nutanix_installer_package.tar.gz'),
       (f"{config_server}/boot/images/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso",
        '/tmp/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso')
   ]
   
   for url, local_path in package_downloads:
       log(f"Downloading {os.path.basename(local_path)}...")
       
       # Create directory if needed
       os.makedirs(os.path.dirname(local_path), exist_ok=True)
       
       # Use curl for download
       curl_cmd = f"curl -L --progress-bar --connect-timeout 30 --max-time 1200 --retry 5 -o {local_path} {url}"
       exit_code = os.system(curl_cmd)
       
       # Check if file exists and has reasonable size
       if exit_code == 0 and os.path.exists(local_path):
           file_size = os.path.getsize(local_path)
           
           if file_size > 1024 * 1024:  # At least 1MB
               log(f"Successfully downloaded {os.path.basename(local_path)} ({file_size:,} bytes)")
           else:
               log(f"Downloaded file too small: {os.path.basename(local_path)} - only {file_size:,} bytes")
               return False
       else:
           log(f"Failed to download {os.path.basename(local_path)}")
           return False
   
   return True

def install_hypervisor(config):
   """Install AHV hypervisor to boot disk with optimized production configuration"""

   log("Wiping all drives...")
   wipe_nvmes()

   log("Installing AHV hypervisor...")
   
   boot_disk = config['hardware']['boot_disk']
   log(f"Using boot disk: {boot_disk}")
   boot_device = f"/dev/{boot_disk}"
   
   try:
       # Create hypervisor partitions
       log("Creating hypervisor partitions...")
       # Create partitions:
       # 1. EFI partition (200MB)
       # 2. Hypervisor partition (32GB)
       # 3. Data partition (rest of disk)
       fdisk_commands = "n\np\n1\n\n+200M\nn\np\n2\n\n+32G\nn\np\n3\n\n\nt\n1\nef\na\n1\nw\n"
       
       result = subprocess.run(['fdisk', boot_device],
                             input=fdisk_commands, text=True,
                             capture_output=True)
       
       if result.returncode != 0:
           log(f"Failed to create partitions: {result.stderr}")
           drop_to_shell(f"Failed to create partitions on {boot_device}")
       
       # Wait for partitions to be recognized
       time.sleep(3)
       subprocess.run(['partprobe', boot_device])
       time.sleep(2)
       
       # Format partitions
       log("Formatting partitions...")
       
       # EFI partition
       result = subprocess.run(['mkfs.vfat', f'{boot_device}p1'], capture_output=True)
       if result.returncode != 0:
           log(f"Failed to format EFI partition: {result.stderr}")
           drop_to_shell(f"Failed to format EFI partition on {boot_device}p1")
       
       # Hypervisor partition with ROOT label
       result = subprocess.run(['mkfs.ext4', '-F', '-L', 'ROOT', f'{boot_device}p2'], capture_output=True)
       if result.returncode != 0:
           log(f"Failed to format hypervisor partition: {result.stderr}")
           drop_to_shell(f"Failed to format hypervisor partition on {boot_device}p2")
       
       log("Partitions created and formatted")
       
       # Mount and install AHV hypervisor
       log("Mounting and installing AHV hypervisor...")
       
       # Create mount points
       os.makedirs('/mnt/stage', exist_ok=True)
       os.makedirs('/mnt/ahv', exist_ok=True)
       os.makedirs('/mnt/install', exist_ok=True)
       
       # Mount hypervisor partition
       result = subprocess.run(['mount', f'{boot_device}p2', '/mnt/stage'])
       if result.returncode != 0:
           log("Failed to mount hypervisor partition")
           drop_to_shell(f"Failed to mount hypervisor partition {boot_device}p2 to /mnt/stage")
       
       # Mount AHV ISO
       ahv_iso_path = '/tmp/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso'
       result = subprocess.run(['mount', '-o', 'loop', ahv_iso_path, '/mnt/ahv'])
       if result.returncode != 0:
           log("Failed to mount AHV ISO")
           cleanup_mounts()
           return False
       
       # Mount and extract AHV filesystem
       result = subprocess.run(['mount', '-o', 'loop', '/mnt/ahv/images/install.img', '/mnt/install'])
       if result.returncode != 0:
           log("Failed to mount AHV install image")
           cleanup_mounts()
           return False
       
       # Copy AHV filesystem to hypervisor partition
       log("Copying AHV filesystem...")
       result = subprocess.run(['cp', '-a', '/mnt/install/.', '/mnt/stage/'])
       if result.returncode != 0:
           log("Failed to copy AHV filesystem")
           cleanup_mounts()
           return False
       
       # Set up EFI boot
       log("Setting up EFI boot...")
       os.makedirs('/mnt/stage/boot/efi', exist_ok=True)
       
       # Format and mount EFI partition
       log("Setting up EFI partition...")
       result = subprocess.run(['mkfs.vfat', '-F', '32', f'{boot_device}p1'], capture_output=True)
       if result.returncode != 0:
           log(f"Warning: Could not format EFI partition: {result.stderr}")
       
       result = subprocess.run(['mount', f'{boot_device}p1', '/mnt/stage/boot/efi/'])
       if result.returncode != 0:
           log(f"Failed to mount EFI partition: {result.stderr}")
           cleanup_mounts()
           return False
       
       log("EFI partition mounted successfully")
       
       # Create EFI directories
       log("Creating EFI directory structure...")
       efi_dirs = [
           '/mnt/stage/boot/efi/EFI/BOOT',
           '/mnt/stage/boot/efi/EFI/NUTANIX'
       ]
       
       for efi_dir in efi_dirs:
           os.makedirs(efi_dir, exist_ok=True)
       
       # Find and copy GRUB EFI binary
       log("Setting up GRUB EFI boot...")
       
       # Search for GRUB EFI binaries
       grub_efi_paths = []
       search_locations = ['/mnt/ahv', '/mnt/stage', '/mnt/install']
       search_patterns = ['grubx64.efi', 'BOOTX64.EFI', 'shimx64.efi']
       
       for location in search_locations:
           for pattern in search_patterns:
               result = subprocess.run(['find', location, '-name', pattern, '-type', 'f'],
                                     capture_output=True, text=True)
               if result.stdout.strip():
                   grub_efi_paths.extend(result.stdout.strip().split('\n'))
       
       if grub_efi_paths:
           grub_efi_path = grub_efi_paths[0]
           log(f"Using GRUB EFI binary at {grub_efi_path}")
           
           # Copy to standard locations
           subprocess.run(['cp', grub_efi_path, '/mnt/stage/boot/efi/EFI/BOOT/BOOTX64.EFI'])
           subprocess.run(['cp', grub_efi_path, '/mnt/stage/boot/efi/EFI/NUTANIX/grubx64.efi'])
           log("Copied GRUB EFI binary to standard locations")
       
       # Create optimized GRUB configuration for production
       log("Creating optimized GRUB configuration...")
       
       kernel_version = "5.10.194-5.20230302.0.991650.el8.x86_64"
       
       # Production kernel parameters optimized for IBM Cloud VPC
       production_params = f"root=LABEL=ROOT ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal"
       
       # GRUB2 configuration for EFI
       efi_grub_config = f"""# GRUB configuration for Nutanix AHV - Production
insmod part_gpt
insmod ext2
insmod search_label
insmod fat
insmod normal
insmod linux
insmod gzio

set default=0
set timeout=5
set timeout_style=menu
set gfxpayload=keep

# Use root partition
search --no-floppy --set=root --label=ROOT

# Primary boot entry
menuentry 'Nutanix AHV' --unrestricted --id nutanix {{
 echo 'Loading Linux kernel...'
 linux /vmlinuz {production_params}
 echo 'Loading initial ramdisk...'
 initrd /initrd
}}

# Fallback entry with full paths
menuentry 'Nutanix AHV (Fallback)' --unrestricted --id nutanix_fallback {{
 echo 'Loading Linux kernel (fallback)...'
 linux /boot/vmlinuz-{kernel_version} root=/dev/{boot_disk}p2 {production_params}
 echo 'Loading initial ramdisk (fallback)...'
 initrd /boot/initramfs-{kernel_version}.img
}}
"""
       
       # Create GRUB configuration files
       efi_grub_locations = [
           '/mnt/stage/boot/efi/EFI/BOOT/grub.cfg',
           '/mnt/stage/boot/efi/EFI/NUTANIX/grub.cfg'
       ]
       
       for grub_path in efi_grub_locations:
           with open(grub_path, 'w') as f:
               f.write(efi_grub_config)
           log(f"Created GRUB configuration at {grub_path}")
       
       # Main GRUB2 configuration
       os.makedirs('/mnt/stage/boot/grub2', exist_ok=True)
       
       grub2_config = f"""# GRUB configuration for Nutanix AHV - Production
insmod part_gpt
insmod ext2
insmod search_label
insmod fat
insmod normal
insmod linux
insmod gzio

set default=0
set timeout=5
set timeout_style=menu
set gfxpayload=keep

# Use root partition by label
search --no-floppy --set=root --label=ROOT

# Primary boot entry
menuentry 'Nutanix AHV' --unrestricted --id nutanix {{
  echo 'Loading Linux kernel...'
  linux /boot/vmlinuz-{kernel_version} {production_params}
  echo 'Loading initial ramdisk...'
  initrd /boot/initramfs-{kernel_version}.img
}}

# Fallback entry with symlinks
menuentry 'Nutanix AHV (Fallback)' --unrestricted --id nutanix_fallback {{
  echo 'Loading Linux kernel (fallback)...'
  linux /vmlinuz {production_params}
  echo 'Loading initial ramdisk (fallback)...'
  initrd /initrd
}}
"""
       
       with open('/mnt/stage/boot/grub2/grub.cfg', 'w') as f:
           f.write(grub2_config)
       
       # Create GRUB defaults file
       with open('/mnt/stage/etc/default/grub', 'w') as f:
           f.write(f"""GRUB_TIMEOUT=5
GRUB_TIMEOUT_STYLE=menu
GRUB_DISTRIBUTOR="Nutanix AHV"
GRUB_DEFAULT=0
GRUB_DISABLE_RECOVERY=false
GRUB_TERMINAL="console serial"
GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"
GRUB_CMDLINE_LINUX="{production_params}"
GRUB_PRELOAD_MODULES="part_gpt ext2 search_label fat normal linux gzio"
""")
       log("Created GRUB configuration files")
       
       # Generate initramfs with required modules
       log("Setting up initramfs...")
       
       # Create dracut configuration for required drivers
       os.makedirs('/mnt/stage/etc/dracut.conf.d', exist_ok=True)
       with open('/mnt/stage/etc/dracut.conf.d/vpc_drivers.conf', 'w') as f:
           f.write("""# Include NVMe and network modules in initramfs
add_drivers+=" nvme nvme-core "
hostonly="no"
hostonly_cmdline="no"
early_microcode="yes"
""")
       
       # Detect kernel version
       log("Detecting kernel version...")
       result = subprocess.run(['chroot', '/mnt/stage', 'ls', '-1', '/lib/modules'],
                             capture_output=True, text=True)
       
       if result.returncode == 0 and result.stdout.strip():
           kernel_version = result.stdout.strip().split('\n')[0]
           log(f"Detected kernel version: {kernel_version}")
       
       # Copy dracut from host to chroot environment if it's missing
       log("Ensuring dracut is available in chroot environment...")
       if not os.path.exists('/mnt/stage/usr/bin/dracut'):
           # Try to copy dracut from host system
           subprocess.run(['cp', '-f', '/usr/bin/dracut', '/mnt/stage/usr/bin/'],
                         capture_output=True, text=True)
           # Copy dracut libraries and dependencies
           subprocess.run(['cp', '-rf', '/usr/lib/dracut', '/mnt/stage/usr/lib/'],
                         capture_output=True, text=True)
           log("Copied dracut from host to chroot environment")
       
       # Create required directories for dracut
       log("Creating required directories for dracut...")
       os.makedirs('/mnt/stage/var/tmp', exist_ok=True)
       os.makedirs('/mnt/stage/tmp', exist_ok=True)
       os.makedirs('/mnt/stage/var/lib/initramfs', exist_ok=True)
       # Set proper permissions
       subprocess.run(['chmod', '1777', '/mnt/stage/var/tmp'], check=False)
       subprocess.run(['chmod', '1777', '/mnt/stage/tmp'], check=False)
       
       # Generate initramfs
       log(f"Generating initramfs for kernel version {kernel_version}")
       result = subprocess.run(['chroot', '/mnt/stage', 'dracut', '--force',
                               f'/boot/initramfs-{kernel_version}.img',
                               kernel_version],
                               capture_output=True, text=True)
       
       if result.returncode != 0:
           log(f"Failed to generate initramfs: {result.stderr}")
           # Try to copy existing initramfs from ISO
           log("Attempting to copy initramfs from ISO...")
           result = subprocess.run(['find', '/mnt/ahv', '-name', 'initramfs*'],
                                 capture_output=True, text=True)
           if result.stdout.strip():
               initramfs_path = result.stdout.strip().split('\n')[0]
               subprocess.run(['cp', initramfs_path, f'/mnt/stage/boot/initramfs-{kernel_version}.img'])
               log(f"Copied initramfs from ISO: {initramfs_path}")
       else:
           log("Successfully generated initramfs")
       
       # Install GRUB bootloader
       log("Installing GRUB bootloader...")
       
       # Create necessary directories
       os.makedirs('/mnt/stage/boot/efi/EFI/BOOT', exist_ok=True)
       os.makedirs('/mnt/stage/boot/efi/EFI/NUTANIX', exist_ok=True)
       
       # Install GRUB packages with all dependencies
       log("Installing GRUB packages with all dependencies...")
       subprocess.run(['chroot', '/mnt/stage', 'yum', 'install', '-y',
                      'grub2-efi-x64', 'grub2-tools', 'grub2-efi-x64-modules',
                      'efibootmgr', 'shim-x64'],
                     capture_output=True, text=True)
       
       # Copy kernel and initramfs to required locations
       log("Setting up kernel and initramfs files...")
       
       # Find kernel and initramfs files
       kernel_files = []
       initramfs_files = []
       
       result = subprocess.run(['find', '/mnt/stage', '-name', 'vmlinuz*'],
                             capture_output=True, text=True)
       if result.stdout.strip():
           kernel_files = result.stdout.strip().split('\n')
       
       result = subprocess.run(['find', '/mnt/stage', '-name', 'initramfs*'],
                             capture_output=True, text=True)
       if result.stdout.strip():
           initramfs_files = result.stdout.strip().split('\n')
       
       # Copy to standard locations
       if kernel_files:
           kernel_source = kernel_files[0]
           subprocess.run(['cp', kernel_source, '/mnt/stage/vmlinuz'])
           subprocess.run(['cp', kernel_source, '/mnt/stage/boot/vmlinuz'])
           log("Kernel files copied to standard locations")
       
       if initramfs_files:
           initramfs_source = initramfs_files[0]
           subprocess.run(['cp', initramfs_source, '/mnt/stage/initrd'])
           subprocess.run(['cp', initramfs_source, '/mnt/stage/boot/initrd'])
           log("Initramfs files copied to standard locations")
       
       # Create symlinks
       log("Creating symlinks...")
       symlink_pairs = [
           ('/boot/vmlinuz', f'/boot/vmlinuz-{kernel_version}'),
           ('/boot/initrd', f'/boot/initramfs-{kernel_version}.img'),
           ('/vmlinuz', f'/boot/vmlinuz-{kernel_version}'),
           ('/initrd', f'/boot/initramfs-{kernel_version}.img')
       ]
       
       for link, target in symlink_pairs:
           try:
               subprocess.run(['chroot', '/mnt/stage', 'ln', '-sf', target, link],
                             capture_output=True, check=True)
           except subprocess.CalledProcessError:
               pass  # Continue if symlink creation fails
       
       # Copy GRUB modules from host if they exist
       log("Checking for GRUB modules on host system...")
       host_grub_dir = '/usr/lib/grub/x86_64-efi'
       target_grub_dir = '/mnt/stage/usr/lib/grub/x86_64-efi'
       
       if os.path.exists(host_grub_dir):
           log(f"Copying GRUB modules from host {host_grub_dir} to chroot...")
           os.makedirs(target_grub_dir, exist_ok=True)
           subprocess.run(['cp', '-rf', f'{host_grub_dir}/*', target_grub_dir],
                         shell=True, capture_output=True)
       
       # Install GRUB with explicit target and directory
       log("Installing GRUB with explicit target and directory...")
       result = subprocess.run(['chroot', '/mnt/stage', 'grub2-install',
                               '--target=x86_64-efi',
                               '--efi-directory=/boot/efi',
                               '--bootloader-id=NUTANIX',
                               '--boot-directory=/boot',
                               f'{boot_device}'],
                               capture_output=True, text=True)
       
       if result.returncode == 0:
           log("GRUB installation successful")
       else:
           log(f"GRUB installation failed: {result.stderr}")
       
       # Create EFI boot entries
       log("Creating EFI boot entries...")
       try:
           subprocess.run(['chroot', '/mnt/stage', 'efibootmgr', '--create',
                          '--disk', f'{boot_device}', '--part', '1',
                          '--label', 'Nutanix AHV', '--loader', '/EFI/NUTANIX/grubx64.efi'],
                          capture_output=True, text=True)
           log("EFI boot entry created")
       except:
           log("EFI boot entry creation failed - will rely on fallback boot")
       
       # Cleanup
       cleanup_mounts()
       
       log("AHV hypervisor installation completed")
       return True
       
   except Exception as e:
       log(f"Hypervisor installation error: {e}")
       cleanup_mounts()
       return False

def cleanup_mounts():
   """Clean up all mount points"""
   mount_points = [
       '/mnt/stage/boot/efi',
       '/mnt/stage', 
       '/mnt/install',
       '/mnt/ahv'
   ]
   
   for mount_point in mount_points:
       try:
           subprocess.run(['umount', mount_point], capture_output=True)
       except:
           pass

def setup_environment(config):
    """Set up installation environment"""
    log("Setting up installation environment...")
    
    # Set environment variables
    os.environ['COMMUNITY_EDITION'] = 'true'
    os.environ['AUTOMATED_INSTALL'] = 'true'
    
    # Set up Python path
    sys.path.insert(0, '/phoenix')
    sys.path.insert(0, '/usr/lib/python3.9')
    
    log("Environment setup complete")

def generate_cluster_id():
    """Generate cluster ID from MAC addresses"""
    log("Generating cluster_id")
    randomizer_hex = hex(randint(1, int('7FFF', 16)))[2:]
    mac_addrs = []
    pcibase = "/sys/devices/pci"
    for net in glob.glob("/sys/class/net/*"):
      if not os.path.realpath(net).startswith(pcibase):
        continue
      try:
          with open("%s/address" % net, 'r') as f:
              mac_addrs.append(f.read().strip())
      except IOError:
          log(f"Could not read MAC address for {net}")
    mac_addrs.sort()
    if mac_addrs:
        cluster_id = int(randomizer_hex + mac_addrs[0].replace(':', ''), 16)
    else:
        cluster_id = int(randomizer_hex + "000000000000", 16)
    return cluster_id

def create_installation_params(config):
    """Create Nutanix installation parameters from config"""
    log("Creating installation parameters from configuration...")
    
    try:
        import param_list
        
        params = param_list.ParamList()
        
        # Node configuration
        if 'node' not in config:
            config['node'] = {}
            
        node_config = config['node']
        params.block_id = node_config.get('block_id', str(uuid.uuid4()).split('-')[0])
        params.node_position = node_config.get('node_position', "A")
        params.node_serial = node_config.get('node_serial', str(uuid.uuid4()))
        params.cluster_id = node_config.get('cluster_id', generate_cluster_id())
        
        # Hardware configuration
        hw_config = config['hardware']
        params.model = hw_config['model']
        params.model_string = hw_config['model']
        params.boot_disk = hw_config['boot_disk']
        params.boot_disk_model = hw_config.get('boot_disk_model', 'Generic')
        params.boot_disk_sz_GB = hw_config['boot_disk_size_gb']
        params.hw_layout = None
        
        # Installation type
        params.hyp_type = 'kvm'
        params.hyp_install_type = 'clean'
        params.svm_install_type = 'clean'
        params.installer_path = '/tmp/nutanix_installer_package.tar.gz'
        
        # Resource configuration
        resources = config['resources']
        params.svm_gb_ram = resources['cvm_memory_gb']
        params.svm_num_vcpus = resources['cvm_vcpus']
        
        # Disk layout
        if isinstance(hw_config['cvm_data_disks'], str):
            params.ce_cvm_data_disks = [hw_config['cvm_data_disks']]
        else:
            params.ce_cvm_data_disks = hw_config['cvm_data_disks']
            
        if isinstance(hw_config['cvm_boot_disks'], str):
            params.ce_cvm_boot_disks = [hw_config['cvm_boot_disks']]
        else:
            params.ce_cvm_boot_disks = hw_config['cvm_boot_disks']
            
        params.ce_hyp_boot_disk = hw_config['hypervisor_boot_disk']
        
        if isinstance(hw_config['cvm_data_disks'], str):
            params.ce_disks = [hw_config['boot_disk']] + [hw_config['cvm_data_disks']]
        else:
            params.ce_disks = [hw_config['boot_disk']] + hw_config['cvm_data_disks']
        
        # Community Edition settings
        params.ce_eula_accepted = True
        params.ce_eula_viewed = True
        params.create_1node_cluster = False
        
        # Version information
        params.nos_version = '6.8.0'
        params.svm_version = '6.8.0'
        params.hyp_version = 'el8.nutanix.20230302.101026'
        params.phoenix_version = '4.6'
        params.foundation_version = '4.6'

        # Configure CVM network interface
        network_config = config['network']
        params.cvm_interfaces = [
            {
                "name": "eth0",
                "ip": network_config['cvm_ip'],
                "netmask": network_config['cvm_netmask'], 
                "gateway": network_config['cvm_gateway'],
                "vswitch": "br0"
            }
        ]

        # Set DNS servers
        params.dns_ip = ",".join(network_config['dns_servers'])
        
        log("Installation parameters created")
        return params
        
    except Exception as e:
        log(f"Error creating installation parameters: {e}")
        return None

def cleanup_previous_attempts():
    """Clean up any previous installation attempts"""
    log("Cleaning up previous installation attempts...")
    
    cleanup_paths = [
        '/tmp/svm_install_chroot',
        '/tmp/svm_marker'
    ]
    
    try:
        for path in cleanup_paths:
            if os.path.isdir(path):
                subprocess.run(['rm', '-rf', path], check=True)
                log(f"Removed directory: {path}")
            elif os.path.isfile(path):
                os.remove(path)
                log(f"Removed file: {path}")
        
        log("Cleanup completed")
        return True
        
    except Exception as e:
        log(f"Cleanup failed: {e}")
        return False

def send_status_update(management_ip, phase, message):
    """
    Sends status and log messages to the PXE config server API using urllib.
    
    Args:
        management_ip: The IP address of the management interface
        phase: The installation phase number or "error" for error messages
        message: The status message to send
    """
    global config_server
    if not config_server:
        return
    
    api_url = f"{config_server}/api/installation/status"
    payload = {
        "management_ip": management_ip,
        "phase": phase,
        "message": message
    }
    
    # Convert payload to JSON and encode
    data = json.dumps(payload).encode('utf-8')
    
    try:
        req = urllib.request.Request(api_url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        
        response = urllib.request.urlopen(req, timeout=10)
        status_code = response.getcode()
        
        if not (200 <= status_code < 300):
            log(f"Status update failed with HTTP {status_code}", send_to_api=False)
            
    except Exception as e:
        # Silently fail status updates to avoid disrupting installation
        pass

def wipe_nvmes():
    """Wipe all NVMe drives"""
    drives = [d for d in glob.glob('/dev/nvme*') if re.match(r'.*/nvme\d+n\d+', d)]
    for drive in sorted(drives):
        log(f"Wiping {drive}")
        subprocess.run(['wipefs', '-a', drive], check=True)
    log(f"Wiped {len(drives)} drives")

def verify_installation(config):
    """
    Verify that the installation has completed successfully
    
    Args:
        config: The node configuration dictionary
        
    Returns:
        True if verification passes, False otherwise
    """
    log("Verifying installation...")
    
    boot_disk = config['hardware']['boot_disk']
    boot_device = f"/dev/{boot_disk}"
    
    # Check if the hypervisor partition is mounted
    if not os.path.ismount('/mnt/stage'):
        log("Mounting hypervisor partition for verification...")
        result = subprocess.run(['mount', f'{boot_device}p2', '/mnt/stage'])
        if result.returncode != 0:
            log("Failed to mount hypervisor partition for verification")
            return False
    
    # Define essential files that must exist
    essential_files = [
        '/mnt/stage/boot/vmlinuz',
        '/mnt/stage/boot/initrd', 
        '/mnt/stage/boot/grub2/grub.cfg',
        '/mnt/stage/boot/efi/EFI/BOOT/BOOTX64.EFI'
    ]
    
    # Check for existence of essential files
    missing_files = []
    for file_path in essential_files:
        if not os.path.exists(file_path) and not glob.glob(file_path + '*'):
            missing_files.append(file_path)
    
    if missing_files:
        log(f"Verification failed: {len(missing_files)} essential files are missing")
        for missing in missing_files:
            log(f"Missing: {missing}")
        return False
    
    # Check for ROOT label on hypervisor partition
    result = subprocess.run(['blkid', f'{boot_device}p2'], capture_output=True, text=True)
    if 'LABEL="ROOT"' not in result.stdout:
        log("Verification failed: ROOT label not found on hypervisor partition")
        return False
    
    log("Verification successful: All required boot files are present")
    return True

def run_nutanix_installation(params, config):
    """Run the actual Nutanix installation"""
    log("Starting Nutanix CE installation...")
    
    try:
        # Import installation modules
        log("Importing Nutanix installation modules...")
        try:
            import imagingUtil
            import sysUtil
            import shell
        except ImportError as e:
            log(f"Failed to import required modules: {e}")
            drop_to_shell("Failed to import Nutanix installation modules")
        
        # Patch shell commands to protect partitions
        log("Patching shell commands to protect partitions...")
        original_shell_cmd = shell.shell_cmd
        
        def protected_shell_cmd(cmd_list, *args, **kwargs):
            cmd_str = ' '.join(cmd_list) if isinstance(cmd_list, list) else str(cmd_list)
            if 'wipefs' in cmd_str and params.boot_disk in cmd_str:
                log(f'BLOCKED: {cmd_str}')
                return '', ''
            return original_shell_cmd(cmd_list, *args, **kwargs)
        
        shell.shell_cmd = protected_shell_cmd
        sysUtil.shell_cmd = protected_shell_cmd
        
        # Bypass hardware detection
        log("Bypassing hardware detection...")
        try:
            import layout.layout_tools
            def mock_get_hyp_raid_info_from_layout(layout):
                return None, None
            layout.layout_tools.get_hyp_raid_info_from_layout = mock_get_hyp_raid_info_from_layout
        except ImportError:
            pass
        
        def bypass_populate_host_boot_disk_param(param_list):
            pass
        sysUtil.populate_host_boot_disk_param = bypass_populate_host_boot_disk_param
        
        # Log installation summary
        log("Installation Summary:")
        log(f"  Node:          {config['node']['node_serial']}")
        log(f"  Hypervisor:    KVM on {params.ce_hyp_boot_disk}")
        log(f"  Storage:       {len(params.ce_cvm_data_disks)} data drives")
        log(f"  CVM:           {params.svm_gb_ram}GB RAM, {params.svm_num_vcpus} vCPUs")
        log(f"  CVM IP:        {params.cvm_interfaces[0]['ip']}")

        # Start installation
        log("Starting installation process...")
        try:
            os.makedirs('/mnt/svm_installer', exist_ok=True)
            
            log("Calling imagingUtil.image_node...")
            imagingUtil.image_node(params)
            log("imagingUtil.image_node completed successfully")
        except Exception as e:
            error_str = str(e)
            if "umount /tmp/svm_install_chroot/dev" in error_str and "target is busy" in error_str:
                log("Warning: Could not unmount /tmp/svm_install_chroot/dev, but continuing...")
                try:
                    subprocess.run(['umount', '-f', '/tmp/svm_install_chroot/dev'], check=False)
                except:
                    pass
            else:
                raise
        
        log("Installation completed successfully!")
        return True
        
    except Exception as e:
        log(f"Installation error: {e}")
        import traceback
        log(f"Traceback: {traceback.format_exc()}")
        return False

def main():
    """Main installation function"""
    global management_ip, config_server
    log("=== Nutanix CE VPC Bare Metal Server Installation ===")
    log("Platform: IBM Cloud VPC - Production Version")
    
    # Phase 1: Initialization
    management_ip = get_management_ip()
    config_server = get_config_server_from_cmdline()
    
    if not config_server:
        drop_to_shell("Could not determine config server URL from command line")
    
    if not management_ip:
        drop_to_shell("Could not determine management IP address")
    
    log(f"Management IP: {management_ip}, Config Server: {config_server}")
    log("Initialization complete", phase=1)

    # Phase 2: Download Node Configuration
    log("Downloading node configuration", phase=2)
    config = download_node_config(config_server, management_ip)
    if not config:
        drop_to_shell("Unable to download node configuration from server")
    
    # Phase 3: Validate Configuration
    log("Validating configuration", phase=3)
    if not validate_config(config):
        drop_to_shell("Configuration validation failed")
    
    # Phase 4: Download Packages
    log("Downloading installation packages", phase=4)
    if not download_packages(config_server):
        drop_to_shell("Failed to download required installation packages")
    
    # Phase 5: Install Hypervisor
    log("Installing AHV hypervisor", phase=5)
    if not install_hypervisor(config):
        drop_to_shell("AHV hypervisor installation failed")
    
    # Setup environment
    setup_environment(config)
    
    # Add required paths
    phoenix_dir = '/phoenix'
    if phoenix_dir not in sys.path:
        sys.path.insert(0, phoenix_dir)
    
    site_packages_paths = [
        '/usr/lib/python3.9/site-packages',
        '/usr/lib/python3.6/site-packages'
    ]
    
    for site_packages in site_packages_paths:
        if site_packages not in sys.path:
            sys.path.insert(0, site_packages)
    
    # Create mock modules for missing dependencies
    create_mock_modules(config)
    
    # Ensure node configuration exists
    if 'node' not in config:
        config['node'] = {
            'block_id': str(uuid.uuid4()).split('-')[0],
            'node_position': 'A',
            'node_serial': str(uuid.uuid4()),
            'cluster_id': generate_cluster_id()
        }
    
    # Create installation parameters
    params = create_installation_params(config)
    if not params:
        drop_to_shell("Failed to create installation parameters")
    
    # Phase 6: Clean and run Nutanix installation
    if not cleanup_previous_attempts():
        drop_to_shell("Cleanup of previous installation attempts failed")
    
    log("Running Nutanix installation", phase=6)
    if not run_nutanix_installation(params, config):
        drop_to_shell("Nutanix installation process failed")
    
    # Phase 7: Verify Installation
    log("Verifying installation", phase=7)
    if not verify_installation(config):
        drop_to_shell("Installation verification failed")
    
    # Phase 8: Reboot Server
    log("Installation complete. Rebooting server.", phase=8)
    subprocess.run(['reboot'])
    
    log("Installation completed successfully!")
    return 0

def create_mock_modules(config):
    """Create mock modules for missing dependencies"""
    import types
    
    # Mock hardware_inventory module
    try:
        import hardware_inventory
    except ImportError:
        hardware_inventory = types.ModuleType('hardware_inventory')
        sys.modules['hardware_inventory'] = hardware_inventory
        
        # Create disk_info submodule
        disk_info = types.ModuleType('hardware_inventory.disk_info')
        
        class MockDisk:
            def __init__(self, dev, model="Generic SSD", size=100, is_ssd=True):
                self.dev = dev
                self.model = model
                self.size = size
                self.isSSD = is_ssd
            
            def is_virtual_disk(self):
                return False
        
        def mock_collect_disk_info(disk_list_filter=None, skip_part_info=True):
            result = {}
            boot_disk = config['hardware']['boot_disk']
            result[boot_disk] = MockDisk(boot_disk, "Boot SSD", 200)
            
            for disk in config['hardware']['cvm_data_disks']:
                result[disk] = MockDisk(disk, "Data SSD", 500)
                
            return result
        
        disk_info.collect_disk_info = mock_collect_disk_info
        disk_info.list_hyp_boot_disks = lambda: [config['hardware']['boot_disk']]
        
        sys.modules['hardware_inventory.disk_info'] = disk_info
        hardware_inventory.disk_info = disk_info
    
    # Mock layout modules
    try:
        import layout
    except ImportError:
        layout = types.ModuleType('layout')
        sys.modules['layout'] = layout
        
        layout_finder = types.ModuleType('layout.layout_finder')
        layout_finder.find_model_match = lambda: (None, "CommunityEdition", "Nutanix Community Edition")
        layout_finder.is_layout_supported = lambda: True
        layout_finder.get_layout = lambda x: {"node": {"boot_device": {"structure": "HYPERVISOR_ONLY"}}}
        sys.modules['layout.layout_finder'] = layout_finder
        
        layout_tools = types.ModuleType('layout.layout_tools')
        layout_tools.get_boot_device_from_layout = lambda layout, lun_index=0: None
        layout_tools.get_hyp_raid_info_from_layout = lambda layout: (None, None)
        layout_tools.get_data_disks = lambda layout: config['hardware']['cvm_data_disks']
        sys.modules['layout.layout_tools'] = layout_tools
        
        # Add missing layout_vroc_utils module
        layout_vroc_utils = types.ModuleType('layout.layout_vroc_utils')
        layout_vroc_utils.get_vroc_disks = lambda layout: []
        layout_vroc_utils.get_vroc_raid_info = lambda layout: (None, None)
        layout_vroc_utils.is_vroc_supported = lambda: False
        layout_vroc_utils.get_vroc_volume = lambda layout, volume_id=None: None
        sys.modules['layout.layout_vroc_utils'] = layout_vroc_utils
        
        layout.layout_finder = layout_finder
        layout.layout_tools = layout_tools
        layout.layout_vroc_utils = layout_vroc_utils

if __name__ == "__main__":
    sys.exit(main())
