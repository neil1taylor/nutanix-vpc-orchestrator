"""
Boot service for handling iPXE requests and boot script generation
"""
import logging
from database import Database
from config import Config
from server_profiles import ServerProfileConfig

logger = logging.getLogger(__name__)

import hashlib
import os

class BootService:
    def __init__(self):
        self.db = Database()
        self.config = Config()
        # Import IBMCloudClient here to avoid circular imports
        from ibm_cloud_client import IBMCloudClient
        self.ibm_cloud = IBMCloudClient()
    
    def handle_ipxe_boot(self, request_args):
        """Handle iPXE boot requests from provisioned servers"""
        # Get management IP and clean it up
        mgmt_ip = request_args.get('mgmt_ip', '')
        if '@' in mgmt_ip:
            # Handle case where @ is used instead of & in URL
            logger.warning(f"Found @ in IP: {mgmt_ip}, cleaning up")
            mgmt_ip = mgmt_ip.split('@')[0]
            
        # Removed boot_type check and calls to generate_iso_boot_script and generate_default_boot_script
        # All requests will now use the general generate_boot_script

        # Start monitoring for this IP address immediately, even before database lookup
        if mgmt_ip:
            try:
                # Try to find the node by IP first
                node_by_ip = self.db.get_node_by_management_ip(mgmt_ip)
                if node_by_ip:
                    # Start server status monitoring if not already running
                    try:
                        from node_provisioner import NodeProvisioner
                        node_provisioner = NodeProvisioner()
                        logger.info(f"Starting server status monitoring for IP {mgmt_ip} from iPXE boot request")
                        node_provisioner.start_deployment_monitoring(node_by_ip['id'])
                    except Exception as e:
                        logger.error(f"Failed to start monitoring from iPXE boot request: {str(e)}")
                        # Log full traceback for debugging
                        import traceback
                        logger.error(f"Full traceback: {traceback.format_exc()}")
            except Exception as e:
                logger.error(f"Failed to lookup node by IP {mgmt_ip}: {str(e)}")
                # Continue with normal flow, don't return error here
        
        # Look up server in database by management IP
        if mgmt_ip:
            node = self.db.get_node_by_management_ip(mgmt_ip)
        else:
            logger.warning("No mgmt_ip provided in iPXE boot request")
            # Use generate_error_boot_script as a fallback if mgmt_ip is missing
            return self.generate_error_boot_script(
                "No mgmt_ip provided in iPXE boot request"
            )
        
        if not node:
            logger.warning(f"Server {mgmt_ip} not found in configuration database")
            # Use generate_error_boot_script if node is not found
            return self.generate_error_boot_script(
                f"Server {mgmt_ip} not found in configuration database"
            )
        
        # Update deployment status
        self.db.log_deployment_event(
            node['id'],
            'ipxe_boot',
            'in_progress',
            f"iPXE boot initiated from node {node.get('management_ip', 'unknown')}"
        )
        
        # Start server status monitoring if not already running
        try:
            from node_provisioner import NodeProvisioner
            node_provisioner = NodeProvisioner()
            logger.info(f"Starting server status monitoring for node {node['id']} from boot service")
            node_provisioner.start_deployment_monitoring(node['id'])
        except Exception as e:
            logger.error(f"Failed to start monitoring from boot service: {str(e)}")
            # Log full traceback for debugging
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Generate boot script for node provisioning
        boot_script = self.generate_boot_script(node)
        
        # Log the boot script content with a clear separator for better readability
        logger.info(f"Generated boot script for {node['node_name']}:")
        logger.info("--- BEGIN BOOT SCRIPT ---")
        for line in boot_script.splitlines():
            logger.info(f"BOOT: {line}")
        logger.info("--- END BOOT SCRIPT ---")
        
        return boot_script
    
    def generate_boot_script(self, node):
        """Generate an iPXE boot script for Nutanix CE automated installation"""
        # Log the node configuration for debugging
        logger.info(f"Generating boot script for node: {node['node_name']}")
        logger.info(f"Node configuration: Management IP: {node['management_ip']}, AHV IP: {node['nutanix_config']['ahv_ip']}, CVM IP: {node['nutanix_config']['cvm_ip']}")
        
        # Get network information from VPC SDK
        try:
            # Get the management subnet ID from the node configuration
            management_subnet_id = Config.MANAGEMENT_SUBNET_ID
            
            # Get network information from VPC SDK
            from ibm_cloud_client import IBMCloudClient
            ibm_cloud = IBMCloudClient()
            
            # Get subnet information
            subnet_info = ibm_cloud.get_subnet_info(management_subnet_id)
            logger.info(f"Retrieved subnet info for {management_subnet_id}")
            
            # Get gateway address
            gateway = ibm_cloud.get_subnet_gateway(management_subnet_id)
            logger.info(f"Retrieved gateway for subnet {management_subnet_id}: {gateway}")
            
            # Get netmask
            netmask = ibm_cloud.get_subnet_netmask(management_subnet_id)
            logger.info(f"Retrieved netmask for subnet {management_subnet_id}: {netmask}")
            
            # Get DNS servers
            dns_servers = ibm_cloud.get_vpc_dns_servers(Config.VPC_ID)
            # Join all DNS servers with commas for the NAMESERVER parameter
            dns_server_list = ','.join(dns_servers) if dns_servers else '8.8.8.8'
            logger.info(f"Retrieved DNS servers for VPC {Config.VPC_ID}: {dns_servers}, using {dns_server_list}")
            
            # Store network information
            network_info = {
                'ip': str(node['management_ip']),
                'netmask': netmask,
                'gateway': gateway,
                'dns': dns_server_list,
                'mac': ''  # We don't have the MAC address from the SDK
            }
            logger.info(f"Network info prepared: {network_info}")
        except Exception as e:
            logger.warning(f"Failed to get network information from VPC SDK: {str(e)}")
            # Use default values if VPC SDK fails
            network_info = {
                'ip': str(node['management_ip']),
                'netmask': '255.255.0.0',
                'gateway': '',
                'dns': '8.8.8.8,9.9.9.9',  # Use multiple DNS servers by default
                'mac': ''
            }
        
        # Define URLs for boot files
        base_url = f"http://{Config.PXE_SERVER_DNS}:8080/boot/images"
        
        template = f"""#!ipxe
echo ===============================================
echo Nutanix CE Direct Installation
echo IBM Cloud VPC + Ionic Driver
echo ===============================================
echo Node ID: {node['node_name']}
echo Management IP: {node['management_ip']}
echo AHV IP: {node['nutanix_config']['ahv_ip']}
echo CVM IP: {node['nutanix_config']['cvm_ip']}
echo ===============================================

:retry_dhcp
dhcp || goto retry_dhcp
sleep 2

# Set PXE server URL
set base-url http://{Config.PXE_SERVER_DNS}:8080

# Direct kernel boot with optimized parameters
kernel ${{base-url}}/boot/images/kernel init=/vpc_init config_server=${{base-url}} console=tty1 console=ttyS1,115200n8 intel_iommu=on iommu=pt kvm-intel.nested=1 kvm.ignore_msrs=1 kvm-intel.ept=1 vga=791 net.ifnames=0 IMG=squashfs PXEBOOT=true LIVEFS_URL=${{base-url}}/squashfs.img AUTOMATED_INSTALL=true

# Use VPC initrd
initrd ${{base-url}}/boot/images/initrd-vpc.img

boot || goto error

:error
echo Boot failed
shell
"""
        # Log the generated boot script for debugging
        logger.info("Generated iPXE boot script for VPC with Ionic driver")
        return template
    
    def generate_error_boot_script(self, error_message):
        """Generate error boot script"""
        template = f"""#!ipxe
echo ===============================================
echo Nutanix CE Boot Error
echo ===============================================
echo Error: {error_message}
echo ===============================================
echo Please check:
echo 1. Server is properly registered in configuration
echo 2. Network connectivity to PXE server
echo 3. IP address assignment is correct
echo ===============================================
echo Dropping to iPXE shell for debugging...
shell
"""
        return template
        
