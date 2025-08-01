"""
Boot service for handling iPXE requests and boot script generation
"""
import logging
from database import Database
from config import Config

logger = logging.getLogger(__name__)

class BootService:
    def __init__(self):
        self.db = Database()
        self.config = Config()
    
    def handle_ipxe_boot(self, request_args):
        """Handle iPXE boot requests from provisioned servers"""
        mgmt_ip = request_args.get('mgmt_ip')
        mgmt_mac = request_args.get('mgmt_mac')
        workload_ip = request_args.get('workload_ip')
        workload_mac = request_args.get('workload_mac')
        server_serial = request_args.get('serial')
        
        logger.info(f"iPXE boot request from {mgmt_ip} (MAC: {mgmt_mac})")
        
        # Look up server in database
        node = self.db.get_node_by_management_ip(mgmt_ip)
        
        if not node:
            logger.warning(f"Server {mgmt_ip} not found in configuration database")
            return self.generate_error_boot_script(
                f"Server {mgmt_ip} not found in configuration database"
            )
        
        # Update deployment status
        self.db.log_deployment_event(
            node['id'], 
            'ipxe_boot', 
            'in_progress',
            f"iPXE boot initiated from {mgmt_ip}"
        )
        
        # Determine cluster operation
        cluster_operation = self.determine_cluster_operation(node)
        
        # Generate appropriate boot script
        if cluster_operation == 'create_new':
            boot_script = self.generate_cluster_creation_script(node)
        else:
            boot_script = self.generate_node_addition_script(node, cluster_operation)
        
        logger.info(f"Generated boot script for {node['node_name']} ({cluster_operation})")
        return boot_script
    
    def determine_cluster_operation(self, node):
        """Determine if this node should create or join a cluster"""
        existing_nodes = self.db.get_nodes_with_status('deployed')
        
        if len(existing_nodes) == 0:
            # This is the first node - create new cluster
            logger.info(f"Node {node['node_name']} will create new cluster")
            return 'create_new'
        else:
            # Join existing cluster
            cluster_info = self.db.get_cluster_info()
            if cluster_info:
                logger.info(f"Node {node['node_name']} will join existing cluster {cluster_info['cluster_name']}")
                return {
                    'operation': 'join_existing',
                    'cluster_ip': cluster_info['cluster_ip'],
                    'cluster_name': cluster_info['cluster_name'],
                    'cluster_dns': cluster_info['cluster_dns']
                }
            else:
                logger.warning("Existing nodes found but no cluster info - creating new cluster")
                return 'create_new'
    
    def generate_cluster_creation_script(self, node):
        """Generate iPXE script for creating a new cluster"""
        template = f"""#!ipxe
echo ===============================================
echo Nutanix CE Cluster Creation
echo ===============================================
echo Node: {node['node_name']}
echo Management IP: {node['management_ip']}
echo AHV IP: {node['nutanix_config']['ahv_ip']}
echo CVM IP: {node['nutanix_config']['cvm_ip']}
echo Cluster IP: {node['nutanix_config']['cluster_ip']}
echo ===============================================

set base-url http://{Config.PXE_SERVER_DNS}:8080
set operation create_cluster
set node_id {node['id']}
set mgmt_ip {node['management_ip']}
set ahv_ip {node['nutanix_config']['ahv_ip']}
set cvm_ip {node['nutanix_config']['cvm_ip']}
set cluster_ip {node['nutanix_config']['cluster_ip']}
set config_server {Config.PXE_SERVER_DNS}

echo Loading Foundation environment...
kernel ${{base-url}}/images/vmlinuz-foundation console=tty0 console=ttyS0,115200
initrd ${{base-url}}/images/initrd-foundation.img

echo Starting cluster creation process...
imgargs vmlinuz-foundation node_id=${{node_id}} operation=${{operation}} mgmt_ip=${{mgmt_ip}} ahv_ip=${{ahv_ip}} cvm_ip=${{cvm_ip}} cluster_ip=${{cluster_ip}} config_server=${{config_server}}

boot || goto error

:error
echo Boot failed - dropping to shell
shell
"""
        return template
    
    def generate_node_addition_script(self, node, cluster_operation):
        """Generate iPXE script for adding node to existing cluster"""
        template = f"""#!ipxe
echo ===============================================
echo Nutanix CE Node Addition
echo ===============================================
echo Node: {node['node_name']}
echo Cluster: {cluster_operation['cluster_name']}
echo Cluster IP: {cluster_operation['cluster_ip']}
echo Node Management IP: {node['management_ip']}
echo Node AHV IP: {node['nutanix_config']['ahv_ip']}
echo Node CVM IP: {node['nutanix_config']['cvm_ip']}
echo ===============================================

set base-url http://{Config.PXE_SERVER_DNS}:8080
set operation add_node
set node_id {node['id']}
set mgmt_ip {node['management_ip']}
set ahv_ip {node['nutanix_config']['ahv_ip']}
set cvm_ip {node['nutanix_config']['cvm_ip']}
set cluster_ip {cluster_operation['cluster_ip']}
set cluster_name {cluster_operation['cluster_name']}
set config_server {Config.PXE_SERVER_DNS}

echo Loading Foundation environment...
kernel ${{base-url}}/images/vmlinuz-foundation console=tty0 console=ttyS0,115200
initrd ${{base-url}}/images/initrd-foundation.img

echo Starting node addition process...
imgargs vmlinuz-foundation node_id=${{node_id}} operation=${{operation}} mgmt_ip=${{mgmt_ip}} ahv_ip=${{ahv_ip}} cvm_ip=${{cvm_ip}} cluster_ip=${{cluster_ip}} cluster_name=${{cluster_name}} config_server=${{config_server}}

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
        
        # Determine cluster operation for storage config
        cluster_operation = self.determine_cluster_operation(node)
        is_first_node = cluster_operation == 'create_new'
        
        # Generate Foundation configuration
        foundation_config = self.generate_foundation_config(node, is_first_node)
        
        # Generate storage configuration
        storage_config = self.generate_storage_config(node)
        
        # Generate network configuration
        network_config = self.generate_network_config(node)
        
        response = {
            'server_info': {
                'server_name': node['node_name'],
                'server_id': node['id'],
                'mgmt_ip': str(node['management_ip']),
                'workload_ip': str(node['workload_ip'])
            },
            'cluster_config': foundation_config['cluster_config'],
            'node_config': foundation_config['node_config'],
            'storage_config': storage_config,
            'network_config': network_config,
            'deployment_scripts': {
                'foundation_init': '/scripts/foundation-init.sh',
                'network_setup': '/scripts/network-config.sh',
                'post_install': '/scripts/post-install.sh'
            },
            'cluster_operation': cluster_operation
        }
        
        return response
    
    def generate_foundation_config(self, node, is_first_node):
        """Generate Foundation configuration from node data"""
        nutanix_config = node['nutanix_config']
        
        # Determine cluster IP - use node's cluster IP if first node, otherwise get from existing cluster
        if is_first_node:
            cluster_ip = nutanix_config['cluster_ip']
            cluster_name = nutanix_config['cluster_dns'].split('.')[0]
        else:
            cluster_info = self.db.get_cluster_info()
            cluster_ip = cluster_info['cluster_ip'] if cluster_info else nutanix_config['cluster_ip']
            cluster_name = cluster_info['cluster_name'] if cluster_info else 'cluster01'
        
        foundation_config = {
            'cluster_config': {
                'cluster_name': cluster_name,
                'cluster_external_ip': str(cluster_ip),
                'cluster_external_data_services_ip': str(cluster_ip),
                'timezone': 'UTC',
                'ntp_servers': ['pool.ntp.org'],
                'name_servers': ['161.26.0.10', '161.26.0.11', '8.8.8.8'],
                'enable_encryption': False,
                'redundancy_factor': 1 if is_first_node else 2  # RF1 for single node, RF2 for multi-node
            },
            'node_config': {
                'hypervisor': 'ahv',
                'hypervisor_ip': nutanix_config['ahv_ip'],
                'hypervisor_netmask': '255.255.255.0',
                'hypervisor_gateway': '10.240.0.1',
                'cvm_ip': nutanix_config['cvm_ip'],
                'cvm_netmask': '255.255.255.0',
                'cvm_gateway': '10.240.0.1',
                'ipmi_ip': '127.0.0.1',  # Dummy - no real IPMI access
                'ipmi_user': 'local',
                'ipmi_password': 'local'
            }
        }
        
        return foundation_config
    
    def generate_storage_config(self, node):
        """Generate storage configuration for server"""
        # IBM Cloud VPC bare metal with 'd' profiles have specific drive layout
        storage_config = {
            'boot_device': '/dev/sda',           # RAID1 boot drives (960GB)
            'hypervisor_device': '/dev/nvme0n1', # AHV installation target
            'cvm_device': '/dev/nvme1n1',        # CVM root filesystem
            'data_devices': [                    # Nutanix storage pool
                '/dev/nvme2n1',
                '/dev/nvme3n1',
                '/dev/nvme4n1',
                '/dev/nvme5n1',
                '/dev/nvme6n1',
                '/dev/nvme7n1'
            ],
            'disk_layout': {
                'total_drives': 8,
                'boot_drives': 2,   # RAID1 SATA M.2 drives
                'nvme_drives': 8,   # 3.2TB U.2 NVMe SSDs
                'raid_config': 'software_raid'  # No hardware RAID controller access
            }
        }
        
        # Adjust based on node's storage config if specified
        if node['nutanix_config'].get('storage_config'):
            user_storage = node['nutanix_config']['storage_config']
            if 'data_drives' in user_storage:
                # Convert drive names to full paths
                storage_config['data_devices'] = [
                    f"/dev/{drive}" for drive in user_storage['data_drives']
                ]
        
        return storage_config
    
    def generate_network_config(self, node):
        """Generate network configuration for node"""
        network_config = {
            'management_network': {
                'interface': 'eth0',  # First interface is management
                'ip': node['nutanix_config']['ahv_ip'],
                'netmask': '255.255.255.0',
                'gateway': '10.240.0.1',
                'dns_servers': ['161.26.0.10', '161.26.0.11'],
                'domain': Config.DNS_ZONE_NAME
            },
            'workload_network': {
                'interface': 'eth1',  # Second interface is workload
                'ip': node['workload_ip'],
                'netmask': '255.255.255.0',
                'gateway': '10.241.0.1',
                'vlan_config': 'bridge_mode'  # Bridge for VM traffic
            },
            'cvm_network': {
                'ip': node['nutanix_config']['cvm_ip'],
                'netmask': '255.255.255.0',
                'gateway': '10.240.0.1',
                'interface': 'eth0'  # CVM uses management interface
            },
            'cluster_network': {
                'cluster_ip': node['nutanix_config'].get('cluster_ip'),
                'cluster_netmask': '255.255.255.0',
                'data_services_ip': node['nutanix_config'].get('cluster_ip')
            }
        }
        
        return network_config