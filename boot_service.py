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
        mgmt_ip = request_args.get('mgmt_ip')
        mgmt_mac = request_args.get('mgmt_mac')
        workload_ip = request_args.get('workload_ip')
        workload_mac = request_args.get('workload_mac')
        server_serial = request_args.get('serial')
        node_id = request_args.get('node_id')
        boot_type = request_args.get('type')
        
        mac_info = f" (MAC: {mgmt_mac})" if mgmt_mac else ""
        type_info = f" (Type: {boot_type})" if boot_type else ""
        logger.info(f"iPXE boot request from {mgmt_ip}{mac_info}{type_info}")
        
        # Check if this is an ISO boot request
        if boot_type == 'iso':
            logger.info(f"Generating ISO boot script for {mgmt_ip}")
            return self.generate_iso_boot_script(mgmt_ip)
        
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
        
        # Look up server in database by node_id (primary) or management IP (fallback)
        if node_id:
            # Convert node_id to integer if it's a string
            try:
                node_id_int = int(node_id)
                node = self.db.get_node(node_id_int)
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid node_id format: {node_id}")
                return self.generate_error_boot_script(
                    f"Invalid node_id format: {node_id}"
                )
        elif mgmt_ip:
            node = self.db.get_node_by_management_ip(mgmt_ip)
        else:
            logger.warning("No node_id or mgmt_ip provided in iPXE boot request")
            return self.generate_error_boot_script(
                "No node_id or mgmt_ip provided in iPXE boot request"
            )
        
        if not node:
            if node_id:
                logger.warning(f"Node {node_id} not found in configuration database")
                return self.generate_error_boot_script(
                    f"Node {node_id} not found in configuration database"
                )
            else:
                logger.warning(f"Server {mgmt_ip} not found in configuration database")
                return self.generate_error_boot_script(
                    f"Server {mgmt_ip} not found in configuration database"
                )
        
        # Update deployment status
        self.db.log_deployment_event(
            node['id'],
            'ipxe_boot',
            'in_progress',
            f"iPXE boot initiated from node {node_id or node.get('management_ip', 'unknown')}"
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
            # Use first DNS server from the list, with consistent fallback
            dns_server = dns_servers[0] if dns_servers else '8.8.8.8'
            logger.info(f"Retrieved DNS servers for VPC {Config.VPC_ID}: {dns_servers}, using {dns_server}")
            
            # Store network information
            network_info = {
                'ip': str(node['management_ip']),
                'netmask': netmask,
                'gateway': gateway,
                'dns': dns_server,
                'mac': ''  # We don't have the MAC address from the SDK
            }
            logger.info(f"Network info prepared: {network_info}")
        except Exception as e:
            logger.warning(f"Failed to get network information from VPC SDK: {str(e)}")
            # Use default values if VPC SDK fails
            network_info = {
                'ip': str(node['management_ip']),
                'netmask': '255.255.255.0',
                'gateway': '',
                'dns': '8.8.8.8',
                'mac': ''
            }
        
        # Define URLs for boot files
        base_url = f"http://{Config.PXE_SERVER_DNS}:8080/boot/images"
        squashfs_url = f"{base_url}/squashfs.img"
        arizona_url = f"http://{Config.PXE_SERVER_DNS}:8080/boot/server/{network_info['ip']}"
        
        template = f"""#!ipxe
echo ===============================================
echo Nutanix CE Automated Deployment
echo ===============================================
echo Node ID: {node['node_name']}
echo Management IP: {node['management_ip']}
echo AHV IP: {node['nutanix_config']['ahv_ip']}
echo CVM IP: {node['nutanix_config']['cvm_ip']}
echo ===============================================
echo Starting Nutanix CE installer...

:retry_dhcp
dhcp || goto retry_dhcp
sleep 2
ntp time.adn.networklayer.com
set base-url http://{Config.PXE_SERVER_DNS}:8080/boot/images
set pxe_server {Config.PXE_SERVER_DNS}

# Boot CE installer with parameters for HTTP-based installation
# This implements the two-stage approach:
# 1. Minimal kernel parameters for boot with LIVEFS_URL for HTTP download
# 2. Full JSON configuration retrieved via AZ_CONF_URL
#
# Kernel parameters optimized for NVMe-based bare metal server:
# - intel_iommu=on, iommu=pt: Essential for device passthrough
# - kvm-intel.ept=1: Improves virtualization performance
# - kvm.ignore_msrs=1: Helps with VM compatibility
# - LIVEFS_URL: Points to squashfs.img for HTTP download
# - AZ_CONF_URL: Points to Arizona configuration for automation
kernel ${{base-url}}/vmlinuz-phoenix init=/ce_installer intel_iommu=on iommu=pt kvm-intel.ept=1 kvm.ignore_msrs=1 IMG=squashfs console=tty0 console=ttyS0,115200 FOUND_IP={Config.PXE_SERVER_DNS} LIVEFS_URL={squashfs_url} AZ_CONF_URL={arizona_url} PHOENIX_IP={node['management_ip']} MASK={network_info['netmask']} GATEWAY={network_info['gateway']} NAMESERVER={network_info['dns']} ce_eula_accepted=true ce_eula_viewed=true COMMUNITY_EDITION=1
initrd ${{base-url}}/initrd-modified.img
boot || goto error

:error
echo Boot failed - dropping to shell
shell
"""
        # Log the generated boot script for debugging
        logger.info("Generated iPXE boot script with HTTP-based squashfs download")
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
        
    def generate_iso_boot_script(self, management_ip):
        """Generate iPXE boot script for ISO booting"""
        # Try to get node information if available
        node = self.db.get_node_by_management_ip(management_ip)
        node_name = node['node_name'] if node else f"Unknown-{management_ip}"
        
        # Log ISO boot request
        logger.info(f"Generating ISO boot script for {node_name} ({management_ip})")
        
        # If we have a node, log the deployment event
        if node:
            self.db.log_deployment_event(
                node['id'],
                'iso_boot',
                'in_progress',
                f"ISO boot initiated for {node_name} ({management_ip})"
            )
            
            # Start server status monitoring if not already running
            try:
                from node_provisioner import NodeProvisioner
                node_provisioner = NodeProvisioner()
                logger.info(f"Starting server status monitoring for node {node['id']} from ISO boot request")
                node_provisioner.start_deployment_monitoring(node['id'])
            except Exception as e:
                logger.error(f"Failed to start monitoring from ISO boot request: {str(e)}")
                # Log full traceback for debugging
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Generate the ISO boot script
        template = f"""#!ipxe
echo ===============================================
echo Nutanix CE Node Creation
echo ===============================================
echo Node ID: {node_name}
echo Management IP: {management_ip}
echo ===============================================
echo Starting Nutanix CE installer...

:retry_dhcp
dhcp || goto retry_dhcp
sleep 2
ntp time.adn.networklayer.com
set base-url http://{Config.PXE_SERVER_DNS}:8080/boot/images
sanboot ${{base-url}}/nutanix-ce-installer.iso
"""
        
        # Log the boot script content with a clear separator for better readability
        logger.info(f"Generated ISO boot script for {management_ip}:")
        logger.info("--- BEGIN ISO BOOT SCRIPT ---")
        for line in template.splitlines():
            logger.info(f"ISO BOOT: {line}")
        logger.info("--- END ISO BOOT SCRIPT ---")
        
        return template
    
    def get_server_config(self, server_ip):
        """Get detailed server configuration for CE installer automation (Arizona configuration)"""
        node = self.db.get_node_by_management_ip(server_ip)
        
        if not node:
            logger.error(f"Server config requested for unknown IP: {server_ip}")
            return None
        
        # Log configuration request
        self.db.log_deployment_event(
            node['id'],
            'config_requested',
            'success',
            f'Configuration delivered to {server_ip}'
        )
        
        # Start server status monitoring if not already running
        try:
            from node_provisioner import NodeProvisioner
            node_provisioner = NodeProvisioner()
            logger.info(f"Starting server status monitoring for node {node['id']} from config request")
            node_provisioner.start_deployment_monitoring(node['id'])
        except Exception as e:
            logger.error(f"Failed to start monitoring from config request: {str(e)}")
            # Log full traceback for debugging
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Get network information from VPC SDK
        try:
            # Get the management subnet ID from the node configuration
            management_subnet_id = Config.MANAGEMENT_SUBNET_ID
            
            # Get network information from VPC SDK
            from ibm_cloud_client import IBMCloudClient
            ibm_cloud = IBMCloudClient()
            
            # Get gateway address
            gateway = ibm_cloud.get_subnet_gateway(management_subnet_id)
            logger.info(f"Retrieved gateway for subnet {management_subnet_id}: {gateway}")
            
            # Get netmask
            netmask = ibm_cloud.get_subnet_netmask(management_subnet_id)
            logger.info(f"Retrieved netmask for subnet {management_subnet_id}: {netmask}")
            
            # Get DNS servers
            dns_servers = ibm_cloud.get_vpc_dns_servers(Config.VPC_ID)
            # Join all DNS servers with comma, with consistent fallback
            dns_server_list = ','.join(dns_servers) if dns_servers else '8.8.8.8,9.9.9.9'
            logger.info(f"Retrieved DNS servers for VPC {Config.VPC_ID}: {dns_servers}, using list: {dns_server_list}")
        except Exception as e:
            logger.warning(f"Failed to get network information from VPC SDK: {str(e)}")
            # Use default values if VPC SDK fails
            gateway = '10.240.0.1'
            netmask = '255.255.255.0'
            dns_server_list = '8.8.8.8,9.9.9.9'
        
        # Get storage configuration from server profiles
        from server_profiles import ServerProfileConfig
        server_profiles = ServerProfileConfig()
        storage_config = server_profiles.get_storage_config(node.get('server_profile', 'bx2d-metal-48x192'))
        
        # Define URLs and file paths for installer packages
        base_url = f"http://{Config.PXE_SERVER_DNS}:8080/boot/images"
        svm_installer_url = f"{base_url}/nutanix_installer_package.tar.gz"
        hypervisor_iso_url = f"{base_url}/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso"
        squashfs_url = f"{base_url}/squashfs.img"
        
        # Calculate MD5 checksums from the actual files
        svm_installer_path = os.path.join(Config.BOOT_IMAGES_PATH, "nutanix_installer_package.tar.gz")
        hypervisor_iso_path = os.path.join(Config.BOOT_IMAGES_PATH, "AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso")
        squashfs_path = os.path.join(Config.BOOT_IMAGES_PATH, "squashfs.img")
        
        svm_installer_md5 = self.calculate_md5(svm_installer_path)
        hypervisor_iso_md5 = self.calculate_md5(hypervisor_iso_path)
        squashfs_md5 = self.calculate_md5(squashfs_path)
        
        logger.info(f"MD5 checksums calculated: SVM={svm_installer_md5}, HYP={hypervisor_iso_md5}, FS={squashfs_md5}")
        
        # Check if this is the first node (for cluster creation flag)
        is_first_node = self.db.is_first_node()
        
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
                    'svm_ip': node['nutanix_config']['cvm_ip'],
                    'svm_netmask': netmask,
                    'svm_gateway': gateway,
                    'disk_layout': {
                        'boot_disk': storage_config['boot_device'],
                        'cvm_disk': storage_config['boot_device'],  # Use same disk for boot and CVM as in example
                        'storage_pool_disks': storage_config['data_drives']
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
        
        logger.info(f"Generated Arizona configuration for {node['node_name']}")
        return response
    
    def calculate_md5(self, file_path):
        """Calculate MD5 checksum of a file"""
        try:
            if not os.path.exists(file_path):
                logger.warning(f"File not found for MD5 calculation: {file_path}")
                return "file_not_found"
                
            md5_hash = hashlib.md5()
            with open(file_path, "rb") as f:
                # Read file in chunks to handle large files efficiently
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
            
            md5_checksum = md5_hash.hexdigest()
            logger.debug(f"MD5 checksum for {file_path}: {md5_checksum}")
            return md5_checksum
        except Exception as e:
            logger.error(f"Failed to calculate MD5 checksum for {file_path}: {str(e)}")
            return "md5_calculation_failed"
    
    
    
    def generate_documented_storage_config(self, node):
        """Generate storage configuration in the documented format"""
        # Get storage configuration from server profiles
        server_profiles = ServerProfileConfig()
        storage_config = server_profiles.get_storage_config(node['server_profile'])
        
        # Extract just the drive names without the /dev/ prefix
        data_drives = [drive.replace('/dev/', '') for drive in storage_config['data_drives']]
        boot_drives = [drive.replace('/dev/', '') for drive in [storage_config['boot_device']]]
        
        return {
            'data_drives': data_drives,
            'boot_drives': boot_drives
        }