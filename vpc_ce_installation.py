#!/usr/bin/env python3

"""
Nutanix CE VPC Installation Script

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

# Set to False to reduce logging verbosity
VERBOSE_LOGGING = False

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

def log(message, phase=-1, send_to_api=True, verbose=False):
    """
    Log a message to stdout and optionally send to the status API.
    
    Args:
        message: The message to log
        phase: The installation phase number (default: -1 for general logs)
        send_to_api: Whether to also send the message to the API (default: True)
        verbose: Whether this is a verbose/debug log (default: False)
    """
    global management_ip, config_server, VERBOSE_LOGGING
    
    # Only print verbose logs if VERBOSE_LOGGING is enabled
    if not verbose or VERBOSE_LOGGING:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    # Send log message to API if requested and it's not a verbose log
    # No need for recursion protection since send_status_update always calls log with send_to_api=False
    if send_to_api and management_ip and config_server and not verbose:
        # Send status update with specified phase
        send_status_update(management_ip, phase, message)

def get_management_ip():
    """Get IP address of first interface as management IP, in the form of x-x-x-x"""
    
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
                    # Fix the space between hostname and port number
                    server = server.replace(': ', ':')
                    log(f"Fixed port separator in URL: '{server}'", verbose=True)
                
                # Clean up the URL - remove any remaining spaces
                if ' ' in server:
                    log(f"Warning: Config server URL contains spaces: '{server}'", verbose=True)
                    server = server.replace(' ', '')
                    log(f"Cleaned config server URL: '{server}'", verbose=True)
                
                # Ensure URL has proper format
                if not server.startswith('http://') and not server.startswith('https://'):
                    server = 'http://' + server
                
                log(f"Config server from cmdline (cleaned): {server}")
                return server
    except Exception as e:
        log(f"Error reading cmdline: {e}")

def download_node_config(config_server, management_ip):
    """Download node-specific configuration"""
    log(f"Downloading configuration for node: {management_ip}")
    
    if not config_server:
        log("Error: Config server URL is empty or invalid")
        return None
    
    # No need to clean up URL here as it's already cleaned in main()
    
    url = f"{config_server}/boot/server/{management_ip}"
    
    try:
        log(f"Trying config URL: {url}")
        
        # Add more detailed logging
        log(f"Running curl command: curl -s --connect-timeout 10 --max-time 30 {url}", verbose=True)
        
        result = subprocess.run([
            'curl', '-s', '--connect-timeout', '10',
            '--max-time', '30', url
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        log(f"Curl command returned code: {result.returncode}", verbose=True)
        
        if result.returncode == 0:
            log(f"Curl output: {result.stdout[:100]}..." if len(result.stdout) > 100 else f"Curl output: {result.stdout}", verbose=True)
            
            if result.stdout.strip():
                try:
                    config = json.loads(result.stdout)
                    log(f"Configuration downloaded from: {url}")
                    return config
                except json.JSONDecodeError as e:
                    log(f"Invalid JSON from {url}: {e}")
                    log(f"First 200 chars of response: {result.stdout[:200]}", verbose=True)
            else:
                log("Empty response from server")
        else:
            log(f"Failed to download from {url}")
            log(f"Curl stderr: {result.stderr}", verbose=True)
            
    except Exception as e:
        log(f"Error downloading from {url}: {e}")
        import traceback
        log(f"Traceback: {traceback.format_exc()}", verbose=True)
    
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
   
   # Validate config_server URL
   if not config_server:
       log("Error: Config server URL is empty or invalid")
       return False
   
   # No need to clean up URL here as it's already cleaned in main()
   
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
       log(f"Download URL: {url}")
       
       # Create directory if needed
       os.makedirs(os.path.dirname(local_path), exist_ok=True)
       
       # Use os.system for direct execution, similar to console
       curl_cmd = f"curl -L --progress-bar --connect-timeout 30 --max-time 1200 --retry 5 -o {local_path} {url}"
       log(f"Executing: {curl_cmd}", verbose=True)
       
       # Execute curl command directly
       exit_code = os.system(curl_cmd)
       log(f"Curl command exit code: {exit_code}")
       
       # Check if file exists and has reasonable size
       if exit_code == 0 and os.path.exists(local_path):
           file_size = os.path.getsize(local_path)
           log(f"Downloaded file size: {file_size:,} bytes")
           
           if file_size > 1024 * 1024:  # At least 1MB
               log(f"Successfully downloaded {os.path.basename(local_path)} ({file_size:,} bytes)")
           else:
               log(f"Downloaded file too small: {os.path.basename(local_path)} - only {file_size:,} bytes")
               
               # Try wget as fallback
               log("Trying wget as fallback...")
               wget_cmd = f"wget -O {local_path} {url}"
               log(f"Executing: {wget_cmd}")
               exit_code = os.system(wget_cmd)
               
               if exit_code == 0 and os.path.exists(local_path):
                   file_size = os.path.getsize(local_path)
                   if file_size > 1024 * 1024:
                       log(f"Successfully downloaded with wget: {os.path.basename(local_path)} ({file_size:,} bytes)")
                   else:
                       log(f"Wget download also too small: {file_size:,} bytes")
                       return False
               else:
                   log("Wget download failed")
                   return False
       else:
           log(f"Failed to download {os.path.basename(local_path)}")
           return False
   
   return True

def install_hypervisor(config):
   """Install AHV hypervisor to boot disk"""

   log("Wiping all drives...")
   wipe_nvmes()

   log("Installing AHV hypervisor...")
   
   boot_disk = config['hardware']['boot_disk']
   # Assume boot_disk is a string
   log(f"Using boot disk: {boot_disk}")
   boot_device = f"/dev/{boot_disk}"
   
   try:
       # Create hypervisor partitions
       log("Creating hypervisor partitions...")
       # Create partitions:
       # 1. EFI partition (200MB)
       # 2. Hypervisor partition (32GB)
       # 3. Data partition (rest of disk)
       # Then set partition 1 type to EF (EFI System) and mark it as bootable
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
       
       log(f"Formatted hypervisor partition with ROOT label")
       
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
       
       # Ensure EFI partition is formatted correctly
       log("Ensuring EFI partition is formatted correctly...")
       result = subprocess.run(['mkfs.vfat', '-F', '32', f'{boot_device}p1'], capture_output=True)
       if result.returncode != 0:
           log(f"Warning: Could not format EFI partition: {result.stderr}")
       
       # Mount EFI partition with verbose logging
       log(f"Mounting EFI partition {boot_device}p1 to /mnt/stage/boot/efi/...")
       result = subprocess.run(['mount', '-v', f'{boot_device}p1', '/mnt/stage/boot/efi/'],
                             capture_output=True, text=True)
       if result.returncode != 0:
           log(f"Failed to mount EFI partition: {result.stderr}")
           cleanup_mounts()
           return False
       
       # Verify mount
       result = subprocess.run(['findmnt', '/mnt/stage/boot/efi'], capture_output=True, text=True)
       if result.returncode != 0:
           log("EFI partition not properly mounted, trying alternative mount method...")
           # Try alternative mount method
           subprocess.run(['umount', '/mnt/stage/boot/efi'], capture_output=True)
           result = subprocess.run(['mount', '-t', 'vfat', f'{boot_device}p1', '/mnt/stage/boot/efi/'],
                                 capture_output=True, text=True)
           if result.returncode != 0:
               log(f"Alternative mount also failed: {result.stderr}")
               cleanup_mounts()
               return False
       
       log("EFI partition mounted successfully")
       
       # Copy EFI files with verbose logging
       log("Copying EFI files from ISO...")
       result = subprocess.run(['find', '/mnt/ahv/EFI', '-type', 'f'], capture_output=True, text=True)
       if result.stdout.strip():
           log(f"Found EFI files in ISO: {result.stdout}")
           result = subprocess.run(['cp', '-rv', '/mnt/ahv/EFI/.', '/mnt/stage/boot/efi/'],
                                 capture_output=True, text=True)
           if result.returncode != 0:
               log(f"Failed to copy EFI files: {result.stderr}")
               log("Will try to create EFI directories and files manually")
           else:
               log("Successfully copied EFI files from ISO")
       else:
           log("No EFI directory found in ISO, will create manually")
           
       # Create additional EFI directories with verbose logging
       log("Creating EFI directory structure...")
       efi_dirs = [
           '/mnt/stage/boot/efi/EFI',
           '/mnt/stage/boot/efi/EFI/BOOT',
           '/mnt/stage/boot/efi/EFI/NUTANIX',
           '/mnt/stage/boot/efi/EFI/redhat',
           '/mnt/stage/boot/efi/EFI/centos'
       ]
       
       for efi_dir in efi_dirs:
           os.makedirs(efi_dir, exist_ok=True)
           log(f"Created directory: {efi_dir}")
       
       # Verify EFI directories exist
       result = subprocess.run(['ls', '-la', '/mnt/stage/boot/efi/EFI'], capture_output=True, text=True)
       log(f"EFI directory contents: {result.stdout}")
       
       # Find and copy GRUB EFI binary with comprehensive search
       log("Finding and copying GRUB EFI binary with comprehensive search...")
       
       # Search in multiple locations
       grub_efi_paths = []
       search_locations = ['/mnt/ahv', '/mnt/stage', '/mnt/install']
       search_patterns = ['grubx64.efi', 'BOOTX64.EFI', 'shimx64.efi', 'GRUBX64.EFI']
       
       for location in search_locations:
           for pattern in search_patterns:
               result = subprocess.run(['find', location, '-name', pattern, '-type', 'f'],
                                     capture_output=True, text=True)
               if result.stdout.strip():
                   grub_efi_paths.extend(result.stdout.strip().split('\n'))
       
       if grub_efi_paths:
           log(f"Found {len(grub_efi_paths)} GRUB EFI binaries:")
           for path in grub_efi_paths:
               log(f"  - {path}")
           
           # Use the first one found
           grub_efi_path = grub_efi_paths[0]
           log(f"Using GRUB EFI binary at {grub_efi_path}")
           
           # Copy to essential locations only to save space
           efi_targets = [
               ('/mnt/stage/boot/efi/EFI/BOOT/BOOTX64.EFI', 'BOOTX64.EFI'),  # Primary EFI location
               ('/mnt/stage/boot/efi/EFI/NUTANIX/grubx64.efi', 'grubx64.efi')  # Nutanix-specific location
           ]
           
           # Check EFI partition space before copying
           df_result = subprocess.run(['df', '-k', '/mnt/stage/boot/efi'],
                                     capture_output=True, text=True)
           log(f"EFI partition space before copying GRUB binaries: {df_result.stdout}")
           
           for target_path, target_name in efi_targets:
               try:
                   result = subprocess.run(['cp', grub_efi_path, target_path],
                                         capture_output=True, text=True)
                   if result.returncode == 0:
                       log(f"Copied GRUB EFI binary to {target_path}")
                   else:
                       log(f"Failed to copy GRUB EFI binary to {target_path}: {result.stderr}")
                       if 'No space left on device' in result.stderr:
                           log("EFI partition is full, skipping remaining copies")
                           break
               except Exception as e:
                   log(f"Error copying GRUB EFI binary to {target_path}: {e}")
           
           # Verify essential files were copied
           for target_path, _ in efi_targets:
               if os.path.exists(target_path):
                   log(f"Verified EFI binary exists at {target_path}")
               else:
                   log(f"WARNING: EFI binary not found at {target_path}")
           
           log("Copied GRUB EFI binary to standard locations")
       else:
           log("Could not find GRUB EFI binary in any location, creating a minimal one...")
           
           # Create a minimal GRUB EFI binary as a last resort
           efi_targets = [
               '/mnt/stage/boot/efi/EFI/BOOT/BOOTX64.EFI',
               '/mnt/stage/boot/efi/EFI/NUTANIX/grubx64.efi'
           ]
           
           for target_path in efi_targets:
               with open(target_path, 'wb') as f:
                   # Write a minimal EFI stub header
                   f.write(b'MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00\xb8\x00\x00\x00\x00\x00\x00\x00\x40\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x80\x00\x00\x00\x0e\x1f\xba\x0e\x00\xb4\x09\xcd\x21\xb8\x01\x4c\xcd\x21This program cannot be run in DOS mode.\r\r\n$\x00\x00\x00\x00\x00\x00\x00')
               log(f"Created minimal EFI binary at {target_path}")
       
       # Create startup.nsh script for EFI shell fallback boot (only in the root of EFI partition)
       log("Creating startup.nsh script for EFI shell fallback boot...")
       
       startup_script = f"""@echo -off
