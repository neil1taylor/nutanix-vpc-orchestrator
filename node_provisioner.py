"""
Node provisioning service for Nutanix PXE/Config Server
Updated to use Config class and integrated with CleanupService
"""
import ipaddress
import base64
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from database import Database
from ibm_cloud_client import IBMCloudClient
from config import Config
from server_profiles import ServerProfileConfig

logger = logging.getLogger(__name__)

class NodeProvisioner:
    def __init__(self):
        self.db = Database()
        self.ibm_cloud = IBMCloudClient()
        self.config = Config
        
        # Import cleanup service for error handling
        from cleanup_service import CleanupService
        self.cleanup_service = CleanupService()
        
        # Validate required configuration
        self.config.validate_required_config()
        
        logger.info("NodeProvisioner initialized with Config class and CleanupService")
    
    def provision_node(self, node_request):
        """Main node provisioning orchestration"""
        node_name = node_request['node_config']['node_name']
        
        try:
            logger.info(f"Starting provisioning for node {node_name}")
            
            # Step 0: Check if node with same name already exists and is successfully provisioned
            existing_node = self.db.get_node_by_name(node_name)
            logger.info(f"Checking for existing node with name {node_name}: {existing_node}")
            if existing_node:
                logger.info(f"Existing node found with status: {existing_node['deployment_status']}")
                if existing_node['deployment_status'] not in ['cleanup_completed', 'failed']:
                    raise Exception(f"Node with name {node_name} already exists and is in status {existing_node['deployment_status']}")
                # If node is in cleanup_completed or failed status, we can proceed with provisioning
                logger.info(f"Proceeding with provisioning as existing node is in {existing_node['deployment_status']} status")
            
            # Step 1: Reserve IP addresses
            ip_allocation = self.reserve_node_ips(node_request['node_config'])
            
            # Step 2: Register DNS records
            dns_records = self.register_node_dns(ip_allocation, node_request['node_config'])
            
            # Step 3: Create Virtual Network Interfaces (VNIs)
            vnis = self.create_node_vnis(ip_allocation, node_request['node_config'])
            
            # Step 4: Update configuration database
            node_id = self.update_config_database(node_request, ip_allocation, vnis)
            
            # Step 5: Deploy bare metal server
            deployment_result = self.deploy_bare_metal_server(node_id, vnis, node_request)
            
            # Step 6: Initialize monitoring
            self.start_deployment_monitoring(node_id)
            
            return {
                'node_id': node_id,
                'deployment_id': deployment_result['id'],
                'estimated_completion': self.calculate_completion_time(),
                'monitoring_endpoint': f'/api/status/nodes/{node_id}'
            }
            
        except Exception as e:
            logger.error(f"Node provisioning failed for {node_name}: {str(e)}")
            
            # Trigger comprehensive cleanup using CleanupService
            try:
                logger.info(f"Initiating cleanup for failed provisioning: {node_name}")
                cleanup_result = self.cleanup_service.cleanup_failed_provisioning(node_name)
                
                if cleanup_result.get('success'):
                    logger.info(f"Cleanup completed successfully for {node_name}")
                else:
                    logger.error(f"Cleanup failed for {node_name}: {cleanup_result.get('error', 'Unknown cleanup error')}")
                    
            except Exception as cleanup_error:
                logger.error(f"Cleanup service failed for {node_name}: {str(cleanup_error)}")
            
            raise
    
    def reserve_node_ips(self, node_config):
        """Reserve IP addresses for all node components"""
        logger.info(f"Reserving IPs for node {node_config['node_name']}")
        
        # Get subnet information
        mgmt_subnet = self.ibm_cloud.get_subnet_info(self.config.MANAGEMENT_SUBNET_ID)
        workload_subnet = self.ibm_cloud.get_subnet_info(self.config.WORKLOAD_SUBNET_ID)
        
        # Get existing reserved IPs to avoid conflicts
        mgmt_reserved_ips = self.ibm_cloud.get_subnet_reserved_ips(self.config.MANAGEMENT_SUBNET_ID)
        workload_reserved_ips = self.ibm_cloud.get_subnet_reserved_ips(self.config.WORKLOAD_SUBNET_ID)
        
        ip_allocation = {}
        
        try:
            # Reserve management interface IP
            mgmt_ip = self.get_next_available_ip(
                mgmt_subnet['ipv4_cidr_block'], 
                'management', 
                mgmt_reserved_ips
            )
            ip_allocation['management'] = self.ibm_cloud.create_subnet_reserved_ip(
                self.config.MANAGEMENT_SUBNET_ID,
                mgmt_ip,
                f"{node_config['node_name']}-mgmt"
            )
            
            # Reserve AHV IP
            ahv_ip = self.get_next_available_ip(
                mgmt_subnet['ipv4_cidr_block'], 
                'ahv', 
                mgmt_reserved_ips + [mgmt_ip]
            )
            ip_allocation['ahv'] = self.ibm_cloud.create_subnet_reserved_ip(
                self.config.MANAGEMENT_SUBNET_ID,
                ahv_ip,
                f"{node_config['node_name']}-ahv"
            )
            
            # Reserve CVM IP
            cvm_ip = self.get_next_available_ip(
                mgmt_subnet['ipv4_cidr_block'], 
                'cvm', 
                mgmt_reserved_ips + [mgmt_ip, ahv_ip]
            )
            ip_allocation['cvm'] = self.ibm_cloud.create_subnet_reserved_ip(
                self.config.MANAGEMENT_SUBNET_ID,
                cvm_ip,
                f"{node_config['node_name']}-cvm"
            )
            
            # Reserve workload interface IP
            workload_ip = self.get_next_available_ip(
                workload_subnet['ipv4_cidr_block'], 
                'workload', 
                workload_reserved_ips
            )
            ip_allocation['workload'] = self.ibm_cloud.create_subnet_reserved_ip(
                self.config.WORKLOAD_SUBNET_ID,
                workload_ip,
                f"{node_config['node_name']}-workload"
            )
            
            ip_allocation['cluster'] = None
            
            # Store reservations for cleanup if needed
            self.db.store_ip_reservations(node_config['node_name'], ip_allocation)
            
            logger.info(f"IP reservation completed for {node_config['node_name']}")
            return ip_allocation
            
        except Exception as e:
            # Cleanup any successful reservations before re-raising
            logger.error(f"IP reservation failed for {node_config['node_name']}, initiating cleanup")
            self._cleanup_partial_ip_allocation(ip_allocation)
            raise Exception(f"IP reservation failed: {str(e)}")
    
    def _cleanup_partial_ip_allocation(self, ip_allocation):
        """Clean up partially allocated IPs when reservation fails"""
        for ip_type, ip_info in ip_allocation.items():
            if ip_info:
                try:
                    subnet_id = self.config.MANAGEMENT_SUBNET_ID if ip_type != 'workload' else self.config.WORKLOAD_SUBNET_ID
                    self.ibm_cloud.delete_subnet_reserved_ip(subnet_id, ip_info['reservation_id'])
                    logger.info(f"Cleaned up IP reservation for {ip_type}: {ip_info['ip_address']}")
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup IP reservation for {ip_type}: {str(cleanup_error)}")
    
    def get_next_available_ip(self, subnet_cidr, ip_type, existing_ips):
        """Get next available IP in the specified range"""
        subnet = ipaddress.IPv4Network(subnet_cidr)
        start_range, end_range = self.config.IP_RANGES[ip_type]
        
        for i in range(start_range, end_range + 1):
            candidate_ip = str(subnet.network_address + i)
            if candidate_ip not in existing_ips:
                return candidate_ip
        
        raise Exception(f"No available IPs in range for {ip_type}")
    
    def register_node_dns(self, ip_allocation, node_config):
        """Register DNS records for all node components"""
        logger.info(f"Registering DNS records for {node_config['node_name']}")
        
        node_name = node_config['node_name']
        dns_records = []
        
        try:
            # Management interface DNS
            mgmt_record = self.ibm_cloud.create_dns_record(
                'A',
                f"{node_name}-mgmt",
                ip_allocation['management']['ip_address']
            )
            dns_records.append(mgmt_record)
            
            # AHV interface DNS
            ahv_record = self.ibm_cloud.create_dns_record(
                'A',
                f"{node_name}-ahv",
                ip_allocation['ahv']['ip_address']
            )
            dns_records.append(ahv_record)
            
            # CVM interface DNS
            cvm_record = self.ibm_cloud.create_dns_record(
                'A',
                f"{node_name}-cvm",
                ip_allocation['cvm']['ip_address']
            )
            dns_records.append(cvm_record)
            
            # Workload interface DNS
            workload_record = self.ibm_cloud.create_dns_record(
                'A',
                f"{node_name}-workload",
                ip_allocation['workload']['ip_address']
            )
            dns_records.append(workload_record)
            
            # No cluster DNS record creation
            
            # Store DNS records for cleanup
            self.db.store_dns_records(node_config['node_name'], dns_records)
            
            logger.info(f"DNS registration completed for {node_config['node_name']}")
            return dns_records
            
        except Exception as e:
            # Cleanup any successful DNS records before re-raising
            logger.error(f"DNS registration failed for {node_config['node_name']}, initiating cleanup")
            logger.error(f"Error details: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            self._cleanup_partial_dns_records(dns_records)
            raise Exception(f"DNS registration failed: {str(e)}")
    
    def _cleanup_partial_dns_records(self, dns_records):
        """Clean up partially created DNS records when registration fails"""
        for record in dns_records:
            try:
                self.ibm_cloud.delete_dns_record(record['id'])
                logger.info(f"Cleaned up DNS record: {record['name']}")
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup DNS record {record['name']}: {str(cleanup_error)}")
    
    def create_node_vnis(self, ip_allocation, node_config):
        """Create Virtual Network Interfaces (VNIs) for the bare metal server"""
        logger.info(f"Creating VNIs for {node_config['node_name']}")
        
        vnis = {}
        
        try:
            # Create management VNI
            mgmt_vni = self.ibm_cloud.create_virtual_network_interface(
                self.config.MANAGEMENT_SUBNET_ID,
                f"{node_config['node_name']}-mgmt-vni",
                ip_allocation['management']['reservation_id'],
                [self.config.MANAGEMENT_SECURITY_GROUP_ID, self.config.INTRA_NODE_SECURITY_GROUP_ID]
            )
            vnis['management_vni'] = mgmt_vni
            
            # Get workload subnets from node config or use default
            workload_subnets = node_config.get('network_config', {}).get('workload_subnets', [])
            if not workload_subnets:
                # Use default workload subnet if none specified
                workload_subnets = [self.config.WORKLOAD_SUBNET_ID]
            
            # Create workload VNIs for each subnet
            workload_vnis = []
            for i, subnet_id in enumerate(workload_subnets):
                workload_vni = self.ibm_cloud.create_virtual_network_interface(
                    subnet_id,
                    f"{node_config['node_name']}-workload-vni-{i+1}",
                    ip_allocation['workload']['reservation_id'],
                    [self.config.WORKLOAD_SECURITY_GROUP_ID]
                )
                workload_vnis.append(workload_vni)
            
            # Store first workload VNI as primary for backward compatibility
            vnis['workload_vni'] = workload_vnis[0] if workload_vnis else None
            # Store all workload VNIs
            vnis['workload_vnis'] = workload_vnis
            
            # Store VNI info for cleanup
            self.db.store_vnic_info(node_config['node_name'], vnis)
            
            logger.info(f"VNI creation completed for {node_config['node_name']}")
            return vnis
            
        except Exception as e:
            # Log the VNI information for debugging
            logger.error(f"VNI creation failed for {node_config['node_name']}, VNI info: {vnis}")
            # Cleanup any successful VNIs before re-raising
            logger.error(f"VNI creation failed for {node_config['node_name']}, initiating cleanup")
            try:
                self._cleanup_partial_vnis(vnis)
                logger.info(f"VNI cleanup completed for {node_config['node_name']}")
            except Exception as cleanup_error:
                logger.error(f"VNI cleanup also failed for {node_config['node_name']}: {str(cleanup_error)}")
                logger.error("WARNING: Orphaned VNIs may exist in IBM Cloud that need manual cleanup")
            raise Exception(f"VNI creation failed: {str(e)}")
    
    def _cleanup_partial_vnis(self, vnis):
        """Clean up partially created VNIs when creation fails"""
        for vni_type, vni_info in vnis.items():
            # Handle list of VNIs (e.g., workload_vnis)
            if isinstance(vni_info, list):
                for vni in vni_info:
                    self._delete_single_vni(vni)
            else:
                # Handle single VNI
                self._delete_single_vni(vni_info)
    
    def _delete_single_vni(self, vni_info):
        """Delete a single VNI with proper error handling"""
        try:
            # Check if vni_info is valid
            if not vni_info or not isinstance(vni_info, dict):
                logger.warning(f"Invalid VNI info provided for cleanup: {vni_info}")
                return
                
            # Check if required fields exist
            if 'id' not in vni_info or 'name' not in vni_info:
                logger.warning(f"VNI info missing required fields (id/name): {vni_info}")
                return
            
            # First check if the VNI exists
            try:
                self.ibm_cloud.get_virtual_network_interface(vni_info['id'])
                logger.info(f"Found existing VNI {vni_info['name']}, proceeding with cleanup")
            except Exception as check_error:
                error_str = str(check_error).lower()
                if "404" in error_str or "not found" in error_str:
                    logger.info(f"VNI {vni_info['name']} not found (404), no cleanup needed")
                    return
                else:
                    logger.warning(f"Error checking VNI {vni_info['name']} existence: {str(check_error)}, proceeding with deletion attempt")
            
            # Attempt deletion
            self.ibm_cloud.delete_virtual_network_interfaces(vni_info['id'])
            logger.info(f"Successfully cleaned up VNI: {vni_info['name']}")
        except Exception as cleanup_error:
            error_str = str(cleanup_error).lower()
            if "404" in error_str or "not found" in error_str:
                logger.info(f"VNI {vni_info.get('name', 'unknown')} not found during deletion, cleanup successful")
            else:
                logger.error(f"Failed to cleanup VNI {vni_info.get('name', 'unknown')}: {str(cleanup_error)}")
                logger.error(f"VNI info: {json.dumps(vni_info, indent=2, default=str)}")
            if "not found" in str(cleanup_error).lower():
                logger.warning(f"VNI {vni_info['name']} not found - skipping deletion")
    
    def update_config_database(self, node_data, ip_allocation, vnis):
        """Update configuration database with new node"""
        logger.info(f"Updating database for {node_data['node_config']['node_name']}")
        
        # Prepare workload VNIs data
        workload_vnics_data = {}
        if 'workload_vnis' in vnis:
            workload_vnics_data = {
                f"workload_vni_{i+1}": {
                    'vnic_id': vni['id'],
                    'ip': ip_allocation['workload']['ip_address'],  # Same IP for all workload interfaces
                    'dns_name': f"{node_data['node_config']['node_name']}-workload-{i+1}.{self.config.DNS_ZONE_NAME}",
                    'subnet_id': vni.get('subnet_id', '')
                }
                for i, vni in enumerate(vnis['workload_vnis'])
            }
        
        node_config = {
            'node_name': node_data['node_config']['node_name'],
            'server_profile': node_data['node_config']['server_profile'],
            'deployment_status': 'provisioning',
            'management_vnic': {
                'vnic_id': vnis['management_vni']['id'],
                'ip': ip_allocation['management']['ip_address'],
                'dns_name': f"{node_data['node_config']['node_name']}-mgmt.{self.config.DNS_ZONE_NAME}"
            },
            'workload_vnic': {
                'vnic_id': vnis['workload_vni']['id'],
                'ip': ip_allocation['workload']['ip_address'],
                'dns_name': f"{node_data['node_config']['node_name']}-workload.{self.config.DNS_ZONE_NAME}"
            },
            'workload_vnics': workload_vnics_data,
            'nutanix_config': {
                'ahv_ip': ip_allocation['ahv']['ip_address'],
                'ahv_dns': f"{node_data['node_config']['node_name']}-ahv.{self.config.DNS_ZONE_NAME}",
                'cvm_ip': ip_allocation['cvm']['ip_address'],
                'cvm_dns': f"{node_data['node_config']['node_name']}-cvm.{self.config.DNS_ZONE_NAME}",
                'storage_config': node_data['node_config'].get('storage_config', {})
            }
        }
        
        # Insert into database
        node_id = self.db.insert_node(node_config)
        
        # Initialize deployment tracking
        self.db.log_deployment_event(node_id, 'provisioning', 'success', 'Node configuration created')
        
        logger.info(f"Database update completed for node ID {node_id}")
        return node_id
    
    def deploy_bare_metal_server(self, node_id, vnis, node_data):
        """Deploy the bare metal server with IBM Cloud iPXE image"""
        logger.info(f"Deploying bare metal server for node ID {node_id}")
        
        node_config = self.db.get_node(node_id)
        
        try:
            # Get custom iPXE image
            ipxe_image = self.ibm_cloud.get_custom_image(self.config.IPXE_IMAGE_ID)
            
            # Generate user data
            user_data = self.generate_user_data(node_id)
            
            # Deploy bare metal server with VNIs
            deployment_result = self.ibm_cloud.create_bare_metal_server(
                name=node_config['node_name'],
                profile=node_config['server_profile'],
                image_id=ipxe_image['id'],
                primary_vni_id=vnis['management_vni']['id'],
                ssh_key_ids=[self.config.SSH_KEY_ID],
                additional_vnis=vnis.get('workload_vnis', [vnis['workload_vni']]) if vnis.get('workload_vni') else [],
                user_data=user_data
            )
            
            # Update database with deployment info
            self.db.update_node_deployment_info(
                node_id,
                deployment_result['id'],
                'deploying'
            )
            
            self.db.log_deployment_event(
                node_id, 
                'bare_metal_deploy', 
                'success', 
                f"Bare metal server {deployment_result['id']} deployment initiated"
            )
            
            logger.info(f"Bare metal deployment initiated for node {node_id}")
            return deployment_result
            
        except Exception as e:
            self.db.log_deployment_event(
                node_id, 
                'bare_metal_deploy', 
                'failed', 
                f"Deployment failed: {str(e)}"
            )
            raise Exception(f"Bare metal deployment failed: {str(e)}")
    
    def generate_user_data(self, node_id):
        """Generate user data for server initialization"""
        # Get node information
        node = self.db.get_node(node_id)
        if not node:
            raise Exception(f"Node with ID {node_id} not found")
        
        # Create URL for iPXE boot script with node_id only
        user_data = f"http://{self.config.PXE_SERVER_DNS}:8080/boot/config?node_id={node_id}"
        
        return user_data
    
    def start_deployment_monitoring(self, node_id):
        """Initialize deployment monitoring for the node"""
        try:
            # Get node information for better logging
            node = self.db.get_node(node_id)
            node_name = node['node_name'] if node else f"Node {node_id}"
            
            # Log with high visibility
            logger.info(f"🚀 MONITORING INITIALIZATION: Starting deployment monitoring for {node_name}")
            
            self.db.log_deployment_event(
                node_id,
                'monitoring_start',
                'success',
                'Deployment monitoring initialized'
            )
            
            # Start IBM Cloud status monitoring in a separate thread to avoid blocking
            monitor_thread = threading.Thread(
                target=self._start_monitoring_with_retry,
                args=(node_id,),
                daemon=True,
                name=f"monitor-{node_id}"
            )
            monitor_thread.start()
            
            logger.info(f"🧵 THREAD STARTED: Background monitoring thread launched for {node_name}")
        except Exception as e:
            logger.error(f"❌ MONITORING ERROR: Failed to start monitoring for node {node_id}: {str(e)}")
            # Log full traceback for debugging
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
    
    def _start_monitoring_with_retry(self, node_id):
        """Start monitoring with retry logic to handle potential errors"""
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.info(f"🔄 MONITORING ATTEMPT #{retry_count+1}: Starting server status monitoring for node {node_id}")
                self.monitor_server_status(node_id)
                # If successful, break out of the retry loop
                break
            except Exception as e:
                retry_count += 1
                logger.error(f"❌ MONITORING ERROR (Attempt #{retry_count}): {str(e)}")
                if retry_count < max_retries:
                    # Wait before retrying (exponential backoff)
                    wait_time = 5 * (2 ** retry_count)
                    logger.info(f"⏳ RETRY: Will retry monitoring in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ MONITORING FAILED: All {max_retries} attempts to start monitoring for node {node_id} failed")
    
    def monitor_server_status(self, node_id):
        """Monitor IBM Cloud server status and log state transitions"""
        try:
            # Get node information
            node = self.db.get_node(node_id)
            if not node:
                logger.warning(f"⚠️ NODE NOT FOUND: Cannot monitor server status for node {node_id}")
                return
                
            logger.info(f"🔍 MONITOR DETAILS: Node ID: {node_id}, Name: {node['node_name']}, Bare Metal ID: {node.get('bare_metal_id', 'None')}")
                
            # For existing nodes that might not have bare_metal_id yet
            if not node.get('bare_metal_id'):
                logger.warning(f"⏳ WAITING FOR ID: Node {node_id} ({node['node_name']}) doesn't have bare_metal_id yet")
                
                # Check if deployment_status indicates the server has been requested
                if node.get('deployment_status') in ['provisioning', 'deploying', 'bare_metal_deploy_success']:
                    logger.info(f"🔄 DEPLOYMENT IN PROGRESS: Node {node['node_name']} is in {node.get('deployment_status')} state")
                    
                    # Start a thread to wait for bare_metal_id to be assigned and then monitor
                    wait_thread = threading.Thread(
                        target=self._wait_for_bare_metal_id_and_monitor,
                        args=(node_id,),
                        daemon=True,
                        name=f"wait-{node_id}"
                    )
                    wait_thread.start()
                    logger.info(f"🧵 WAIT THREAD STARTED: Waiting for bare_metal_id assignment for {node['node_name']}")
                else:
                    logger.warning(f"⚠️ UNEXPECTED STATE: Node {node['node_name']} is in {node.get('deployment_status')} state, not waiting for bare_metal_id")
                return
                
            # Get current server status from IBM Cloud
            try:
                logger.info(f"🔍 FETCHING STATUS: Getting status for server {node['bare_metal_id']} ({node['node_name']})")
                server_info = self.ibm_cloud.get_bare_metal_server(node['bare_metal_id'])
                current_status = server_info.get('status', 'unknown')
                logger.info(f"📊 SERVER INFO: {json.dumps(server_info, indent=2, default=str)[:500]}...")
            except Exception as server_error:
                logger.error(f"❌ SERVER INFO ERROR: Error getting server info: {str(server_error)}")
                # Log full traceback for debugging
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                current_status = 'unknown'
            
            # Log initial status with high visibility
            logger.info(f"⚙️ INITIAL STATUS: Server {node['node_name']} IBM Cloud status is {current_status.upper()}")
            
            # Update status in status monitor
            try:
                from status_monitor import StatusMonitor
                status_monitor = StatusMonitor()
                logger.info(f"📝 UPDATING STATUS: Sending status update for {node['node_name']}: {current_status}")
                status_monitor.update_deployment_phase({
                    'server_ip': str(node['management_ip']),
                    'phase': 'ibm_cloud_status',
                    'status': 'in_progress',
                    'message': f"Server status: {current_status}",
                    'server_status': current_status
                })
                logger.info(f"✅ STATUS UPDATED: Status update sent for {node['node_name']}")
            except Exception as status_error:
                logger.error(f"❌ STATUS UPDATE ERROR: Failed to update status: {str(status_error)}")
                # Log full traceback for debugging
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Start a background thread to continuously monitor the server status
            monitor_thread = threading.Thread(
                target=self._continuous_status_monitoring,
                args=(node_id, node['bare_metal_id'], current_status),
                daemon=True,
                name=f"continuous-{node_id}"
            )
            monitor_thread.start()
            
            # Log all active threads for debugging
            all_threads = threading.enumerate()
            thread_names = [t.name for t in all_threads]
            logger.info(f"🧵 ACTIVE THREADS: {len(all_threads)} threads running: {thread_names}")
            
            logger.info(f"🔍 MONITORING STARTED: Background thread for {node['node_name']} status monitoring is running")
        except Exception as e:
            logger.error(f"❌ MONITORING ERROR: Error starting server status monitoring for node {node_id}: {str(e)}")
            # Log full traceback for debugging
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
    
    def _wait_for_bare_metal_id_and_monitor(self, node_id):
        """Wait for bare_metal_id to be assigned and then start monitoring"""
        try:
            # Get initial node info for better logging
            initial_node = self.db.get_node(node_id)
            node_name = initial_node['node_name'] if initial_node else f"Node {node_id}"
            
            logger.info(f"⏳ WAIT STARTED: Waiting for bare_metal_id assignment for {node_name}")
            
            # Wait for up to 5 minutes (300 seconds)
            for attempt in range(30):  # 30 attempts, 10 seconds each
                # Get fresh node data
                node = self.db.get_node(node_id)
                if not node:
                    logger.warning(f"⚠️ NODE MISSING: Node {node_id} no longer exists in database")
                    return
                    
                # Log every 5th attempt
                if attempt % 5 == 0:
                    logger.info(f"🔄 WAIT ATTEMPT #{attempt+1}: Checking for bare_metal_id for {node_name}")
                    logger.info(f"📊 NODE STATUS: {node_name} is in {node.get('deployment_status', 'unknown')} state")
                
                if node.get('bare_metal_id'):
                    logger.info(f"✅ ID ASSIGNED: bare_metal_id {node['bare_metal_id']} assigned to {node_name}")
                    # Start monitoring now that we have the ID
                    logger.info(f"🔄 STARTING MONITOR: Initiating status monitoring for {node_name}")
                    self.monitor_server_status(node_id)
                    return
                    
                # Wait 10 seconds before checking again
                time.sleep(10)
                
            logger.warning(f"⏱️ TIMEOUT: Timed out waiting for bare_metal_id assignment for {node_name}")
        except Exception as e:
            logger.error(f"❌ WAIT ERROR: Error in wait_for_bare_metal_id thread: {str(e)}")
            # Log full traceback for debugging
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
    
    def _continuous_status_monitoring(self, node_id, server_id, last_status):
        """Continuously monitor server status in a background thread"""
        try:
            # Get node information
            node = self.db.get_node(node_id)
            if not node:
                logger.warning(f"⚠️ NODE NOT FOUND: Cannot continue monitoring: Node {node_id} not found")
                return
                
            # Log thread info
            thread_id = threading.get_ident()
            thread_name = threading.current_thread().name
            logger.info(f"🧵 THREAD INFO: Monitoring running in thread {thread_id} ({thread_name})")
            
            logger.info(f"🔄 CONTINUOUS MONITORING: Starting for {node['node_name']} (ID: {server_id})")
            logger.info(f"📊 INITIAL STATUS: {node['node_name']} starting with status {last_status}")
            
            # Initialize status monitor
            try:
                from status_monitor import StatusMonitor
                status_monitor = StatusMonitor()
                logger.info(f"✅ STATUS MONITOR: Successfully initialized StatusMonitor")
            except Exception as sm_error:
                logger.error(f"❌ STATUS MONITOR ERROR: Failed to initialize StatusMonitor: {str(sm_error)}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                # Create a fallback status monitor
                status_monitor = None
                logger.warning(f"⚠️ FALLBACK: Will continue monitoring but status updates will not be sent")
            
            # Monitor for up to 30 minutes (1800 seconds)
            end_time = time.time() + 1800
            poll_count = 0
            
            while time.time() < end_time:
                try:
                    poll_count += 1
                    # Get current server status
                    logger.info(f"🔍 FETCHING STATUS #{poll_count}: Getting status for {node['node_name']} (ID: {server_id})")
                    server_info = self.ibm_cloud.get_bare_metal_server(server_id)
                    current_status = server_info.get('status', 'unknown')
                    
                    # Log every poll for debugging
                    logger.info(f"🔍 POLL #{poll_count}: Server {node['node_name']} status is {current_status}")
                    
                    # If status changed, log it with high visibility
                    if current_status != last_status:
                        # Use emoji indicators for better visibility in logs
                        status_emoji = "⏳"
                        if current_status == "starting":
                            status_emoji = "⚡"
                            logger.info(f"⚡⚡⚡ SERVER STARTING: {node['node_name']} is now STARTING UP")
                        elif current_status == "running":
                            status_emoji = "✅"
                            logger.info(f"✅✅✅ SERVER RUNNING: {node['node_name']} is now RUNNING")
                        elif current_status == "stopped":
                            status_emoji = "⏹️"
                            logger.info(f"⏹️⏹️⏹️ SERVER STOPPED: {node['node_name']} is now STOPPED")
                        elif current_status == "failed":
                            status_emoji = "❌"
                            logger.info(f"❌❌❌ SERVER FAILED: {node['node_name']} has FAILED")
                            
                        logger.info(f"{status_emoji} STATUS CHANGE: Server {node['node_name']} changed from {last_status.upper()} to {current_status.upper()}")
                        
                        # Update status in status monitor
                        if status_monitor:
                            try:
                                logger.info(f"📝 UPDATING STATUS: Sending status update for {node['node_name']}: {current_status}")
                                
                                # Map IBM Cloud status to appropriate deployment status
                                deployment_status = 'in_progress'
                                if current_status == 'running':
                                    deployment_status = 'success'
                                elif current_status == 'failed':
                                    deployment_status = 'failed'
                                elif current_status == 'stopped':
                                    deployment_status = 'stopped'
                                elif current_status == 'starting':
                                    deployment_status = 'starting'
                                
                                status_monitor.update_deployment_phase({
                                    'server_ip': str(node['management_ip']),
                                    'phase': 'ibm_cloud_status',
                                    'status': deployment_status,
                                    'message': f"Server status changed: {last_status} -> {current_status}",
                                    'server_status': current_status
                                })
                                logger.info(f"✅ STATUS UPDATED: Status update sent for {node['node_name']}")
                            except Exception as update_error:
                                logger.error(f"❌ STATUS UPDATE ERROR: Failed to update status: {str(update_error)}")
                                import traceback
                                logger.error(f"Full traceback: {traceback.format_exc()}")
                        else:
                            logger.warning(f"⚠️ STATUS MONITOR UNAVAILABLE: Cannot update status for {node['node_name']}")
                        
                        # Update last status
                        last_status = current_status
                        
                        # If server is running, we can stop monitoring
                        if current_status == 'running':
                            logger.info(f"✅ MONITORING COMPLETE: Server {node['node_name']} is now RUNNING, stopping continuous monitoring")
                            break
                    
                    # Sleep for 10 seconds before checking again
                    logger.info(f"⏳ WAITING: Sleeping for 10 seconds before next poll for {node['node_name']}")
                    time.sleep(10)
                    
                except Exception as poll_error:
                    logger.error(f"❌ POLL ERROR: Error polling server status: {str(poll_error)}")
                    # Log full traceback for debugging
                    import traceback
                    logger.error(f"Full traceback: {traceback.format_exc()}")
                    time.sleep(30)  # Longer sleep on error
            
            logger.info(f"🏁 MONITORING ENDED: Continuous status monitoring completed for {node['node_name']} after {poll_count} polls")
            
        except Exception as e:
            logger.error(f"❌ MONITORING ERROR: Error in continuous status monitoring thread: {str(e)}")
            # Log full traceback for debugging
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
    
    def calculate_completion_time(self):
        """Calculate estimated completion time"""
        total_timeout = sum(self.config.DEPLOYMENT_TIMEOUTS.values())
        return (datetime.now() + timedelta(seconds=total_timeout)).isoformat()
    
    def cleanup_failed_provisioning(self, node_name):
        """
        Clean up resources for a failed provisioning
        Updated to use the comprehensive CleanupService
        """
        logger.warning(f"Initiating comprehensive cleanup for failed provisioning: {node_name}")
        
        try:
            # Use the CleanupService for comprehensive cleanup
            cleanup_result = self.cleanup_service.cleanup_failed_provisioning(node_name)
            
            if cleanup_result.get('success'):
                logger.info(f"Cleanup completed successfully for {node_name}")
                logger.info(f"Cleanup summary: {cleanup_result.get('successful_operations', 0)}/{cleanup_result.get('total_operations', 0)} operations successful")
                
                # Log detailed cleanup results
                for result in cleanup_result.get('results', []):
                    resource_type = result.get('resource_type', 'unknown')
                    operations = result.get('operations', [])
                    successful_ops = len([op for op in operations if op.get('success', False)])
                    total_ops = len(operations)
                    
                    if total_ops > 0:
                        logger.info(f"Cleanup {resource_type}: {successful_ops}/{total_ops} operations successful")
                        
                        # Log any failed operations for troubleshooting
                        failed_ops = [op for op in operations if not op.get('success', False)]
                        for failed_op in failed_ops:
                            logger.error(f"Failed cleanup operation: {failed_op.get('type', 'unknown')} - {failed_op.get('message', 'No message')}")
                
                return cleanup_result
            else:
                logger.error(f"Cleanup failed for {node_name}: {cleanup_result.get('error', 'Unknown error')}")
                
                # Log partial cleanup results for troubleshooting
                if 'results' in cleanup_result:
                    logger.info("Partial cleanup results:")
                    for result in cleanup_result['results']:
                        logger.info(f"  {result.get('resource_type', 'unknown')}: {len(result.get('operations', []))} operations attempted")
                
                return cleanup_result
                
        except Exception as e:
            logger.error(f"Cleanup service failed for {node_name}: {str(e)}")
            
            # Fallback: log that manual cleanup is required
            logger.error(f"MANUAL CLEANUP REQUIRED for {node_name}")
            logger.error("Resources that may need manual cleanup:")
            logger.error("1. Bare metal server")
            logger.error("2. Virtual network interfaces")
            logger.error("3. DNS records")
            logger.error("4. IP reservations")
            logger.error("5. Database records")
            
            return {
                'success': False,
                'error': str(e),
                'node_name': node_name,
                'manual_cleanup_required': True,
                'timestamp': datetime.now().isoformat()
            }
    
    def validate_cleanup(self, node_name):
        """
        Validate that cleanup was completed successfully
        """
        try:
            validation_result = self.cleanup_service.validate_cleanup_completion(node_name)
            
            if validation_result.get('cleanup_complete'):
                logger.info(f"Cleanup validation passed for {node_name}")
            else:
                logger.warning(f"Cleanup validation found issues for {node_name}")
                
                # Log validation details
                for result in validation_result.get('validation_results', []):
                    status = result.get('status', 'UNKNOWN')
                    check = result.get('check', 'unknown')
                    message = result.get('message', 'No message')
                    
                    if status == 'FAIL':
                        logger.error(f"Validation FAILED for {check}: {message}")
                    elif status == 'ERROR':
                        logger.error(f"Validation ERROR for {check}: {message}")
                    else:
                        logger.info(f"Validation PASSED for {check}: {message}")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Cleanup validation failed for {node_name}: {str(e)}")
            return {
                'node_name': node_name,
                'cleanup_complete': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_cleanup_script(self, deployment_id):
        """
        Generate a cleanup script for manual execution
        """
        try:
            script_content = self.cleanup_service.generate_cleanup_script(deployment_id)
            logger.info(f"Generated cleanup script for deployment {deployment_id}")
            return script_content
            
        except Exception as e:
            logger.error(f"Failed to generate cleanup script for deployment {deployment_id}: {str(e)}")
            return f"""#!/bin/bash
# Error generating cleanup script for deployment {deployment_id}
# Error: {str(e)}

echo "Error generating cleanup script"
echo "Please perform manual cleanup in IBM Cloud console"
"""
    
    def cleanup_orphaned_resources(self, max_age_hours=24):
        """
        Clean up orphaned resources from failed deployments
        """
        try:
            cleanup_result = self.cleanup_service.cleanup_orphaned_resources(max_age_hours)
            
            if cleanup_result.get('success'):
                logger.info(f"Orphaned resource cleanup completed: {cleanup_result.get('orphaned_nodes_cleaned', 0)} nodes cleaned")
            else:
                logger.error(f"Orphaned resource cleanup failed: {cleanup_result.get('error', 'Unknown error')}")
            
            return cleanup_result
            
        except Exception as e:
            logger.error(f"Orphaned resource cleanup failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }