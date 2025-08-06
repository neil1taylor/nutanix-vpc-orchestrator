"""
Boot service for handling iPXE requests and boot script generation
"""
import logging
from database import Database
from config import Config
from server_profiles import ServerProfileConfig

logger = logging.getLogger(__name__)

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
        
        mac_info = f" (MAC: {mgmt_mac})" if mgmt_mac else ""
        logger.info(f"iPXE boot request from {mgmt_ip}{mac_info}")
        
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
        """Generate a generic iPXE boot script for node provisioning"""
        template = f"""#!ipxe
echo ===============================================
echo Nutanix CE Node Provisioning
echo ===============================================
echo Node ID: {node['node_name']}
echo Management IP: {node['management_ip']}
echo AHV IP: {node['nutanix_config']['ahv_ip']}
echo CVM IP: {node['nutanix_config']['cvm_ip']}
echo ===============================================
echo Starting Nutanix Foundation deployment...

:retry_dhcp
dhcp || goto retry_dhcp
sleep 2
set base-url http://{Config.PXE_SERVER_DNS}:8080/boot/images
set node_id {node['node_name']}
set mgmt_ip {node['management_ip']}
set ahv_ip {node['nutanix_config']['ahv_ip']}
set cvm_ip {node['nutanix_config']['cvm_ip']}
kernel ${{base-url}}/vmlinuz-foundation console=tty0 console=ttyS0,115200
initrd ${{base-url}}/initrd-foundation.img
imgargs vmlinuz-foundation node_id=${{node_id}} mgmt_ip=${{mgmt_ip}} ahv_ip=${{ahv_ip}} cvm_ip=${{cvm_ip}} config_server=http://{Config.PXE_SERVER_DNS}:8080/boot/server/${{mgmt_ip}}
boot || goto error

:error
echo Boot failed - dropping to shell
shell
"""
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
    
    def get_server_config(self, server_ip):
        """Get detailed server configuration for Foundation"""
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
        
        # Generate storage configuration in the documented format
        storage_config = self.generate_documented_storage_config(node)
        
        response = {
            'node_config': {
                'node_id': node['node_name'],
                'mgmt_ip': str(node['management_ip']),
                'ahv_ip': node['nutanix_config']['ahv_ip'],
                'cvm_ip': node['nutanix_config']['cvm_ip']
            },
            'storage_config': storage_config,
            'server_profile': node['server_profile']
        }
        
        return response
    
    
    
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