echo Loading Nutanix AHV...
echo Attempting to boot from EFI/BOOT...
\\EFI\\BOOT\\BOOTX64.EFI
echo If that failed, trying EFI/NUTANIX...
\\EFI\\NUTANIX\\grubx64.efi
echo If that failed, trying direct kernel boot...
echo Loading kernel: vmlinuz
echo Loading initrd: initrd
echo Boot parameters: root=LABEL=ROOT ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
\\vmlinuz root=LABEL=ROOT ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal initrd=\\initrd
"""
       
       # Only create startup.nsh in the root of the EFI partition to save space
       startup_script_path = '/mnt/stage/boot/efi/startup.nsh'
       try:
           with open(startup_script_path, 'w') as f:
               f.write(startup_script)
           log(f"Created startup.nsh script at {startup_script_path}")
       except Exception as e:
           log(f"Failed to create startup.nsh script: {e}")
       
       # Create a grub.cfg file directly in the EFI partition (only in essential locations)
       log("Creating grub.cfg in EFI partition directories...")
       
       # Check available space before creating more files
       df_result = subprocess.run(['df', '-k', '/mnt/stage/boot/efi'],
                                 capture_output=True, text=True)
       log(f"EFI partition space before creating GRUB configs: {df_result.stdout}")
       
       # Create minimal but essential GRUB configuration
       efi_grub_config = f"""# GRUB configuration for Nutanix AHV (EFI partition)
insmod part_gpt
insmod ext2
insmod search_fs_uuid
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

# Boot entry
menuentry 'Nutanix AHV' --unrestricted --id nutanix {{
 echo 'Loading Linux kernel...'
 linux /vmlinuz root=LABEL=ROOT ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 quiet pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
 echo 'Loading initial ramdisk...'
 initrd /initrd
}}
"""
       
       # Only create in essential locations
       efi_grub_locations = [
           '/mnt/stage/boot/efi/EFI/BOOT/grub.cfg',  # Primary location
           '/mnt/stage/boot/efi/EFI/NUTANIX/grub.cfg'  # Nutanix-specific location
       ]
       
       for grub_path in efi_grub_locations:
           try:
               os.makedirs(os.path.dirname(grub_path), exist_ok=True)
               with open(grub_path, 'w') as f:
                   f.write(efi_grub_config)
               log(f"Created grub.cfg at {grub_path}")
           except Exception as e:
               log(f"Failed to create grub.cfg at {grub_path}: {e}")
               if 'No space left on device' in str(e):
                   log("EFI partition is full, skipping remaining GRUB configs")
                   break
       
       log("Created startup.nsh scripts and GRUB configurations in EFI partition")
       
       # Create GRUB configurations
       log("Creating GRUB configurations...")
       
       # GRUB2 configuration
       os.makedirs('/mnt/stage/boot/grub2', exist_ok=True)
       kernel_version = "5.10.194-5.20230302.0.991650.el8.x86_64"
       
       # Get UUID of the root partition
       result = subprocess.run(['blkid', '-s', 'UUID', '-o', 'value', f'{boot_device}p2'],
                             capture_output=True, text=True)
       root_uuid = result.stdout.strip() if result.returncode == 0 else None
       
       # Create a more comprehensive GRUB configuration with multiple boot options
       grub2_config = f"""# GRUB configuration for Nutanix AHV
insmod part_gpt
insmod ext2
insmod search_fs_uuid
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
  linux /boot/vmlinuz-{kernel_version} root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
  echo 'Loading initial ramdisk...'
  initrd /boot/initramfs-{kernel_version}.img
}}

# Fallback entry with symlinks
menuentry 'Nutanix AHV (Fallback)' --unrestricted --id nutanix_fallback {{
  echo 'Loading Linux kernel (fallback)...'
  linux /vmlinuz root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
  echo 'Loading initial ramdisk (fallback)...'
  initrd /initrd
}}
"""

       # Add UUID-based entry if we have the UUID
       if root_uuid:
           grub2_config += f"""
# UUID-based entry
menuentry 'Nutanix AHV (UUID)' --unrestricted --id nutanix_uuid {{
  echo 'Loading Linux kernel (UUID)...'
  search --no-floppy --set=root --fs-uuid {root_uuid}
  linux /boot/vmlinuz-{kernel_version} root=UUID={root_uuid} ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
  echo 'Loading initial ramdisk (UUID)...'
  initrd /boot/initramfs-{kernel_version}.img
}}
"""
       
       with open('/mnt/stage/boot/grub2/grub.cfg', 'w') as f:
           f.write(grub2_config)
       
       # Legacy GRUB configuration
       os.makedirs('/mnt/stage/boot/grub', exist_ok=True)
       grub_config = f"""default=0
timeout=5
title Nutanix AHV
 root (hd0,1)
 kernel /boot/vmlinuz-{kernel_version} root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
 initrd /boot/initramfs-{kernel_version}.img

title Nutanix AHV (Fallback)
 root (hd0,1)
 kernel /vmlinuz root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
 initrd /initrd
"""
       
       with open('/mnt/stage/boot/grub/grub.conf', 'w') as f:
           f.write(grub_config)
       
       log("GRUB configurations created")
       
       # Create a rescue script that can be used to manually boot the system
       log("Creating rescue script...")
       rescue_script = f"""#!/bin/sh
# Rescue script for Nutanix AHV boot
echo "Nutanix AHV Rescue Boot Script"
echo "Attempting to find and boot the kernel..."

# List all available kernels and initrds
echo "Available kernels:"
find / -name "vmlinuz*" -o -name "bzImage*" 2>/dev/null | sort
echo ""
echo "Available initrds:"
find / -name "initramfs*" -o -name "initrd*" 2>/dev/null | sort
echo ""

# Try different kernel paths
for KERNEL_PATH in /boot/vmlinuz-{kernel_version} /vmlinuz /boot/bzImage /bzImage /boot/vmlinuz-*.x86_64 /boot/vmlinuz-*; do
 if [ -f "$KERNEL_PATH" ]; then
   echo "Found kernel at $KERNEL_PATH"
   
   # Try different initrd paths
   for INITRD_PATH in /boot/initramfs-{kernel_version}.img /initrd /boot/initramfs-*.img; do
     if [ -f "$INITRD_PATH" ]; then
       echo "Found initrd at $INITRD_PATH"
       
       # Try different root specifications
       for ROOT_SPEC in "root=/dev/{boot_disk}p2" "root=LABEL=ROOT" "root=UUID=$(blkid -s UUID -o value /dev/{boot_disk}p2 2>/dev/null || echo 'none')"; do
         echo "Attempting boot with $ROOT_SPEC"
         echo "kexec -l $KERNEL_PATH --initrd=$INITRD_PATH --command-line=\\"$ROOT_SPEC ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal\\""
         
         kexec -l $KERNEL_PATH --initrd=$INITRD_PATH --command-line="$ROOT_SPEC ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal" 2>/dev/null
         
         if [ $? -eq 0 ]; then
           echo "kexec load successful, executing kernel..."
           echo "Press Ctrl+C within 5 seconds to abort..."
           sleep 5
           kexec -e
           # If we get here, kexec failed
           echo "kexec execution failed, trying next option"
         else
           echo "kexec load failed, trying next option"
         fi
       done
     fi
   done
 fi
done

# If all automatic attempts fail, provide manual instructions
echo "All automatic boot attempts failed!"
echo ""
echo "Manual boot instructions:"
echo "1. Find a valid kernel:"
echo "   ls -la /boot/vmlinuz*"
echo ""
echo "2. Find a valid initrd:"
echo "   ls -la /boot/initramfs*"
echo ""
echo "3. Try manual boot with kexec:"
echo "   kexec -l /path/to/kernel --initrd=/path/to/initrd --command-line=\\"root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal\\""
echo "   kexec -e"
echo ""
echo "4. Or try manual boot from GRUB command line:"
echo "   linux /boot/vmlinuz-{kernel_version} root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal"
echo "   initrd /boot/initramfs-{kernel_version}.img"
echo "   boot"
echo ""
echo "Dropping to shell for manual recovery"
exec /bin/sh
"""
       
       with open('/mnt/stage/boot/rescue.sh', 'w') as f:
           f.write(rescue_script)
       subprocess.run(['chmod', '+x', '/mnt/stage/boot/rescue.sh'])
       log("Created rescue script at /boot/rescue.sh")
       
       # Add a rescue entry to the GRUB configuration
       with open('/mnt/stage/boot/grub2/grub.cfg', 'a') as f:
           f.write(f"""
# Rescue script entry
menuentry 'Nutanix AHV (Rescue Script)' --unrestricted --id nutanix_rescue {{
 echo 'Running rescue script...'
 linux /boot/rescue.sh
}}
""")
       log("Added rescue script entry to GRUB configuration")
       
       # Generate initramfs with required modules
       log("Generating initramfs with NVMe and Ionic support...")
       
       # Create a dracut configuration file to ensure NVMe and Ionic modules are included
       os.makedirs('/mnt/stage/etc/dracut.conf.d', exist_ok=True)
       with open('/mnt/stage/etc/dracut.conf.d/vpc_drivers.conf', 'w') as f:
           f.write("""# Include NVMe and Ionic modules in initramfs
add_drivers+=" nvme nvme-core ionic "
force_drivers+=" nvme nvme-core ionic "
hostonly="no"
hostonly_cmdline="no"
early_microcode="yes"
""")
       
       # Create a modprobe configuration to load the ionic driver at boot
       # Create modules-load.d directory but don't create ionic.conf file
       # to prevent loading the ionic driver at boot
       os.makedirs('/mnt/stage/etc/modules-load.d', exist_ok=True)
       log("Skipping creation of ionic.conf to disable the ionic driver")
       
       # Set SELinux to permissive mode to avoid issues with ionic driver
       log("Configuring SELinux for ionic driver...")
       
       # Create SELinux config file to set permissive mode
       os.makedirs('/mnt/stage/etc/selinux', exist_ok=True)
       with open('/mnt/stage/etc/selinux/config', 'w') as f:
           f.write("""# This file controls the state of SELinux on the system.
# SELINUX= can take one of these three values:
#     enforcing - SELinux security policy is enforced.
#     permissive - SELinux prints warnings instead of enforcing.
#     disabled - No SELinux policy is loaded.
SELINUX=permissive
# SELINUXTYPE= can take one of these three values:
#     targeted - Targeted processes are protected,
#     minimum - Modification of targeted policy. Only selected processes are protected.
#     mls - Multi Level Security protection.
SELINUXTYPE=targeted
""")
       log("Set SELinux to permissive mode in config")
       
       # Note: We'll add selinux=0 to GRUB_CMDLINE_LINUX when the GRUB defaults file is created later
       
       # Create a script to run at first boot to properly label the ionic.conf file
       os.makedirs('/mnt/stage/etc/rc.d/rc.local.d', exist_ok=True)
       with open('/mnt/stage/etc/rc.d/rc.local.d/fix_selinux.sh', 'w') as f:
           f.write("""#!/bin/bash