# Removed generate_iso_boot_script method

    # generate_default_boot_script method removed as per requirements
    
    def get_server_config(self, server_ip):
        """Get detailed server configuration for CE installer automation (Arizona configuration)"""
        logger.info(f"Attempting to get server config for IP: {server_ip}")
        
        try:
            # Get node information from database
            node = self.db.get_node_by_management_ip(server_ip)
            
            if not node:
                logger.error(f"Server config requested for unknown IP: {server_ip}")
                return None
            
            # Log configuration request
            try:
                self.db.log_deployment_event(
                    node['id'],
                    'config_requested',
                    'success',
                    f'Configuration delivered to {server_ip}'
                )
            except Exception as e:
                logger.error(f"Failed to log deployment event: {str(e)}")
                # Continue processing even if logging fails
            
            # Start server status monitoring if not already running
            try:
                from node_provisioner import NodeProvisioner
                node_provisioner = NodeProvisioner()
                logger.info(f"Starting server status monitoring for node {node['id']} from config request")
                node_provisioner.start_deployment_monitoring(node['id'])
            except Exception as e:
                logger.error(f"Failed to start monitoring from config request: {str(e)}")
                # Continue processing even if monitoring fails
            
            # Default network values in case VPC SDK fails
            gateway = '192.168.0.1'
            netmask = '255.255.0.0'
            dns_server_list = '8.8.8.8,9.9.9.9'
            
            # Get network information from VPC SDK
            try:
                # Get the management subnet ID from the node configuration
                management_subnet_id = Config.MANAGEMENT_SUBNET_ID
                
                # Get network information from VPC SDK
                from ibm_cloud_client import IBMCloudClient
                ibm_cloud = IBMCloudClient()
                
                # Get gateway address
                vpc_gateway = ibm_cloud.get_subnet_gateway(management_subnet_id)
                if vpc_gateway:
                    gateway = vpc_gateway
                    logger.info(f"Retrieved gateway for subnet {management_subnet_id}: {gateway}")
                
                # Get netmask
                vpc_netmask = ibm_cloud.get_subnet_netmask(management_subnet_id)
                if vpc_netmask:
                    netmask = vpc_netmask
                    logger.info(f"Retrieved netmask for subnet {management_subnet_id}: {netmask}")
                
                # Get DNS servers
                dns_servers = ibm_cloud.get_vpc_dns_servers(Config.VPC_ID)
                if dns_servers:
                    dns_server_list = ','.join(dns_servers)
                    logger.info(f"Retrieved DNS servers for VPC {Config.VPC_ID}: {dns_servers}")
            except Exception as e:
                logger.warning(f"Failed to get network information from VPC SDK: {str(e)}")
                logger.warning("Using default network values")
            
            # Get storage configuration from server profiles with robust error handling
            try:
                from server_profiles import ServerProfileConfig
                server_profiles = ServerProfileConfig()
                profile = node.get('server_profile', 'bx2d-metal-48x192')
                logger.info(f"Getting storage config for profile: {profile}")
                storage_config_from_profile = server_profiles.get_storage_config(profile)

                if not storage_config_from_profile:
                    logger.error(f"Empty storage configuration returned for profile {profile}")
                    # Use default storage config if profile is unknown or empty
                    storage_config_for_installer = {
                        'boot_device': '/dev/sda',
                        'hypervisor_device': '/dev/sda',
                        'cvm_device': '/dev/sda',
                        'data_drives': ['/dev/sdb'],
                        'exclude_drives': 0,
                        'raid_config': 'nutanix_managed'
                    }
                    logger.info(f"Using default storage configuration: {storage_config_for_installer}")
                else:
                    # Map to installer's expected JSON structure
                    storage_config_for_installer = {
                        'boot_device': storage_config_from_profile.get('boot_drives', ['/dev/sda'])[0], # Use first boot drive
                        'hypervisor_device': storage_config_from_profile.get('boot_drives', ['/dev/sda'])[0], # Hypervisor uses boot device
                        'cvm_device': storage_config_from_profile.get('boot_drives', ['/dev/sda'])[0], # CVM also uses boot device for its OS install
                        'data_drives': storage_config_from_profile.get('data_drives', ['/dev/sdb']),
                        'exclude_drives': storage_config_from_profile.get('exclude_drives', 0),
                        'raid_config': storage_config_from_profile.get('raid_config', 'nutanix_managed')
                    }
                    logger.info(f"Mapped storage configuration: {storage_config_for_installer}")

            except Exception as e:
                logger.error(f"Failed to get storage configuration: {str(e)}")
                # Use fallback storage configuration
                storage_config_for_installer = {
                    'boot_device': '/dev/sda',
                    'hypervisor_device': '/dev/sda',
                    'cvm_device': '/dev/sda',
                    'data_drives': ['/dev/sdb'],
                    'exclude_drives': 0,
                    'raid_config': 'nutanix_managed'
                }
                logger.info(f"Using fallback storage configuration due to error: {storage_config_for_installer}")

            # Helper to convert size string (e.g., '960GB') to GB integer
            def convert_size_to_gb(size_str):
                if not size_str: return 0
                size_str = size_str.upper()
                if size_str.endswith('GB'):
                    return int(size_str[:-2])
                elif size_str.endswith('TB'):
                    return int(float(size_str[:-2]) * 1024)
                return 0 # Default to 0 if format is unexpected

            # Construct the final installer configuration JSON
            installer_config = {
                "hardware": {
                    "model": "CommunityEdition", # Placeholder, can be derived from profile if needed
                    "boot_disk": storage_config_for_installer['boot_device'],
                    "boot_disk_model": "Micron_7450_MTFD", # Hardcoded as per example, or derive if possible
                    "boot_disk_size_gb": convert_size_to_gb(storage_config_from_profile.get('boot_drive_size', '960GB')), # Convert size to GB
                    "cvm_data_disks": storage_config_for_installer['data_drives'],
                    "cvm_boot_disks": [storage_config_for_installer['boot_device']], # Using boot_device as per common practice, example in doc might be wrong
                    "hypervisor_boot_disk": storage_config_for_installer['hypervisor_device']
                },
                "resources": {
                    "cvm_memory_gb": node.get('nutanix_config', {}).get('cvm_memory_gb', 32), # Get from node config or use default
                    "cvm_vcpus": node.get('nutanix_config', {}).get('cvm_vcpus', 16)      # Get from node config or use default
                },
                "network": {
                    "cvm_ip": ip_allocation['cvm']['ip_address'],
                    "cvm_netmask": network_info['netmask'],
                    "cvm_gateway": network_info['gateway'],
                    "dns_servers": network_info['dns'].split(',') # Split comma-separated string
                }
            }
            # ... rest of the function, ensuring installer_config is returned or used ...
            
            # Define URLs for installer packages
            base_url = f"http://{Config.PXE_SERVER_DNS}:8080/boot/images"
            svm_installer_url = f"{base_url}/nutanix_installer_package.tar.gz"
            hypervisor_iso_url = f"{base_url}/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso"
            squashfs_url = f"{base_url}/squashfs.img"
            
            # Get MD5 checksums from pre-calculated file
            try:
                # Check if checksums file exists
                checksums_file = os.path.join(Config.BOOT_IMAGES_PATH, "checksums.json")
                
                if os.path.exists(checksums_file):
                    logger.info(f"Reading pre-calculated checksums from {checksums_file}")
                    import json
                    with open(checksums_file, 'r') as f:
                        checksums = json.load(f)
                    
                    # Get checksums for each file
                    svm_installer_md5 = checksums.get("nutanix_installer_package.tar.gz", "checksum_not_found")
                    hypervisor_iso_md5 = checksums.get("AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso", "checksum_not_found")
                    squashfs_md5 = checksums.get("squashfs.img", "checksum_not_found")
                    
                    logger.info(f"MD5 checksums from file: SVM={svm_installer_md5}, HYP={hypervisor_iso_md5}, FS={squashfs_md5}")
                else:
                    # Fallback to file sizes if checksums file doesn't exist
                    logger.warning(f"Checksums file not found: {checksums_file}, falling back to MD5 calculation")
                    svm_installer_path = os.path.join(Config.BOOT_IMAGES_PATH, "nutanix_installer_package.tar.gz")
                    hypervisor_iso_path = os.path.join(Config.BOOT_IMAGES_PATH, "AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso")
                    squashfs_path = os.path.join(Config.BOOT_IMAGES_PATH, "squashfs.img")
                    
                    # Calculate MD5 checksums for all files
                    if os.path.exists(svm_installer_path):
                        svm_installer_md5 = self.calculate_md5(svm_installer_path)
                        logger.info(f"Calculated MD5 for SVM installer: {svm_installer_md5}")
                    else:
                        svm_installer_md5 = "file_not_found"
                    
                    if os.path.exists(hypervisor_iso_path):
                        hypervisor_iso_md5 = self.calculate_md5(hypervisor_iso_path)
                        logger.info(f"Calculated MD5 for hypervisor ISO: {hypervisor_iso_md5}")
                    else:
                        hypervisor_iso_md5 = "file_not_found"
                    
                    if os.path.exists(squashfs_path):
                        squashfs_md5 = self.calculate_md5(squashfs_path)
                        logger.info(f"Calculated MD5 for squashfs: {squashfs_md5}")
                    else:
                        squashfs_md5 = "file_not_found"
            except Exception as e:
                logger.error(f"Failed to get checksums: {str(e)}")
                import traceback
                logger.error(f"Checksums error traceback: {traceback.format_exc()}")
                svm_installer_md5 = "checksum_error"
                hypervisor_iso_md5 = "checksum_error"
                squashfs_md5 = "checksum_error"
            
            # Check if this is the first node (for cluster creation flag)
            try:
                is_first_node = self.db.is_first_node()
            except Exception as e:
                logger.warning(f"Failed to determine if this is the first node: {str(e)}")
                is_first_node = True  # Default to creating a cluster
            
            # Format response according to Arizona configuration format
            response = {
                # Basic node information
                'hyp_type': 'kvm',  # AHV is based on KVM
                'node_position': 'A',  # All nodes use position A as requested
                
                # URLs for installer packages with MD5 checksums
                'svm_installer_url': {
                    'url': svm_installer_url,
                    'md5sum': svm_installer_md5
                },
                'hypervisor_iso_url': {
                    'url': hypervisor_iso_url,
                    'md5sum': hypervisor_iso_md5
                },
                'squashfs_url': {
                    'url': squashfs_url,
                    'md5sum': squashfs_md5
                },
                
                # Node configuration array (single node in our case)
                'nodes': [
                    {
                        'node_position': 'A',  # All nodes use position A
                        'hyp_ip': str(node['management_ip']),
                        'hyp_netmask': netmask,
                        'hyp_gateway': gateway,
                        'svm_ip': node.get('nutanix_config', {}).get('cvm_ip', str(node['management_ip'])),
                        'svm_netmask': netmask,
                        'svm_gateway': gateway,
                        'disk_layout': {
                            # For NVMe-based servers, use /dev/nvme0n1 as boot and CVM disk
                            'boot_disk': '/dev/nvme0n1' if 'nvme' in str(storage_config.get('data_drives', [])) else storage_config.get('boot_device', '/dev/sda'),
                            'cvm_disk': '/dev/nvme0n1' if 'nvme' in str(storage_config.get('data_drives', [])) else storage_config.get('boot_device', '/dev/sda'),
                            # Add /dev/ prefix to all data drives if not already present
                            'storage_pool_disks': [f"/dev/{drive}" if not drive.startswith('/dev/') else drive for drive in storage_config.get('data_drives', ['/dev/sdb'])]
                        }
                    }
                ],
                
                # Network configuration
                'dns_servers': dns_server_list,
                'ntp_servers': 'time.adn.networklayer.com',
                
                # Installation flags
                'skip_hypervisor': False,
                'install_cvm': True,
                
                # CE-specific flags
                'create_1node_cluster': is_first_node,  # Only create cluster if this is the first node
                'ce_eula_accepted': True,
                'ce_eula_viewed': True,
                
                # Additional metadata
                'cluster_name': 'ce-cluster',
                'node_name': node['node_name']
            }
            
            # Log the full configuration for debugging
            logger.info(f"Generated Arizona configuration for {node.get('node_name', 'unknown')}")
            logger.info(f"Configuration details: nodes={len(response['nodes'])}, dns={response['dns_servers']}")
            logger.info(f"Disk layout: boot={response['nodes'][0]['disk_layout']['boot_disk']}, data={response['nodes'][0]['disk_layout']['storage_pool_disks']}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to generate server configuration for {server_ip}: {str(e)}")
            # Log full traceback for debugging
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None
    
    def calculate_md5(self, file_path):
        """Calculate MD5 checksum of a file"""
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                logger.warning(f"File not found for MD5 calculation: {file_path}")
                return "file_not_found"
            
            # Check if file is readable
            if not os.access(file_path, os.R_OK):
                logger.warning(f"File not readable for MD5 calculation: {file_path}")
                return "file_not_readable"
            
            # Check file size
            try:
                file_size = os.path.getsize(file_path)
                logger.info(f"File size for MD5 calculation: {file_path} = {file_size} bytes")
                if file_size == 0:
                    logger.warning(f"Empty file for MD5 calculation: {file_path}")
                    return "empty_file"
            except Exception as e:
                logger.warning(f"Could not get file size: {file_path}: {str(e)}")
            
            # Calculate MD5
            md5_hash = hashlib.md5()
            with open(file_path, "rb") as f:
                # Read file in chunks to handle large files efficiently
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
            
            md5_checksum = md5_hash.hexdigest()
            logger.info(f"MD5 checksum for {file_path}: {md5_checksum}")
            return md5_checksum
            
        except PermissionError as e:
            logger.error(f"Permission error calculating MD5 for {file_path}: {str(e)}")
            return "permission_denied"
        except IOError as e:
            logger.error(f"IO error calculating MD5 for {file_path}: {str(e)}")
            return "io_error"
        except Exception as e:
            logger.error(f"Failed to calculate MD5 checksum for {file_path}: {str(e)}")
            import traceback
            logger.error(f"MD5 calculation traceback: {traceback.format_exc()}")
            return "md5_calculation_failed"
    
    
    
    def generate_documented_storage_config(self, node):
        """Generate storage configuration in the documented format"""
        try:
            # Get storage configuration from server profiles
            server_profiles = ServerProfileConfig()
            
            # Safely get server profile with fallback
            profile = node.get('server_profile', 'bx2d-metal-48x192')
            logger.info(f"Getting documented storage config for profile: {profile}")
            
            # Get storage configuration with error handling
            try:
                storage_config = server_profiles.get_storage_config(profile)
            except Exception as e:
                logger.error(f"Failed to get storage config for {profile}: {str(e)}")
                # Use default values
                storage_config = {
                    'boot_device': '/dev/sda',
                    'data_drives': ['/dev/sdb']
                }
                logger.info(f"Using default storage configuration: {storage_config}")
            
            # Safely extract drive names with error handling
            try:
                # Extract just the drive names without the /dev/ prefix
                data_drives = [drive.replace('/dev/', '') for drive in storage_config.get('data_drives', ['/dev/sdb'])]
                boot_drives = [drive.replace('/dev/', '') for drive in [storage_config.get('boot_device', '/dev/sda')]]
                
                logger.info(f"Documented storage config: boot={boot_drives}, data={data_drives}")
                
                return {
                    'data_drives': data_drives,
                    'boot_drives': boot_drives
                }
            except Exception as e:
                logger.error(f"Error formatting drive names: {str(e)}")
                # Return default values
                return {
                    'data_drives': ['sdb'],
                    'boot_drives': ['sda']
                }
                
        except Exception as e:
            logger.error(f"Failed to generate documented storage config: {str(e)}")
            import traceback
            logger.error(f"Storage config traceback: {traceback.format_exc()}")
            # Return default values
            return {
                'data_drives': ['sdb'],
                'boot_drives': ['sda']
            }