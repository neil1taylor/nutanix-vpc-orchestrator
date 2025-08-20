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
       fdisk_commands = "n\np\n1\n\n+200M\nn\np\n2\n\n+32G\nn\np\n3\n\n\nt\n1\nef\nw\n"
       
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
       
       # Hypervisor partition
       result = subprocess.run(['mkfs.ext4', '-F', f'{boot_device}p2'], capture_output=True)
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
       
       result = subprocess.run(['mount', f'{boot_device}p1', '/mnt/stage/boot/efi/'])
       if result.returncode != 0:
           log("Failed to mount EFI partition")
           cleanup_mounts()
           return False
       
       # Copy EFI files
       result = subprocess.run(['cp', '-r', '/mnt/ahv/EFI/.', '/mnt/stage/boot/efi/'])
       if result.returncode != 0:
           log("Failed to copy EFI files")
           cleanup_mounts()
           return False
       
       # Create GRUB configurations
       log("Creating GRUB configurations...")
       
       # GRUB2 configuration
       os.makedirs('/mnt/stage/boot/grub2', exist_ok=True)
       grub2_config = f"""set default=0
set timeout=10

menuentry 'Nutanix AHV' {{
   linux /boot/vmlinuz-5.10.194-5.20230302.0.991650.el8.x86_64 root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0
}}
"""
       
       with open('/mnt/stage/boot/grub2/grub.cfg', 'w') as f:
           f.write(grub2_config)
       
       # Legacy GRUB configuration
       os.makedirs('/mnt/stage/boot/grub', exist_ok=True)
       grub_config = f"""default=0
timeout=10
title Nutanix AHV
   root (hd0,1)
   kernel /boot/vmlinuz-5.10.194-5.20230302.0.991650.el8.x86_64 root=/dev/{boot_disk}p2 ro crashkernel=auto net.ifnames=0
"""
       
       with open('/mnt/stage/boot/grub/grub.conf', 'w') as f:
           f.write(grub_config)
       
       log("GRUB configurations created")
       
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
        params.ce_cvm_data_disks = hw_config['cvm_data_disks']
        params.ce_cvm_boot_disks = hw_config['cvm_boot_disks']
        params.ce_hyp_boot_disk = hw_config['hypervisor_boot_disk']
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
            log("Calling imagingUtil.image_node...")
            imagingUtil.image_node(params)
            log("imagingUtil.image_node completed successfully")
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
        
        # Add required functions to disk_info
        def mock_collect_disk_info(disk_list_filter=None, skip_part_info=True):
            return {disk: None for disk in config['hardware']['cvm_data_disks']}
        
        def mock_list_hyp_boot_disks():
            return [config['hardware']['boot_disk']]
        
        # Assign the functions to the module
        disk_info.collect_disk_info = mock_collect_disk_info
        disk_info.list_hyp_boot_disks = mock_list_hyp_boot_disks
        
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
            
        # Assign the functions to the module
        layout_tools.get_hbas = mock_get_hbas
        layout_tools.get_passthru_rdma_pci_info = mock_get_passthru_rdma_pci_info
        layout_tools.get_platform_class = mock_get_platform_class
        layout_tools.get_boot_hba_drivers = mock_get_boot_hba_drivers
        layout_tools.get_passthru_devices = mock_get_passthru_devices
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
    
    # Phase 7: Reboot Server
    log("Installation complete. Rebooting server.", phase=7)
    subprocess.run(['reboot'])
    
    log("Node-agnostic installation completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())