# Fix SELinux labels for ionic driver files
if [ -x /usr/sbin/restorecon ]; then
   # Skip restorecon for ionic.conf since we're not creating it
   /usr/sbin/restorecon -Rv /lib/modules/*/kernel/drivers/net/ethernet/pensando
fi
""")
       
       # Make the script executable
       subprocess.run(['chmod', '+x', '/mnt/stage/etc/rc.d/rc.local.d/fix_selinux.sh'])
       
       # Ensure rc.local is enabled and executable
       with open('/mnt/stage/etc/rc.d/rc.local', 'a') as f:
           f.write("""
# Run custom scripts in rc.local.d
if [ -d /etc/rc.d/rc.local.d ]; then
   for script in /etc/rc.d/rc.local.d/*.sh; do
       if [ -x "$script" ]; then
           echo "Running $script"
           $script
       fi
   done
fi
""")
       
       subprocess.run(['chmod', '+x', '/mnt/stage/etc/rc.d/rc.local'])
       subprocess.run(['chroot', '/mnt/stage', 'systemctl', 'enable', 'rc-local.service'])
       
       log("Created SELinux fix script to run at first boot")
       
       # Copy the ionic driver module from the current environment to the hypervisor
       log("Copying ionic driver module to hypervisor...")
       
       # Find the ionic.ko module in the current environment
       result = subprocess.run(['find', '/', '-name', 'ionic.ko'],
                             capture_output=True, text=True)
       
       if result.stdout.strip():
           ionic_module_path = result.stdout.strip().split('\n')[0]
           log(f"Found ionic module at {ionic_module_path}")
           
           # Create the destination directory in the hypervisor
           kernel_version = "5.10.194-5.20230302.0.991650.el8.x86_64"
           module_dest_dir = f"/mnt/stage/lib/modules/{kernel_version}/kernel/drivers/net/ethernet/pensando"
           os.makedirs(module_dest_dir, exist_ok=True)
           
           # Copy the module
           try:
               subprocess.run(['cp', ionic_module_path, f"{module_dest_dir}/ionic.ko"],
                             check=True, capture_output=True)
               log("Successfully copied ionic driver module")
               
               # Run depmod to update module dependencies
               subprocess.run(['chroot', '/mnt/stage', 'depmod', '-a', kernel_version],
                             capture_output=True)
               
               # Ensure the initramfs is created
               log("Creating initramfs with dracut...")
               
               # First, check if dracut is available in the chroot
               result = subprocess.run(['chroot', '/mnt/stage', 'which', 'dracut'],
                                     capture_output=True, text=True)
               
               if result.returncode == 0:
                   # Use dracut to create the initramfs
                   log("Using dracut to create initramfs...")
                   result = subprocess.run(['chroot', '/mnt/stage', 'dracut', '--force', '--no-hostonly',
                                          f'/boot/initramfs-{kernel_version}.img', kernel_version],
                                         capture_output=True, text=True)
                   
                   if result.returncode == 0:
                       log("Successfully created initramfs with dracut")
                   else:
                       log(f"Failed to create initramfs with dracut: {result.stderr}")
                       
                       # Try to copy an existing initramfs from the ISO
                       log("Trying to find an initramfs in the ISO...")
                       result = subprocess.run(['find', '/mnt/ahv', '-name', 'initramfs*'],
                                             capture_output=True, text=True)
                       
                       if result.stdout.strip():
                           initramfs_path = result.stdout.strip().split('\n')[0]
                           log(f"Found initramfs at {initramfs_path}")
                           
                           # Copy the initramfs
                           subprocess.run(['cp', initramfs_path, f'/mnt/stage/boot/initramfs-{kernel_version}.img'])
                           log(f"Copied initramfs from {initramfs_path} to /mnt/stage/boot/initramfs-{kernel_version}.img")
                       else:
                           log("Could not find an initramfs in the ISO")
               else:
                   log("dracut not available in chroot, trying to find an existing initramfs...")
                   
                   # Try to find an existing initramfs in the ISO
                   result = subprocess.run(['find', '/mnt/ahv', '-name', 'initramfs*'],
                                         capture_output=True, text=True)
                   
                   if result.stdout.strip():
                       initramfs_path = result.stdout.strip().split('\n')[0]
                       log(f"Found initramfs at {initramfs_path}")
                       
                       # Copy the initramfs
                       subprocess.run(['cp', initramfs_path, f'/mnt/stage/boot/initramfs-{kernel_version}.img'])
                       log(f"Copied initramfs from {initramfs_path} to /mnt/stage/boot/initramfs-{kernel_version}.img")
                   else:
                       log("Could not find an initramfs in the ISO")
               log("Updated module dependencies")
           except subprocess.CalledProcessError as e:
               log(f"Failed to copy ionic module: {e}")
               log("This may affect network connectivity after boot")
       else:
           log("Could not find ionic.ko module in the current environment")
           log("Will rely on the module being included in the AHV image")
       
       # Detect the correct kernel version
       log("Detecting kernel version...")
       result = subprocess.run(['chroot', '/mnt/stage', 'ls', '-1', '/lib/modules'],
                             capture_output=True, text=True)
       
       if result.returncode == 0 and result.stdout.strip():
           # Use the first kernel version found
           kernel_version = result.stdout.strip().split('\n')[0]
           log(f"Detected kernel version: {kernel_version}")
       else:
           # Fallback to a common version format, trying both el8 and e18 variants
           log("Could not detect kernel version, using fallback versions")
           kernel_versions = [
               "5.10.194-5.20230302.0.991650.el8.x86_64",
               "5.10.194-5.20230302.0.991650.e18.x86_64",  # Include both formats to handle possible OCR errors
               "5.10.194-5.20230302.0.991650.x86_64",      # Try without el8/e18 prefix
               "5.10.0-0.x86_64",                          # Generic fallback
               "5.10.0-0.el8.x86_64"                       # Another common format
           ]
           
           # Check which kernel version exists
           for version in kernel_versions:
               if os.path.exists(f'/mnt/stage/lib/modules/{version}'):
                   kernel_version = version
                   log(f"Found kernel version: {kernel_version}")
                   break
           else:
               # If none found, use the first one as default
               kernel_version = kernel_versions[0]
               log(f"No kernel version found, using default: {kernel_version}")
       
       # Run dracut to generate the initramfs
       log(f"Generating initramfs for kernel version {kernel_version}")
       result = subprocess.run(['chroot', '/mnt/stage', 'dracut', '--force',
                               f'/boot/initramfs-{kernel_version}.img',
                               kernel_version],
                               capture_output=True, text=True)
       
       if result.returncode != 0:
           log(f"Failed to generate initramfs: {result.stderr}")
           log("This may cause boot issues, but we'll continue with installation")
       else:
           log("Successfully generated initramfs with NVMe support")
       
       # Install GRUB bootloader
       log("Installing GRUB bootloader with comprehensive approach...")
       
       # Create necessary directories for GRUB installation
       os.makedirs('/mnt/stage/boot/efi/EFI/BOOT', exist_ok=True)
       os.makedirs('/mnt/stage/boot/efi/EFI/NUTANIX', exist_ok=True)
       os.makedirs('/mnt/stage/boot/grub2', exist_ok=True)
       
       # Install required packages
       log("Installing required GRUB packages...")
       subprocess.run(['chroot', '/mnt/stage', 'yum', 'install', '-y',
                      'grub2-efi-x64', 'grub2-tools', 'efibootmgr', 'shim-x64'],
                     capture_output=True, text=True)
       
       # Comprehensive search for kernel files
       log("Performing comprehensive kernel file search...")
       
       # First, search for any kernel files in the system (more comprehensive search)
       result = subprocess.run(['find', '/mnt/stage', '-name', 'vmlinuz*', '-o', '-name', 'vmlinux*', '-o', '-name', 'bzImage*'],
                             capture_output=True, text=True)
       
       all_kernels = []
       if result.stdout.strip():
           all_kernels = result.stdout.strip().split('\n')
           log(f"Found {len(all_kernels)} kernel files in the system")
           for kernel in all_kernels:
               log(f"  - {kernel}")
       else:
           log("No kernel files found in the system!")
       
       # Search for initramfs files
       result = subprocess.run(['find', '/mnt/stage', '-name', 'initramfs*', '-o', '-name', 'initrd*'],
                             capture_output=True, text=True)
       
       all_initramfs = []
       if result.stdout.strip():
           all_initramfs = result.stdout.strip().split('\n')
           log(f"Found {len(all_initramfs)} initramfs files in the system")
           for initramfs in all_initramfs:
               log(f"  - {initramfs}")
       else:
           log("No initramfs files found in the system!")
       
       # Try to find matching kernel and initramfs
       kernel_path = None
       initramfs_path = None
       
       # First try to find a kernel with our specific version
       for kernel in all_kernels:
           if kernel_version in kernel:
               kernel_path = kernel.replace('/mnt/stage', '')
               log(f"Found matching kernel for version {kernel_version}: {kernel_path}")
               
               # Look for matching initramfs
               for initramfs in all_initramfs:
                   if kernel_version in initramfs:
                       initramfs_path = initramfs.replace('/mnt/stage', '')
                       log(f"Found matching initramfs: {initramfs_path}")
                       break
               
               break
       
       # If no matching kernel found, use the first available
       if not kernel_path and all_kernels:
           kernel_path = all_kernels[0].replace('/mnt/stage', '')
           # Extract version from filename
           kernel_basename = os.path.basename(kernel_path)
           if kernel_basename.startswith('vmlinuz-'):
               kernel_version = kernel_basename.replace('vmlinuz-', '')
           elif kernel_basename.startswith('vmlinux-'):
               kernel_version = kernel_basename.replace('vmlinux-', '')
           log(f"Using first available kernel: {kernel_path} with version {kernel_version}")
           
           # Look for matching initramfs
           for initramfs in all_initramfs:
               if kernel_version in initramfs:
                   initramfs_path = initramfs.replace('/mnt/stage', '')
                   log(f"Found matching initramfs: {initramfs_path}")
                   break
       
       # If still no kernel found, create one from the installation media
       if not kernel_path:
           log("No kernel found, searching installation media...")
           result = subprocess.run(['find', '/mnt/ahv', '-name', 'vmlinuz*'],
                                 capture_output=True, text=True)
           
           if result.stdout.strip():
               install_kernel = result.stdout.strip().split('\n')[0]
               log(f"Found kernel in installation media: {install_kernel}")
               
               # Copy to standard location
               os.makedirs('/mnt/stage/boot', exist_ok=True)
               kernel_path = f'/boot/vmlinuz-{kernel_version}'
               subprocess.run(['cp', install_kernel, f'/mnt/stage{kernel_path}'])
               log(f"Copied kernel to {kernel_path}")
           else:
               log("No kernel found in installation media!")
               kernel_path = f'/boot/vmlinuz-{kernel_version}'
               log(f"Using default kernel path: {kernel_path}")
       
       # If no initramfs found, create one
       if not initramfs_path:
           log("No matching initramfs found, creating one...")
           initramfs_path = f'/boot/initramfs-{kernel_version}.img'
           
           # Check if we already created one earlier
           if os.path.exists(f'/mnt/stage{initramfs_path}'):
               log(f"Using previously created initramfs: {initramfs_path}")
           else:
               log("No initramfs found, creating a basic one...")
               
               # Try to find an initramfs in the ISO again
               result = subprocess.run(['find', '/mnt/ahv', '-name', 'initramfs*', '-o', '-name', 'initrd*'],
                                     capture_output=True, text=True)
               
               if result.stdout.strip():
                   # Use the first initramfs found
                   iso_initramfs = result.stdout.strip().split('\n')[0]
                   log(f"Found initramfs in ISO: {iso_initramfs}")
                   
                   # Copy it to our target location
                   os.makedirs(os.path.dirname(f'/mnt/stage{initramfs_path}'), exist_ok=True)
                   subprocess.run(['cp', iso_initramfs, f'/mnt/stage{initramfs_path}'])
                   log(f"Copied initramfs from ISO to {initramfs_path}")
               else:
                   # Create a minimal initramfs if we can't find one
                   log("Creating a minimal initramfs file...")
                   os.makedirs(os.path.dirname(f'/mnt/stage{initramfs_path}'), exist_ok=True)
                   
                   # Try using dracut with minimal options
                   result = subprocess.run(['chroot', '/mnt/stage', 'dracut', '--force', '--no-hostonly',
                                          '--no-compress', '--omit', 'plymouth', '--omit', 'i18n',
                                          f'/boot/initramfs-{kernel_version}.img', kernel_version],
                                         capture_output=True, text=True)
                   
                   if result.returncode != 0:
                       log(f"Failed to create minimal initramfs with dracut: {result.stderr}")
                       
                       # Last resort: create an empty initramfs file
                       log("Creating an empty initramfs file as last resort...")
                       with open(f'/mnt/stage{initramfs_path}', 'wb') as f:
                           # Write a minimal cpio archive header
                           f.write(b'070701000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000b00000000TRAILER!!!\0\0\0\0')
                       log("Created minimal initramfs file")
       
       # Copy kernel and initramfs to essential locations only to avoid filling up the EFI partition
       log("Copying kernel and initramfs to essential locations...")
       
       # Define essential locations - prioritize main boot directory and only one copy in EFI
       # Make sure to include the locations that our verification function checks
       essential_locations = [
           ('/boot', 'vmlinuz'),  # Main boot directory - critical for booting
           ('/boot/efi/EFI/BOOT', 'vmlinuz'),  # Primary EFI location - critical for EFI boot
           ('/', 'vmlinuz')  # Root directory for fallback - CRITICAL for GRUB default entry
       ]
       
       # Check EFI partition size before copying
       efi_space_check = subprocess.run(['df', '-h', '/mnt/stage/boot/efi'],
                                       capture_output=True, text=True)
       log(f"EFI partition space before copying: {efi_space_check.stdout}")
       
       # Source files
       source_kernel = f'/mnt/stage{kernel_path}'
       source_initramfs = f'/mnt/stage{initramfs_path}'
       
       # Create minimal initramfs at source location if it doesn't exist
       if not os.path.exists(source_initramfs):
           log(f"WARNING: Source initramfs {initramfs_path} does not exist, creating a minimal one...")
           os.makedirs(os.path.dirname(source_initramfs), exist_ok=True)
           
           # Try to find an initramfs in the ISO first
           result = subprocess.run(['find', '/mnt/ahv', '-name', 'initramfs*', '-o', '-name', 'initrd*'],
                                 capture_output=True, text=True)
           
           if result.stdout.strip():
               # Use the first initramfs found
               iso_initramfs = result.stdout.strip().split('\n')[0]
               log(f"Found initramfs in ISO: {iso_initramfs}")
               
               # Copy it to our target location
               subprocess.run(['cp', iso_initramfs, source_initramfs])
               log(f"Copied initramfs from ISO to {source_initramfs}")
           else:
               # Create a minimal initramfs as last resort
               with open(source_initramfs, 'wb') as f:
                   # Write a minimal cpio archive header
                   f.write(b'070701000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000b00000000TRAILER!!!\0\0\0\0')
               log(f"Created minimal initramfs at source location {initramfs_path}")
       
       # Copy to essential locations
       for dir_path, prefix in essential_locations:
           target_dir = f'/mnt/stage{dir_path}'
           os.makedirs(target_dir, exist_ok=True)
           
           # Check if this is an EFI directory
           is_efi_dir = 'efi' in dir_path.lower()
           
           # For EFI directories, check available space first
           if is_efi_dir:
               df_result = subprocess.run(['df', '-k', target_dir],
                                         capture_output=True, text=True)
               
               # Parse available space
               available_kb = 0
               if df_result.returncode == 0:
                   for line in df_result.stdout.strip().split('\n'):
                       if target_dir in line or '/mnt/stage/boot/efi' in line:
                           parts = line.split()
                           if len(parts) >= 4:
                               try:
                                   available_kb = int(parts[3])
                               except ValueError:
                                   pass
               
               # Check if we have enough space (kernel ~10MB, initramfs ~20MB)
               required_kb = 30000  # 30MB
               if available_kb < required_kb:
                   log(f"WARNING: Not enough space in {target_dir} ({available_kb}KB available, {required_kb}KB required)")
                   log(f"Skipping copy to {target_dir} to avoid filling EFI partition")
                   continue
           
           # Copy kernel
           target_kernel = f'{target_dir}/{prefix}-{kernel_version}'
           if os.path.exists(source_kernel):
               try:
                   subprocess.run(['cp', source_kernel, target_kernel],
                                 capture_output=True, check=True)
                   log(f"Copied kernel to {target_kernel}")
                   
                   # For root directory, also create a copy without version suffix
                   # This is critical for GRUB's default entry which looks for /vmlinuz
                   if dir_path == '/':
                       plain_target = f'{target_dir}/{prefix}'
                       subprocess.run(['cp', source_kernel, plain_target],
                                     capture_output=True, check=True)
                       log(f"Copied kernel to {plain_target} (without version suffix)")
               except subprocess.CalledProcessError as e:
                   log(f"Failed to copy kernel to {target_kernel}: {e}")
                   if 'No space left on device' in str(e.stderr):
                       log("EFI partition is full, skipping remaining copies")
                       break
           
           # Copy initramfs
           target_initramfs = f'{target_dir}/initramfs-{kernel_version}.img'
           if os.path.exists(source_initramfs):
               try:
                   subprocess.run(['cp', source_initramfs, target_initramfs],
                                 capture_output=True, check=True)
                   log(f"Copied initramfs to {target_initramfs}")
                   
                   # For root directory, also create a copy without version suffix
                   # This is critical for GRUB's default entry which looks for /initrd
                   if dir_path == '/':
                       plain_target = f'{target_dir}/initrd'
                       subprocess.run(['cp', source_initramfs, plain_target],
                                     capture_output=True, check=True)
                       log(f"Copied initramfs to {plain_target} (without version suffix)")
               except subprocess.CalledProcessError as e:
                   log(f"Failed to copy initramfs to {target_initramfs}: {e}")
                   if 'No space left on device' in str(e.stderr):
                       log("EFI partition is full, skipping remaining copies")
                       break
           else:
               log(f"WARNING: Source initramfs {initramfs_path} does not exist")
       
       # Check EFI partition space after copying
       efi_space_check = subprocess.run(['df', '-h', '/mnt/stage/boot/efi'],
                                       capture_output=True, text=True)
       log(f"EFI partition space after copying: {efi_space_check.stdout}")
       
       # Create symlinks for GRUB - both in chroot and directly in filesystem
       log("Creating symlinks for GRUB...")
       symlink_pairs = [
           ('/boot/vmlinuz', f'/boot/vmlinuz-{kernel_version}'),
           ('/boot/initrd', f'/boot/initramfs-{kernel_version}.img'),
           ('/vmlinuz', f'/boot/vmlinuz-{kernel_version}'),
           ('/initrd', f'/boot/initramfs-{kernel_version}.img'),
           ('/boot/bzImage', f'/boot/vmlinuz-{kernel_version}'),
           ('/bzImage', f'/boot/vmlinuz-{kernel_version}'),
           ('/boot/kernel', f'/boot/vmlinuz-{kernel_version}'),
           ('/kernel', f'/boot/vmlinuz-{kernel_version}')
       ]
       
       # First create symlinks in the chroot environment
       for link, target in symlink_pairs:
           try:
               subprocess.run(['chroot', '/mnt/stage', 'ln', '-sf', target, link],
                             capture_output=True, check=True)
               log(f"Created symlink in chroot: {link} -> {target}")
           except subprocess.CalledProcessError as e:
               log(f"Failed to create symlink in chroot: {link} -> {target}: {e}")
       
       # Also create the symlinks directly in the filesystem
       for link, target in symlink_pairs:
           try:
               # Create the symlink directly in the filesystem
               full_link = f'/mnt/stage{link}'
               full_target = target  # Target is relative to the link location
               
               # Remove existing symlink or file if it exists
               if os.path.exists(full_link) or os.path.islink(full_link):
                   os.remove(full_link)
               
               # Create the symlink
               os.symlink(full_target, full_link)
               log(f"Created symlink in filesystem: {full_link} -> {full_target}")
               
               # For critical files in root, also create a hard copy
               if link in ['/vmlinuz', '/initrd']:
                   # Get the actual file that the symlink points to
                   actual_target = f'/mnt/stage{target}'
                   if os.path.exists(actual_target):
                       # Make a hard copy
                       subprocess.run(['cp', actual_target, full_link], check=True)
                       log(f"Created hard copy at {full_link} from {actual_target}")
                   else:
                       log(f"WARNING: Target file {actual_target} does not exist, cannot create hard copy")
           except Exception as e:
               log(f"Failed to create symlink in filesystem: {full_link} -> {full_target}: {e}")
       
       # Create a simplified GRUB configuration file
       log("Creating simplified GRUB configuration...")
       grub_config = f"""# GRUB configuration for Nutanix AHV
insmod part_gpt
insmod ext2
insmod search_fs_uuid
insmod search_label
insmod fat
insmod normal
insmod linux
insmod gzio

set default=0
set timeout=5
set timeout_style=menu
set gfxpayload=keep

# Enable interactive features for debugging
set pager=1
set check_signatures=no

# Use root partition
search --no-floppy --set=root --label=ROOT

# Boot entry - use absolute paths to ensure files are found
menuentry 'Nutanix AHV' --unrestricted --id nutanix {{
   echo 'Loading Linux kernel...'
   linux /vmlinuz root=LABEL=ROOT ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 quiet pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
   echo 'Loading initial ramdisk...'
   initrd /initrd
}}

# Fallback entry with full paths
menuentry 'Nutanix AHV (Fallback)' --unrestricted --id nutanix_fallback {{
   echo 'Loading Linux kernel (fallback)...'
   linux /boot/vmlinuz-{kernel_version} root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 quiet pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
   echo 'Loading initial ramdisk (fallback)...'
   initrd /boot/initramfs-{kernel_version}.img
}}

# Emergency entry with UUID
menuentry 'Nutanix AHV (Emergency)' --unrestricted --id nutanix_emergency {{
   echo 'Loading Linux kernel (emergency)...'
   linux /boot/vmlinuz-{kernel_version} root=LABEL=ROOT ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 quiet pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
   echo 'Loading initial ramdisk (emergency)...'
   initrd /boot/initramfs-{kernel_version}.img
}}

# Rescue script entry
menuentry 'Nutanix AHV (Rescue Script)' --unrestricted --id nutanix_rescue {{
   echo 'Running rescue script...'
   linux /boot/rescue.sh
}}
"""
       
       # Write GRUB configuration to all possible locations
       log("Writing GRUB configuration to multiple locations...")
       config_locations = [
           '/mnt/stage/boot/grub2/grub.cfg',
           '/mnt/stage/boot/efi/EFI/NUTANIX/grub.cfg',
           '/mnt/stage/boot/efi/EFI/BOOT/grub.cfg',
           '/mnt/stage/etc/grub2-efi.cfg',
           '/mnt/stage/etc/grub2.cfg',
           '/mnt/stage/boot/grub/grub.cfg',
           '/mnt/stage/grub/grub.cfg',
           '/mnt/stage/boot/efi/grub.cfg'
       ]
       
       for config_path in config_locations:
           os.makedirs(os.path.dirname(config_path), exist_ok=True)
           with open(config_path, 'w') as f:
               f.write(grub_config)
           log(f"Created GRUB configuration at {config_path}")
       
       # Create GRUB defaults file with longer timeout for debugging
       with open('/mnt/stage/etc/default/grub', 'w') as f:
           f.write("""GRUB_TIMEOUT=5
GRUB_TIMEOUT_STYLE=menu
GRUB_DISTRIBUTOR="Nutanix AHV"
GRUB_DEFAULT=0
GRUB_DISABLE_RECOVERY=false
GRUB_DISABLE_SUBMENU=false
GRUB_TERMINAL="console serial"
GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"
GRUB_CMDLINE_LINUX="root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic ip=dhcp rd.neednet=1 console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 debug pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal"
GRUB_PRELOAD_MODULES="part_gpt ext2 search_fs_uuid search_label fat normal linux gzio"
""".format(boot_disk=boot_disk))
       log("Created GRUB defaults file")
       
       # Try multiple GRUB installation methods
       log("Attempting multiple GRUB installation methods...")
       
       # Method 1: Standard grub2-install
       log("Method 1: Standard grub2-install...")
       result = subprocess.run(['chroot', '/mnt/stage', 'grub2-install', '--target=x86_64-efi',
                               '--efi-directory=/boot/efi', '--bootloader-id=NUTANIX',
                               '--boot-directory=/boot', f'{boot_device}'],
                               capture_output=True, text=True)
       
       if result.returncode == 0:
           log("Standard grub2-install succeeded")
       else:
           log(f"Standard grub2-install failed: {result.stderr}")
       
       # Method 2: Copy GRUB binaries directly
       log("Method 2: Copying GRUB binaries directly...")
       
       # Find all possible GRUB EFI binaries
       grub_binaries = []
       search_paths = [
           '/mnt/stage/boot/efi/EFI/NUTANIX/grubx64.efi',
           '/mnt/stage/usr/lib/grub/x86_64-efi/grubx64.efi',
           '/mnt/stage/usr/share/grub/grubx64.efi'
       ]
       
       # Also search the AHV ISO
       result = subprocess.run(['find', '/mnt/ahv', '-name', 'grubx64.efi'],
                             capture_output=True, text=True)
       if result.stdout.strip():
           search_paths.extend(result.stdout.strip().split('\n'))
       
       # Check which binaries exist
       for path in search_paths:
           if os.path.exists(path):
               grub_binaries.append(path)
               log(f"Found GRUB binary at {path}")
       
       # Copy all found binaries to standard locations
       if grub_binaries:
           for binary in grub_binaries:
               # Copy to BOOT directory
               subprocess.run(['cp', binary, '/mnt/stage/boot/efi/EFI/BOOT/BOOTX64.EFI'])
               # Copy to NUTANIX directory
               subprocess.run(['cp', binary, '/mnt/stage/boot/efi/EFI/NUTANIX/grubx64.efi'])
           log("Copied GRUB binaries to standard locations")
       else:
           log("No GRUB binaries found, attempting to extract from packages...")
           
           # Try to extract from RPM packages
           os.makedirs('/tmp/grub_extract', exist_ok=True)
           result = subprocess.run(['find', '/mnt/ahv', '-name', 'grub2-efi-x64*.rpm'],
                                 capture_output=True, text=True)
           
           if result.stdout.strip():
               grub_pkg = result.stdout.strip().split('\n')[0]
               log(f"Found GRUB package at {grub_pkg}")
               
               # Extract the package
               extract_result = subprocess.run(['rpm2cpio', grub_pkg, '|', 'cpio', '-idmv', '-D', '/tmp/grub_extract'],
                                             shell=True, capture_output=True, text=True)
               
               # Find the GRUB EFI binary in the extracted package
               find_result = subprocess.run(['find', '/tmp/grub_extract', '-name', 'grubx64.efi'],
                                         capture_output=True, text=True)
               
               if find_result.stdout.strip():
                   extracted_grub = find_result.stdout.strip().split('\n')[0]
                   log(f"Found extracted GRUB EFI binary at {extracted_grub}")
                   
                   # Copy to standard locations
                   subprocess.run(['cp', extracted_grub, '/mnt/stage/boot/efi/EFI/BOOT/BOOTX64.EFI'])
                   subprocess.run(['cp', extracted_grub, '/mnt/stage/boot/efi/EFI/NUTANIX/grubx64.efi'])
                   log("Copied extracted GRUB binary to standard locations")
       
       # Method 3: Create EFI stub
       log("Method 3: Creating EFI stub...")
       
       # Create a cmdline file with the kernel parameters
       with open('/mnt/stage/tmp/cmdline.txt', 'w') as f:
           f.write(f"root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 quiet pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal")
       
       # Check if objcopy is available
       result = subprocess.run(['chroot', '/mnt/stage', 'which', 'objcopy'],
                             capture_output=True, text=True)
       
       if result.returncode == 0:
           # Create an EFI stub
           result = subprocess.run(['chroot', '/mnt/stage', 'objcopy',
                                  '--add-section', f'.linux={kernel_path}',
                                  '--add-section', f'.initrd={initramfs_path}',
                                  '--add-section', '.cmdline=/tmp/cmdline.txt',
                                  '--change-section-vma', '.linux=0x2000000',
                                  '--change-section-vma', '.initrd=0x3000000',
                                  '--change-section-vma', '.cmdline=0x30000',
                                  '/usr/lib/systemd/boot/efi/linuxx64.efi.stub',
                                  '/boot/efi/EFI/BOOT/BOOTX64.EFI.stub'],
                                 capture_output=True, text=True)
           
           if result.returncode == 0:
               log("Successfully created EFI stub")
               # Copy it as a fallback
               subprocess.run(['cp', '/mnt/stage/boot/efi/EFI/BOOT/BOOTX64.EFI.stub',
                             '/mnt/stage/boot/efi/EFI/BOOT/BOOTX64.EFI.backup'])
           else:
               log(f"Failed to create EFI stub: {result.stderr}")
       
       # Method 4: Generate GRUB configuration with grub2-mkconfig
       log("Method 4: Generating GRUB configuration with grub2-mkconfig...")
       
       # Mount virtual filesystems in chroot for grub2-mkconfig
       log("Mounting virtual filesystems for chroot...")
       for fs in ['/dev', '/proc', '/sys']:
           mount_path = f'/mnt/stage{fs}'
           try:
               # Check if already mounted
               mount_check = subprocess.run(['mount', '|', 'grep', mount_path],
                                         shell=True, capture_output=True, text=True)
               if mount_check.returncode != 0:
                   # Not mounted, so mount it
                   subprocess.run(['mount', '--bind', fs, mount_path], check=False)
                   log(f"Mounted {fs} to {mount_path}")
           except Exception as e:
               log(f"Warning: Failed to mount {fs}: {e}")
       
       # Try to generate GRUB config
       try:
           result = subprocess.run(['chroot', '/mnt/stage', 'grub2-mkconfig', '-o', '/boot/grub2/grub.cfg'],
                                 capture_output=True, text=True)
           
           if result.returncode == 0:
               log("Successfully generated GRUB configuration with grub2-mkconfig")
               # Copy the generated config to other locations
               subprocess.run(['cp', '/mnt/stage/boot/grub2/grub.cfg', '/mnt/stage/boot/efi/EFI/NUTANIX/grub.cfg'])
               subprocess.run(['cp', '/mnt/stage/boot/grub2/grub.cfg', '/mnt/stage/boot/efi/EFI/BOOT/grub.cfg'])
           else:
               log(f"Failed to generate GRUB configuration with grub2-mkconfig: {result.stderr}")
               
               # Fallback: Create a basic GRUB config manually
               log("Creating basic GRUB config manually as fallback...")
               basic_grub_cfg = f"""set timeout=5
set default=0

menuentry "Nutanix AHV" {{
   search --no-floppy --label ROOT --set=root
   linux /vmlinuz root=LABEL=ROOT ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
   initrd /initrd
}}

menuentry "Nutanix AHV (rescue mode)" {{
   search --no-floppy --label ROOT --set=root
   linux /vmlinuz root=LABEL=ROOT ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 single pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
   initrd /initrd
}}
"""
               with open('/mnt/stage/boot/grub2/grub.cfg', 'w') as f:
                   f.write(basic_grub_cfg)
               # Copy to other locations
               subprocess.run(['cp', '/mnt/stage/boot/grub2/grub.cfg', '/mnt/stage/boot/efi/EFI/NUTANIX/grub.cfg'])
               subprocess.run(['cp', '/mnt/stage/boot/grub2/grub.cfg', '/mnt/stage/boot/efi/EFI/BOOT/grub.cfg'])
               log("Created basic GRUB config manually")
       except Exception as e:
           log(f"Error during GRUB config generation: {e}")
           # Create a basic GRUB config manually as a last resort
           log("Creating basic GRUB config manually as last resort...")
           basic_grub_cfg = f"""set timeout=5
set default=0

menuentry "Nutanix AHV" {{
   search --no-floppy --label ROOT --set=root
   linux /vmlinuz root=LABEL=ROOT ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
   initrd /initrd
}}
"""
           try:
               with open('/mnt/stage/boot/grub2/grub.cfg', 'w') as f:
                   f.write(basic_grub_cfg)
               # Copy to other locations
               subprocess.run(['cp', '/mnt/stage/boot/grub2/grub.cfg', '/mnt/stage/boot/efi/EFI/NUTANIX/grub.cfg'])
               subprocess.run(['cp', '/mnt/stage/boot/grub2/grub.cfg', '/mnt/stage/boot/efi/EFI/BOOT/grub.cfg'])
               log("Created basic GRUB config manually as last resort")
           except Exception as e2:
               log(f"Failed to create basic GRUB config: {e2}")
       
       # Unmount virtual filesystems
       log("Unmounting virtual filesystems...")
       for fs in ['/sys', '/proc', '/dev']:  # Unmount in reverse order
           mount_path = f'/mnt/stage{fs}'
           try:
               subprocess.run(['umount', mount_path], check=False)
               log(f"Unmounted {mount_path}")
           except Exception as e:
               log(f"Warning: Failed to unmount {mount_path}: {e}")
       
       # Create EFI NVRAM entries
       log("Creating EFI NVRAM entries...")
       
       # Check if EFI variables are supported
       efi_vars_supported = False
       try:
           # Check if efivarfs is mounted
           result = subprocess.run(['mount', '|', 'grep', 'efivarfs'],
                                 shell=True, capture_output=True, text=True)
           if result.returncode == 0:
               log("EFI variables are supported (efivarfs is mounted)")
               efi_vars_supported = True
           else:
               # Try to mount efivarfs
               log("Attempting to mount efivarfs...")
               mount_result = subprocess.run(['mount', '-t', 'efivarfs', 'efivarfs', '/sys/firmware/efi/efivars'],
                                          check=False, capture_output=True, text=True)
               if mount_result.returncode == 0:
                   log("Successfully mounted efivarfs")
                   efi_vars_supported = True
               else:
                   log(f"Failed to mount efivarfs: {mount_result.stderr}")
                   
           # Additional check - see if efibootmgr works
           if efi_vars_supported:
               test_result = subprocess.run(['chroot', '/mnt/stage', 'efibootmgr', '-v'],
                                         capture_output=True, text=True)
               if test_result.returncode != 0:
                   log(f"efibootmgr test failed: {test_result.stderr}")
                   efi_vars_supported = False
               else:
                   log("efibootmgr test successful")
       except Exception as e:
           log(f"Error checking EFI variables support: {e}")
           efi_vars_supported = False
       
       if efi_vars_supported:
           try:
               # First, clear any existing entries
               clear_result = subprocess.run(['chroot', '/mnt/stage', 'efibootmgr', '--delete-all'],
                                          capture_output=True, text=True)
               if clear_result.returncode == 0:
                   log("Successfully cleared existing EFI entries")
               else:
                   log(f"Warning: Failed to clear existing EFI entries: {clear_result.stderr}")
                   # Continue anyway - this is not critical
               
               # Create new entry for NUTANIX
               result = subprocess.run(['chroot', '/mnt/stage', 'efibootmgr', '--create',
                                      '--disk', f'{boot_device}', '--part', '1',
                                      '--label', 'Nutanix AHV', '--loader', '/EFI/NUTANIX/grubx64.efi'],
                                      capture_output=True, text=True)
               
               if result.returncode == 0:
                   log("Successfully created EFI NVRAM entry for NUTANIX")
                   nutanix_entry_created = True
               else:
                   log(f"Failed to create EFI NVRAM entry for NUTANIX: {result.stderr}")
                   nutanix_entry_created = False
               
               # Create fallback entry for BOOT
               result = subprocess.run(['chroot', '/mnt/stage', 'efibootmgr', '--create',
                                      '--disk', f'{boot_device}', '--part', '1',
                                      '--label', 'Fallback Boot', '--loader', '/EFI/BOOT/BOOTX64.EFI'],
                                      capture_output=True, text=True)
               
               if result.returncode == 0:
                   log("Successfully created EFI NVRAM entry for fallback boot")
                   fallback_entry_created = True
               else:
                   log(f"Failed to create EFI NVRAM entry for fallback boot: {result.stderr}")
                   fallback_entry_created = False
               
               # Set boot order only if at least one entry was created
               if nutanix_entry_created or fallback_entry_created:
                   # Get current boot entries
                   list_result = subprocess.run(['chroot', '/mnt/stage', 'efibootmgr'],
                                             capture_output=True, text=True)
                   
                   if list_result.returncode == 0:
                       # Parse the output to find the boot entries we created
                       boot_entries = []
                       for line in list_result.stdout.splitlines():
                           if "Nutanix AHV" in line or "Fallback Boot" in line:
                               match = re.search(r'Boot([0-9A-F]{4})', line)
                               if match:
                                   boot_entries.append(match.group(1))
                       
                       if boot_entries:
                           # Set boot order with our entries first
                           boot_order = ','.join(boot_entries)
                           result = subprocess.run(['chroot', '/mnt/stage', 'efibootmgr', '--bootorder', boot_order],
                                                 capture_output=True, text=True)
                           
                           if result.returncode == 0:
                               log(f"Successfully set EFI boot order to {boot_order}")
                           else:
                               log(f"Failed to set EFI boot order: {result.stderr}")
                       else:
                           log("No Nutanix boot entries found in efibootmgr output")
                   else:
                       log(f"Failed to list EFI boot entries: {list_result.stderr}")
           except Exception as e:
               log(f"Error during EFI boot entry creation: {e}")
       else:
           log("EFI variables are not supported - skipping efibootmgr commands")
           log("Relying on fallback boot methods: BOOTX64.EFI and startup.nsh")
       
       # Create a startup.nsh script for emergency boot (only in the root of EFI partition)
       log("Creating startup.nsh script for emergency boot...")
       try:
           with open('/mnt/stage/boot/efi/startup.nsh', 'w') as f:
               f.write(f"""@echo -off
echo Loading Nutanix AHV...
echo Attempting to boot from EFI/BOOT...
\\EFI\\BOOT\\BOOTX64.EFI
echo If that failed, trying EFI/NUTANIX...
\\EFI\\NUTANIX\\grubx64.efi
echo If that failed, trying direct kernel boot...
echo Loading kernel: vmlinuz
echo Loading initrd: initrd
echo Boot parameters: root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic ip=dhcp rd.neednet=1 console=tty0 console=ttyS0,115200n8 debug pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal
\\vmlinuz root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic ip=dhcp rd.neednet=1 console=tty0 console=ttyS0,115200n8 debug pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal initrd=\\initrd
echo If all boot methods failed, try running the rescue script...
\\boot\\rescue.sh
""")
           log("Created startup.nsh script at /mnt/stage/boot/efi/startup.nsh")
       except Exception as e:
           log(f"Failed to create startup.nsh script: {e}")
       
       # Create a rescue script that can be used to manually boot the system
       log("Creating rescue script...")
       rescue_script = f"""#!/bin/sh
# Rescue script for Nutanix AHV boot
echo "Nutanix AHV Rescue Boot Script"
echo "Attempting to find and boot the kernel..."

# List all available kernels and initrds
echo "Available kernels:"
find / -name "vmlinuz*" -o -name "bzImage*" 2>/dev/null | sort
echo ""
echo "Available initrds:"
find / -name "initramfs*" -o -name "initrd*" 2>/dev/null | sort
echo ""

# Try different kernel paths
for KERNEL_PATH in /boot/vmlinuz-{kernel_version} /vmlinuz /boot/bzImage /bzImage /boot/vmlinuz-*.x86_64 /boot/vmlinuz-*; do
 if [ -f "$KERNEL_PATH" ]; then
   echo "Found kernel at $KERNEL_PATH"
   
   # Try different initrd paths
   for INITRD_PATH in /boot/initramfs-{kernel_version}.img /initrd /boot/initramfs-*.img; do
     if [ -f "$INITRD_PATH" ]; then
       echo "Found initrd at $INITRD_PATH"
       
       # Try different root specifications
       for ROOT_SPEC in "root=/dev/{boot_disk}p2" "root=LABEL=ROOT" "root=UUID=$(blkid -s UUID -o value /dev/{boot_disk}p2 2>/dev/null || echo 'none')"; do
         echo "Attempting boot with $ROOT_SPEC"
         echo "kexec -l $KERNEL_PATH --initrd=$INITRD_PATH --command-line=\"$ROOT_SPEC ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic ip=dhcp rd.neednet=1 console=tty0 console=ttyS0,115200n8 debug selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal\""
         
         kexec -l $KERNEL_PATH --initrd=$INITRD_PATH --command-line="$ROOT_SPEC ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic ip=dhcp rd.neednet=1 console=tty0 console=ttyS0,115200n8 debug selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal" 2>/dev/null
         
         if [ $? -eq 0 ]; then
           echo "kexec load successful, executing kernel..."
           echo "Press Ctrl+C within 5 seconds to abort..."
           sleep 5
           kexec -e
           # If we get here, kexec failed
           echo "kexec execution failed, trying next option"
         else
           echo "kexec load failed, trying next option"
         fi
       done
     fi
   done
 fi
done

# If all automatic attempts fail, provide manual instructions
echo "All automatic boot attempts failed!"
echo ""
echo "Manual boot instructions:"
echo "1. Find a valid kernel:"
echo "   ls -la /boot/vmlinuz*"
echo ""
echo "2. Find a valid initrd:"
echo "   ls -la /boot/initramfs*"
echo ""
echo "3. Try manual boot with kexec:"
echo "   kexec -l /path/to/kernel --initrd=/path/to/initrd --command-line=\"root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal\""
echo "   kexec -e"
echo ""
echo "4. Or try manual boot from GRUB command line:"
echo "   linux /boot/vmlinuz-{kernel_version} root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0 nvme.io_timeout=4294967295 modprobe.blacklist=mlx4_core,mlx4_en,mlx4_ib,ionic console=tty0 console=ttyS0,115200n8 selinux=0 enforcing=0 pci=realloc=on,nocrs,noaer,assign-busses,resourcehog,hpiosize=0x10000,hpmemsize=0x20000000,hpprefmemsize=0x20000000 pcie_aspm=off iommu=pt nomodeset vga=normal"
echo "   initrd /boot/initramfs-{kernel_version}.img"
echo "   boot"
echo ""
echo "Dropping to shell for manual recovery"
exec /bin/sh
"""
       
       with open('/mnt/stage/boot/rescue.sh', 'w') as f:
           f.write(rescue_script)
       subprocess.run(['chmod', '+x', '/mnt/stage/boot/rescue.sh'])
       log("Created rescue script at /boot/rescue.sh")
       
       # Verify kernel installation
       log("Verifying kernel installation...")
       kernel_found = False
       for kernel_path in [f'/mnt/stage/boot/vmlinuz-{kernel_version}', '/mnt/stage/vmlinuz', '/mnt/stage/boot/bzImage']:
           if os.path.exists(kernel_path):
               kernel_size = os.path.getsize(kernel_path)
               log(f"Found kernel at {kernel_path} (size: {kernel_size} bytes)")
               kernel_found = True
               
               # If kernel is too small, it might be corrupted or a symlink to a non-existent file
               if kernel_size < 1000000:  # Typical kernel is several MB
                   log(f"WARNING: Kernel file at {kernel_path} is suspiciously small ({kernel_size} bytes)")
                   
                   # Try to find a valid kernel and copy it
                   result = subprocess.run(['find', '/mnt/ahv', '-name', 'vmlinuz*', '-size', '+5M'],
                                         capture_output=True, text=True)
                   if result.stdout.strip():
                       valid_kernel = result.stdout.strip().split('\n')[0]
                       log(f"Found valid kernel in installation media: {valid_kernel}")
                       subprocess.run(['cp', valid_kernel, kernel_path])
                       log(f"Copied valid kernel to {kernel_path}")
                   else:
                       log("Could not find a valid kernel in installation media")
       
       if not kernel_found:
           log("WARNING: No kernel files found! System may not boot properly.")
           
           # Last resort - try to extract kernel from RPM packages
           log("Attempting to extract kernel from RPM packages...")
           result = subprocess.run(['find', '/mnt/ahv', '-name', 'kernel*.rpm'],
                                 capture_output=True, text=True)
           if result.stdout.strip():
               kernel_rpm = result.stdout.strip().split('\n')[0]
               log(f"Found kernel RPM at {kernel_rpm}")
               
               # Extract the package
               os.makedirs('/tmp/kernel_extract', exist_ok=True)
               extract_result = subprocess.run(['rpm2cpio', kernel_rpm, '|', 'cpio', '-idmv', '-D', '/tmp/kernel_extract'],
                                             shell=True, capture_output=True, text=True)
               
               # Find the kernel in the extracted package
               find_result = subprocess.run(['find', '/tmp/kernel_extract', '-name', 'vmlinuz*'],
                                         capture_output=True, text=True)
               
               if find_result.stdout.strip():
                   extracted_kernel = find_result.stdout.strip().split('\n')[0]
                   log(f"Found extracted kernel at {extracted_kernel}")
                   
                   # Copy to standard locations
                   subprocess.run(['cp', extracted_kernel, f'/mnt/stage/boot/vmlinuz-{kernel_version}'])
                   subprocess.run(['cp', extracted_kernel, '/mnt/stage/vmlinuz'])
                   log("Copied extracted kernel to standard locations")
       
       # Cleanup - unmount everything
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
    
    # Set up Python path with correct locations
    sys.path.insert(0, '/phoenix')
    sys.path.insert(0, '/usr/lib/python3.9')
    
    # Mock /proc/cmdline with config values
    def mock_cmdline():
        node_config = config['node']
        return f"block_id={node_config['block_id']} node_position={node_config['node_position']} node_serial={node_config['node_serial']} cluster_id={node_config['cluster_id']} model={config['hardware']['model']} hyp_type=kvm installer_path=/tmp/nutanix_installer_package.tar.gz"
    
    original_open = open
    def patched_open(filename, *args, **kwargs):
        if filename == '/proc/cmdline':
            from io import StringIO
            return StringIO(mock_cmdline())
        return original_open(filename, *args, **kwargs)
    
    import builtins
    builtins.open = patched_open
    
    log("Environment setup complete")

def generate_cluster_id():
    # cluster ID generation spec (16 bits random + MAC addr)
    log("Generating cluster_id")
    randomizer_hex = hex(randint(1, int('7FFF', 16)))[2:] # Remove '0x' prefix
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
    cluster_id = int(randomizer_hex + mac_addrs[0].replace(':', ''), 16)
    return cluster_id

def create_installation_params(config):
    """Create Nutanix installation parameters from config"""
    log("Creating installation parameters from configuration...")
    
    try:
        import param_list
        
        params = param_list.ParamList()
        
        # Node configuration - create if not exists
        if 'node' not in config:
            log("Node section not found in config, creating default values")
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
        # Ensure these are lists, even if they're strings in the config
        if isinstance(hw_config['cvm_data_disks'], str):
            params.ce_cvm_data_disks = [hw_config['cvm_data_disks']]
        else:
            params.ce_cvm_data_disks = hw_config['cvm_data_disks']
            
        if isinstance(hw_config['cvm_boot_disks'], str):
            params.ce_cvm_boot_disks = [hw_config['cvm_boot_disks']]
        else:
            params.ce_cvm_boot_disks = hw_config['cvm_boot_disks']
            
        params.ce_hyp_boot_disk = hw_config['hypervisor_boot_disk']
        
        # Ensure cvm_data_disks is a list before concatenation
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
        log(f"Error: Config server URL not found. Cannot send status update.", send_to_api=False)
        return
    
    api_url = f"{config_server}/api/installation/status"
    payload = {
        "management_ip": management_ip,
        "phase": phase,
        "message": message
    }
    
    log(f"Sending status update: Phase {phase}, Message: '{message}' to {api_url}", send_to_api=False, verbose=True)
    
    # Convert payload to JSON and encode
    data = json.dumps(payload).encode('utf-8')
    
    try:
        # Create request
        log(f"Creating request to {api_url}", send_to_api=False, verbose=True)
        req = urllib.request.Request(api_url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        
        # Send request with timeout
        log("Sending request...", send_to_api=False, verbose=True)
        response = urllib.request.urlopen(req, timeout=10)
        status_code = response.getcode()
        
        # Check for success (2xx status codes)
        if 200 <= status_code < 300:
            log(f"Status update sent successfully. Response: {status_code}", send_to_api=False, verbose=True)
        else:
            log(f"Status update failed with HTTP {status_code}", send_to_api=False)
            
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        log(f"Error sending status update to {api_url}: {e}", send_to_api=False)
    except socket.timeout:
        log(f"Timeout sending status update to {api_url}", send_to_api=False)
    except Exception as e:
        log(f"An unexpected error occurred while sending status update: {e}", send_to_api=False)
        import traceback
        log(f"Traceback: {traceback.format_exc()}", send_to_api=False)
        import traceback
        log(f"Traceback: {traceback.format_exc()}")

def wipe_nvmes():
    drives = [d for d in glob.glob('/dev/nvme*') if re.match(r'.*/nvme\d+n\d+$', d)]
    for drive in sorted(drives):
        print(f"Wiping {drive}")
        subprocess.run(['wipefs', '-a', drive], check=True)
    print(f"Wiped {len(drives)} drives")

def run_with_timeout(cmd, timeout=60):
    """Run a command with a timeout"""
    try:
        log(f"Running command with {timeout}s timeout: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result
    except subprocess.TimeoutExpired:
        log(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        return None

def verify_installation(config):
    """
    Verify that the installation has completed successfully by checking for the presence
    of all required boot files and configurations.
    
    Args:
        config: The node configuration dictionary
        
    Returns:
        True if verification passes, False otherwise
    """
    log("Verifying installation...")
    
    # Get boot disk from config
    boot_disk = config['hardware']['boot_disk']
    boot_device = f"/dev/{boot_disk}"
    
    # Check if the hypervisor partition is mounted
    if not os.path.ismount('/mnt/stage'):
        log("Mounting hypervisor partition for verification...")
        result = subprocess.run(['mount', f'{boot_device}p2', '/mnt/stage'])
        if result.returncode != 0:
            log("Failed to mount hypervisor partition for verification")
            return False
    
    # Check if the EFI partition is mounted
    if not os.path.ismount('/mnt/stage/boot/efi'):
        log("Mounting EFI partition for verification...")
        result = subprocess.run(['mount', f'{boot_device}p1', '/mnt/stage/boot/efi'])
        if result.returncode != 0:
            log("Failed to mount EFI partition for verification")
            return False
    
    # Define critical files that must exist
    # Define essential files that must exist for a successful boot
    critical_files = [
        # Kernel files (at least one must exist)
        '/mnt/stage/boot/vmlinuz',
        
        # Initramfs files (at least one must exist)
        '/mnt/stage/boot/initrd',
        
        # GRUB configuration files (at least one must exist)
        '/mnt/stage/boot/grub2/grub.cfg',
        
        # EFI files (essential for EFI boot)
        '/mnt/stage/boot/efi/EFI/BOOT/BOOTX64.EFI',
        
        # Startup script (only one needed at the root of EFI)
        '/mnt/stage/boot/efi/startup.nsh',
        
        # Rescue script
        '/mnt/stage/boot/rescue.sh'
    ]
    
    # Check for existence of critical files - EACH category must have at least one file
    
    # Check kernel files - need at least one
    kernel_files = [
        '/mnt/stage/boot/vmlinuz',
        '/mnt/stage/vmlinuz',
        '/mnt/stage/boot/vmlinuz-*',
        '/mnt/stage/boot/bzImage',
        '/mnt/stage/boot/bzImage-*'
    ]
    
    # Expand wildcards for kernel files
    expanded_kernel_files = []
    for pattern in kernel_files:
        if '*' in pattern:
            expanded_kernel_files.extend(glob.glob(pattern))
        else:
            expanded_kernel_files.append(pattern)
    
    has_kernel = any(os.path.exists(f) for f in expanded_kernel_files)
    if not has_kernel:
        log("Verification FAILED: No kernel files found in any location")
        log("The system will not be able to boot without a kernel")
        return False
    else:
        log("Kernel files verified")
    
    # Check initramfs files - need at least one
    initramfs_files = [
        '/mnt/stage/boot/initrd',
        '/mnt/stage/initrd',
        '/mnt/stage/boot/initramfs-*.img',
        '/mnt/stage/boot/initrd.img-*'
    ]
    
    # Expand wildcards for initramfs files
    expanded_initramfs_files = []
    for pattern in initramfs_files:
        if '*' in pattern:
            expanded_initramfs_files.extend(glob.glob(pattern))
        else:
            expanded_initramfs_files.append(pattern)
    
    has_initramfs = any(os.path.exists(f) for f in expanded_initramfs_files)
    if not has_initramfs:
        log("Verification FAILED: No initramfs files found in any location")
        log("The system will not be able to boot without an initramfs")
        return False
    else:
        log("Initramfs files verified")
    
    # Check GRUB config files - need at least one
    grub_config_files = [
        '/mnt/stage/boot/grub2/grub.cfg',
        '/mnt/stage/boot/grub/grub.conf',
        '/mnt/stage/boot/efi/EFI/BOOT/grub.cfg',
        '/mnt/stage/boot/efi/EFI/NUTANIX/grub.cfg'
    ]
    
    has_grub_config = any(os.path.exists(f) for f in grub_config_files)
    if not has_grub_config:
        log("Verification FAILED: No GRUB configuration files found")
        log("The system will not be able to boot without a GRUB configuration")
        return False
    else:
        log("GRUB configuration files verified")
    
    # Check EFI boot files - need at least one
    efi_boot_files = [
        '/mnt/stage/boot/efi/EFI/BOOT/BOOTX64.EFI',
        '/mnt/stage/boot/efi/EFI/NUTANIX/grubx64.efi'
    ]
    
    has_efi_boot = any(os.path.exists(f) for f in efi_boot_files)
    if not has_efi_boot:
        log("Verification FAILED: No EFI boot files found")
        log("The system will not be able to boot without an EFI bootloader")
        return False
    else:
        log("EFI boot files verified")
    
    # Check for existence of additional essential files
    essential_files = [
        # Startup script for EFI shell fallback
        '/mnt/stage/boot/efi/startup.nsh',
        # Rescue script for manual recovery
        '/mnt/stage/boot/rescue.sh'
    ]
    
    missing_files = []
    for file_path in essential_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
            log(f"Missing essential file: {file_path}")
    
    if missing_files:
        log(f"Verification FAILED: {len(missing_files)} essential files are missing")
        log("These files are required for fallback boot methods")
        return False
    
    # Check for EFI directory structure
    efi_dirs = [
        '/mnt/stage/boot/efi/EFI',
        '/mnt/stage/boot/efi/EFI/BOOT',
        '/mnt/stage/boot/efi/EFI/NUTANIX'
    ]
    
    missing_dirs = []
    for dir_path in efi_dirs:
        if not os.path.isdir(dir_path):
            missing_dirs.append(dir_path)
            log(f"Missing critical directory: {dir_path}")
    
    if missing_dirs:
        log(f"Verification failed: {len(missing_dirs)} critical directories are missing")
        return False
    
    # Check for ROOT label on hypervisor partition
    result = subprocess.run(['blkid', f'{boot_device}p2'], capture_output=True, text=True)
    if 'LABEL="ROOT"' not in result.stdout:
        log("Verification failed: ROOT label not found on hypervisor partition")
        return False
    
    # Check for symlinks
    symlinks = [
        ('/mnt/stage/boot/vmlinuz', '/boot/vmlinuz-'),
        ('/mnt/stage/boot/initrd', '/boot/initramfs-'),
        ('/mnt/stage/vmlinuz', '/boot/vmlinuz-'),
        ('/mnt/stage/initrd', '/boot/initramfs-')
    ]
    
    broken_symlinks = []
    for link, target_prefix in symlinks:
        if os.path.islink(link):
            target = os.readlink(link)
            if not target.startswith(target_prefix):
                broken_symlinks.append(link)
                log(f"Broken symlink: {link} -> {target}")
        else:
            broken_symlinks.append(link)
            log(f"Missing symlink: {link}")
    
    if broken_symlinks:
        log(f"Verification failed: {len(broken_symlinks)} symlinks are broken or missing")
        return False
    
    # All checks passed
    log("Verification successful: All required boot files and configurations are present")
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
            log("This may indicate that the Python environment is not properly set up.")
            log("Check if the Nutanix installer package was correctly extracted.")
            drop_to_shell("Failed to import Nutanix installation modules")
        
        # Patch shell commands to protect partitions
        log("Patching shell commands to protect partitions...")
        original_shell_cmd = shell.shell_cmd
        
        def protected_shell_cmd(cmd_list, *args, **kwargs):
            cmd_str = ' '.join(cmd_list) if isinstance(cmd_list, list) else str(cmd_list)
            if 'wipefs' in cmd_str and params.boot_disk in cmd_str:
                log(f'BLOCKED: {cmd_str}')
                return '', ''
            log(f'Executing: {cmd_str}')
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
        except ImportError as e:
            log(f"Warning: Could not bypass hardware detection: {e}")
            log("This may cause issues with hardware compatibility checks.")
        
        # Bypass hardware detection functions
        def bypass_populate_host_boot_disk_param(param_list):
            log('Bypassing host boot disk parameter population')
            pass
        sysUtil.populate_host_boot_disk_param = bypass_populate_host_boot_disk_param
        
        # Log installation summary
        log("Installation Summary:")
        log(f"  Node:          {config['node']['node_serial']}")
        log(f"  Hypervisor:    KVM on {params.ce_hyp_boot_disk}")
        log(f"  Storage:       {len(params.ce_cvm_data_disks)} data drives")
        log(f"  Management IP: {config['network'].get('management_ip', 'DHCP')}")
        log(f"  CVM:           {params.svm_gb_ram}GB RAM, {params.svm_num_vcpus} vCPUs")
        log("CVM Network Summary:")
        log(f"  IP:            {params.cvm_interfaces[0]['ip']}")
        log(f"  Netmask:       {params.cvm_interfaces[0]['netmask']}")
        log(f"  Gateway:       {params.cvm_interfaces[0]['gateway']}")
        log(f"  DNS:           {params.dns_ip}")

        # Start installation
        log("Starting installation process...")
        try:
            # Create the svm_installer directory if it doesn't exist
            log("Creating /mnt/svm_installer directory...")
            os.makedirs('/mnt/svm_installer', exist_ok=True)
            
            log("Calling imagingUtil.image_node...")
            try:
                imagingUtil.image_node(params)
                log("imagingUtil.image_node completed successfully")
            except Exception as e:
                # Check if the error is about unmounting /tmp/svm_install_chroot/dev
                error_str = str(e)
                if "umount /tmp/svm_install_chroot/dev" in error_str and "target is busy" in error_str:
                    log("Warning: Could not unmount /tmp/svm_install_chroot/dev, but this is not critical")
                    log("Continuing with installation...")
                    # Force unmount the directory
                    try:
                        log("Attempting to force unmount /tmp/svm_install_chroot/dev...")
                        subprocess.run(['umount', '-f', '/tmp/svm_install_chroot/dev'], check=False)
                    except:
                        pass
                else:
                    # Re-raise the exception if it's not the unmount error
                    raise
        except Exception as e:
            log(f"Error during image_node: {e}")
            import traceback
            log(f"Traceback: {traceback.format_exc()}")
            return False
        
        log("Installation completed successfully!")
        return True
        
    except Exception as e:
        log(f"Installation error: {e}")
        import traceback
        log(f"Traceback: {traceback.format_exc()}")
        return False

def main():
    """Main installation function"""
    global management_ip, config_server # Ensure globals are accessible
    log("=== Nutanix CE VPC Bare Metal Server Installation ===")
    log("Platform: IBM Cloud VPC with Ionic Driver")
    
    # Phase 1: Initialization
    management_ip = get_management_ip()
    
    # Get config server URL once and store it in the global variable
    # URL cleaning is now done inside get_config_server_from_cmdline()
    config_server = get_config_server_from_cmdline()
    
    # Validate config_server
    if not config_server:
        drop_to_shell("Could not determine config server URL from command line")
    
    # Validate management_ip
    if not management_ip:
        drop_to_shell("Could not determine management IP address")
    
    log(f"Initialization complete. Management IP: {management_ip}, Config Server: {config_server}")
    log("Initialization complete", phase=1)

    # Phase 2: Download Node Configuration
    log("Downloading node configuration", phase=2)
    config = download_node_config(config_server, management_ip)
    if not config:
        drop_to_shell("Unable to download node configuration from server")
    
    # Phase 3: Validate Configuration
    log("Validating configuration", phase=3)
    if not validate_config(config):
        drop_to_shell("Configuration validation failed - missing required parameters")
    
    # Phase 4: Download Packages
    log("Downloading installation packages", phase=4)
    if not download_packages(config_server):
        drop_to_shell("Failed to download required installation packages")
    
    # Phase 5: Install Hypervisor
    log("Installing AHV hypervisor", phase=5)
    if not install_hypervisor(config):
        drop_to_shell("AHV hypervisor installation failed")
    
    # Setup environment (not a distinct phase for status reporting)
    setup_environment(config)
    
    # Add /phoenix to the Python path to use the real modules
    log("Adding /phoenix to Python path...")
    phoenix_dir = '/phoenix'
    if phoenix_dir not in sys.path:
        sys.path.insert(0, phoenix_dir)
    
    # Also add Python site-packages directories
    site_packages_paths = [
        '/usr/lib/python3.9/site-packages',
        '/usr/lib/python3.6/site-packages'  # Contains the six module
    ]
    
    for site_packages in site_packages_paths:
        if site_packages not in sys.path:
            sys.path.insert(0, site_packages)
    
    # Create mock hardware_inventory module as fallback
    try:
        import hardware_inventory
        log("Found hardware_inventory module")
    except ImportError:
        log("Creating mock hardware_inventory module...")
        import types
        
        # Create the hardware_inventory module
        hardware_inventory = types.ModuleType('hardware_inventory')
        sys.modules['hardware_inventory'] = hardware_inventory
        
        # Create the disk_info submodule
        disk_info = types.ModuleType('hardware_inventory.disk_info')
        
        # Create a mock disk class
        class MockDisk:
            def __init__(self, dev, model="Generic SSD", size=100, is_ssd=True):
                self.dev = dev
                self.model = model
                self.size = size
                self.isSSD = is_ssd
            
            def is_virtual_disk(self):
                return False
        
        # Add required functions to disk_info
        def mock_collect_disk_info(disk_list_filter=None, skip_part_info=True):
            result = {}
            # Add boot disk
            boot_disk = config['hardware']['boot_disk']
            result[boot_disk] = MockDisk(boot_disk, "Boot SSD", 200)
            
            # Add data disks
            for disk in config['hardware']['cvm_data_disks']:
                result[disk] = MockDisk(disk, "Data SSD", 500)
                
            return result
        
        def mock_list_hyp_boot_disks():
            return [config['hardware']['boot_disk']]
            
        # Add function to list NVMe disks
        def mock_list_nvme_disks():
            return [disk for disk in config['hardware']['cvm_data_disks'] if 'nvme' in disk]
        
        # Assign the functions to the module
        disk_info.collect_disk_info = mock_collect_disk_info
        disk_info.list_hyp_boot_disks = mock_list_hyp_boot_disks
        disk_info.list_nvme_disks = mock_list_nvme_disks
        
        # Register the disk_info submodule
        sys.modules['hardware_inventory.disk_info'] = disk_info
        hardware_inventory.disk_info = disk_info
        
        # Create the pci_util submodule
        pci_util = types.ModuleType('hardware_inventory.pci_util')
        
        # Add required functions to pci_util
        def mock_pci_search(vendor_id=None, device_id=None, subsystem_vendor_id=None,
                           subsystem_device_id=None, class_id=None, subclass_id=None,
                           prog_if=None, bus=None, slot=None, function=None):
            return []
            
        # Add parse_lspci function
        def mock_parse_lspci(text, arch="x86"):
            """
            Parses output of "lspci -v -nn".
            
            Returns:
                A list of PciDevice objects
            """
            # For our mock implementation, return an empty list
            return []
        
        # Add more required functions to pci_util
        def mock_list_block_devices_by_controllers(pci_device_search_list=None):
            # Use the config parameters to create a more accurate mock
            # This mimics the behavior of collect_disk_info() in the real implementation
            disk_info = {}
            for disk in config['hardware']['cvm_data_disks']:
                disk_info[disk] = {
                    'model': config['hardware'].get('disk_model', 'NVMe Drive'),
                    'size': config['hardware'].get('boot_disk_size_gb', 100) * 1024 * 1024 * 1024
                }
            return disk_info
            
        def mock_list_nvme_devices(exclude_devs=None):
            # Create a list of mock PciDevice objects for NVMe devices
            exclude_devs = exclude_devs or []
            nvme_devs = []
            
            # Create a PciDevice class similar to the one in the real implementation
            class MockPciDevice:
                def __init__(self, bus_addr, vendor, device):
                    self.bus = bus_addr
                    self.vendor = vendor
                    self.device = device
                    self.pci_dev = f"{vendor}:{device}"
            
            # Add mock NVMe devices based on config
            for i, disk in enumerate(config['hardware']['cvm_data_disks']):
                if disk not in exclude_devs:
                    # Use realistic values for vendor and device IDs
                    nvme_devs.append(MockPciDevice(f"0000:00:{i+1:02x}.0", "144d", "a804"))
            
            return nvme_devs
            
        # Assign the functions to the module
        pci_util.pci_search = mock_pci_search
        pci_util.parse_lspci = mock_parse_lspci
        pci_util.list_block_devices_by_controllers = mock_list_block_devices_by_controllers
        pci_util.list_nvme_devices = mock_list_nvme_devices
        
        # Register the pci_util submodule
        sys.modules['hardware_inventory.pci_util'] = pci_util
        hardware_inventory.pci_util = pci_util
    
    # Create mock layout module as fallback
    try:
        import layout
        log("Found layout module")
    except ImportError:
        log("Creating mock layout module...")
        import types
        
        # Create the layout module
        layout = types.ModuleType('layout')
        sys.modules['layout'] = layout
        
        # Create layout.layout_finder
        layout_finder = types.ModuleType('layout.layout_finder')
        layout_finder.find_model_match = lambda: (None, "CommunityEdition", "Nutanix Community Edition")
        layout_finder.is_layout_supported = lambda: True
        layout_finder.set_hw_attributes_override = lambda x: None
        layout_finder.get_layout = lambda x: {"node": {"boot_device": {"structure": "HYPERVISOR_ONLY"}}}
        layout_finder.get_vpd_info = lambda: {}
        sys.modules['layout.layout_finder'] = layout_finder
        
        # Create layout.pre_new_policy_models
        pre_new_policy_models = types.ModuleType('layout.pre_new_policy_models')
        
        # Add required functions and constants to pre_new_policy_models
        pre_new_policy_models.BOOT_DEVICE_STRUCTURE_HYPERVISOR_ONLY = "HYPERVISOR_ONLY"
        pre_new_policy_models.BOOT_DEVICE_STRUCTURE_HYPERVISOR_AND_CVM = "HYPERVISOR_AND_CVM"
        pre_new_policy_models.BOOT_DEVICE_STRUCTURE_CVM_ONLY = "CVM_ONLY"
        
        # Register the pre_new_policy_models submodule
        sys.modules['layout.pre_new_policy_models'] = pre_new_policy_models
        layout.pre_new_policy_models = pre_new_policy_models
        
        # Create layout.layout_tools
        layout_tools = types.ModuleType('layout.layout_tools')
        
        # Add constants
        layout_tools.RDMA_NIC_PASSTHRU = "rdma_nic_passthru"
        layout_tools.RDMA_PORT_PASSTHRU = "rdma_port_passthru"
        layout_tools.VROC = "VROC"
        
        # Add functions
        layout_tools.get_boot_device_from_layout = lambda layout, lun_index=0, exclude_boot_serial=None: None
        layout_tools.normalize_node_number = lambda x: 1
        layout_tools.get_hyp_raid_info_from_layout = lambda layout: (None, None)
        layout_tools.get_raid_boot_devices_info = lambda structure, raid_ctl: []
        layout_tools.get_possible_boot_devices_from_layout = lambda layout: [config['hardware']['boot_disk']]
        layout_tools.get_data_disks = lambda layout: config['hardware']['cvm_data_disks']
        
        # More detailed implementation of get_hbas based on the real implementation
        def mock_get_hbas(pci_devices=None, **kwargs):
            # Return an empty list of HBAs
            return []
            
        # More detailed implementation of get_passthru_rdma_pci_info based on the real implementation
        def mock_get_passthru_rdma_pci_info(hw_layout, passthru_method=None, rdma_mac_addr=None):
            # Return an empty list of passthrough devices
            return []
            
        # More detailed implementation of get_platform_class based on the real implementation
        def mock_get_platform_class(hw_layout):
            """
            Returns the platform class: SMIPMI, IDRAC7, iLO4 or CE.
            """
            # For our mock implementation, always return "CE" (Community Edition)
            return "CE"
            
        # More detailed implementation of get_boot_hba_drivers based on the real implementation
        def mock_get_boot_hba_drivers(layout):
            """
            Returns a list of boot HBA drivers from the layout
            """
            # For our mock implementation, return a list with a single driver
            return ['nvme']
            
        # More detailed implementation of get_passthru_devices based on the real implementation
        def mock_get_passthru_devices(default_passthru=None, passthru_exclusions=None, **kwargs):
            """
            Returns a list of passthrough devices
            """
            # For our mock implementation, return an empty list
            return []
            
        # Helper functions for chassis class detection
        def mock_belongs_to_chassis_class(hw_layout, chassis_class_list):
            """
            Checks if the hardware layout belongs to a specific chassis class
            """
            if hw_layout:
                layout_class = hw_layout.get("chassis", {}).get("class", "")
                if layout_class in chassis_class_list:
                    return True
            return False
            
        # Vendor-specific detection functions
        def mock_is_dell(hw_layout):
            """
            Checks if the hardware layout is for a Dell system
            """
            return False
            
        def mock_is_dell_13G(hw_layout):
            """
            Checks if the hardware layout is for a Dell 13G system
            """
            return False
            
        def mock_is_dell_14G(hw_layout):
            """
            Checks if the hardware layout is for a Dell 14G system
            """
            return False
            
        def mock_is_hpe(hw_layout):
            """
            Checks if the hardware layout is for an HPE system
            """
            return False
            
        def mock_is_lenovo(hw_layout):
            """
            Checks if the hardware layout is for a Lenovo system
            """
            return False
            
        def mock_is_fujitsu(hw_layout):
            """
            Checks if the hardware layout is for a Fujitsu system
            """
            return False
            
        def mock_is_cisco(hw_layout):
            """
            Checks if the hardware layout is for a Cisco system
            """
            return False
            
        def mock_is_inspur(hw_layout):
            """
            Checks if the hardware layout is for an Inspur system
            """
            return False
            
        def mock_is_nx(hw_layout):
            """
            Checks if the hardware layout is for an NX system
            """
            return True
            
        def mock_is_intel(hw_layout):
            """
            Checks if the hardware layout is for an Intel system
            """
            return False
            
        # Assign the functions to the module
        layout_tools.get_hbas = mock_get_hbas
        layout_tools.get_passthru_rdma_pci_info = mock_get_passthru_rdma_pci_info
        layout_tools.get_platform_class = mock_get_platform_class
        layout_tools.get_boot_hba_drivers = mock_get_boot_hba_drivers
        layout_tools.get_passthru_devices = mock_get_passthru_devices
        layout_tools.is_dell = mock_is_dell
        layout_tools.is_dell_13G = mock_is_dell_13G
        layout_tools.is_dell_14G = mock_is_dell_14G
        layout_tools.is_hpe = mock_is_hpe
        layout_tools.is_lenovo = mock_is_lenovo
        layout_tools.is_fujitsu = mock_is_fujitsu
        layout_tools.is_cisco = mock_is_cisco
        layout_tools.is_inspur = mock_is_inspur
        layout_tools.is_nx = mock_is_nx
        layout_tools.is_intel = mock_is_intel
        sys.modules['layout.layout_tools'] = layout_tools
        
        # Create layout.layout_vroc_utils
        layout_vroc_utils = types.ModuleType('layout.layout_vroc_utils')
        layout_vroc_utils.get_vroc_boot_devices = lambda volume: []
        layout_vroc_utils.get_vroc_volume_size = lambda volume: 0
        layout_vroc_utils.get_boot_device_info = lambda dev: None
        layout_vroc_utils.get_vroc_volume = lambda path: None
        layout_vroc_utils.get_vroc_volumes = lambda: []
        layout_vroc_utils.get_md_volumes = lambda exclude_volumes=None: []
        layout_vroc_utils.get_hyp_raid_volume_excluded_mds = lambda: []
        sys.modules['layout.layout_vroc_utils'] = layout_vroc_utils
        
        # Add submodules to parent modules
        layout.layout_finder = layout_finder
        layout.layout_tools = layout_tools
        layout.layout_vroc_utils = layout_vroc_utils
    
    # Create mock lxml module
    try:
        import lxml
        log("Found lxml module")
    except ImportError:
        log("Creating mock lxml module...")
        import types
        
        # Create the lxml module
        lxml = types.ModuleType('lxml')
        sys.modules['lxml'] = lxml
        
        # Create lxml.etree submodule
        etree = types.ModuleType('lxml.etree')
        
        # Add minimal functionality
        class Element:
            def __init__(self, tag, attrib=None, **extra):
                self.tag = tag
                self.attrib = attrib or {}
                self.text = None
                self.tail = None
                self._children = []
            
            def append(self, element):
                self._children.append(element)
        
        etree.Element = Element
        etree.SubElement = lambda parent, tag, attrib=None, **extra: Element(tag, attrib, **extra)
        etree.tostring = lambda element, **kwargs: b"<mock_xml />"
        etree.fromstring = lambda text, **kwargs: Element("mock")
        etree.parse = lambda source, **kwargs: type('MockElementTree', (), {'getroot': lambda self: Element("root")})()
        
        # Register the submodule
        sys.modules['lxml.etree'] = etree
        lxml.etree = etree
    
    # Create mock xattr module
    try:
        import xattr
        log("Found xattr module")
    except ImportError:
        log("Creating mock xattr module...")
        import types
        
        # Create the xattr module
        xattr_module = types.ModuleType('xattr')
        sys.modules['xattr'] = xattr_module
        
        # Add minimal functionality
        def mock_getxattr(path, name, *args, **kwargs):
            return b""
            
        def mock_setxattr(path, name, value, *args, **kwargs):
            pass
            
        def mock_removexattr(path, name, *args, **kwargs):
            pass
            
        def mock_listxattr(path, *args, **kwargs):
            return []
        
        # Assign functions to the module
        xattr_module.getxattr = mock_getxattr
        xattr_module.setxattr = mock_setxattr
        xattr_module.removexattr = mock_removexattr
        xattr_module.listxattr = mock_listxattr
    
    # Create mock pycdlib module
    try:
        import pycdlib
        log("Found pycdlib module")
    except ImportError:
        log("Creating mock pycdlib module...")
        import types
        
        # Create the pycdlib module
        pycdlib_module = types.ModuleType('pycdlib')
        sys.modules['pycdlib'] = pycdlib_module
        
        # Create PyCdlib class
        class MockPyCdlib:
            def __init__(self):
                self.files = {}
                
            def open(self, iso_path):
                return
                
            def get_file_from_iso(self, iso_path, local_path):
                return
                
            def add_file(self, local_path, iso_path):
                self.files[iso_path] = local_path
                return
                
            def write(self, iso_path):
                return
                
            def close(self):
                return
        
        # Add the class to the module
        pycdlib_module.PyCdlib = MockPyCdlib
    
    # Create mock chroot module
    try:
        import chroot
        log("Found chroot module")
    except ImportError:
        log("Creating mock chroot module...")
        import types
        
        # Create the chroot module
        chroot_module = types.ModuleType('chroot')
        sys.modules['chroot'] = chroot_module
        
        # Create Chroot class
        class MockChroot:
            def __init__(self, chroot_path, mount_path=None, bind_mounts=None):
                self.chroot_path = chroot_path
                self.mount_path = mount_path
                self.bind_mounts = bind_mounts or []
                
                # Create the chroot directory if it doesn't exist
                os.makedirs(chroot_path, exist_ok=True)
                
                # If mount_path is specified, create it too
                if mount_path:
                    os.makedirs(mount_path, exist_ok=True)
            
            def execute(self, cmd, *args, **kwargs):
                log(f"Mock chroot execute: {cmd}")
                return "", ""
                
            def copy_file(self, src, dst):
                log(f"Mock chroot copy_file: {src} -> {dst}")
                return
                
            def __enter__(self):
                return self
                
            def __exit__(self, exc_type, exc_val, exc_tb):
                return
        
        # Add the class to the module
        chroot_module.Chroot = MockChroot
    
    # Ensure the config has a 'node' section
    if 'node' not in config:
        log("Adding 'node' section to config")
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
    
    # Phase 6: Clean previous attempts and run Nutanix installation
    if not cleanup_previous_attempts():
        drop_to_shell("Cleanup of previous installation attempts failed")
    
    log("Running Nutanix installation", phase=6)
    if not run_nutanix_installation(params, config):
        drop_to_shell("Nutanix installation process failed")
    
    # Phase 7: Verify Installation
    log("Verifying installation...", phase=7)
    if not verify_installation(config):
        drop_to_shell("Installation verification failed")
    
    # Phase 8: Reboot Server
    log("Installation complete. Rebooting server.", phase=8)
    subprocess.run(['reboot'])
    
    log("Node-agnostic installation completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())