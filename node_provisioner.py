"""
Node provisioning service for Nutanix PXE/Config Server
Updated to use Config class and integrated with CleanupService
"""
import ipaddress
import base64
import json
import logging
from datetime import datetime, timedelta
from database import Database
from ibm_cloud_client import IBMCloudClient
from config import Config

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
            
            # Reserve cluster IP if this is the first node
            if self.db.is_first_node():
                cluster_ip = self.get_next_available_ip(
                    mgmt_subnet['ipv4_cidr_block'], 
                    'cluster', 
                    mgmt_reserved_ips + [mgmt_ip, ahv_ip, cvm_ip]
                )
                ip_allocation['cluster'] = self.ibm_cloud.create_subnet_reserved_ip(
                    self.config.MANAGEMENT_SUBNET_ID,
                    cluster_ip,
                    f"cluster01"
                )
            else:
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
            
            # Cluster DNS (if first node)
            if ip_allocation.get('cluster'):
                cluster_record = self.ibm_cloud.create_dns_record(
                    'A',
                    "cluster01",
                    ip_allocation['cluster']['ip_address']
                )
                dns_records.append(cluster_record)
            
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
            
            # Create workload VNI
            workload_vni = self.ibm_cloud.create_virtual_network_interface(
                self.config.WORKLOAD_SUBNET_ID,
                f"{node_config['node_name']}-workload-vni",
                ip_allocation['workload']['reservation_id'],
                [self.config.WORKLOAD_SECURITY_GROUP_ID]
            )
            vnis['workload_vni'] = workload_vni
            
            # Store VNI info for cleanup
            self.db.store_vnic_info(node_config['node_name'], vnis)
            
            logger.info(f"VNI creation completed for {node_config['node_name']}")
            return vnis
            
        except Exception as e:
            # Cleanup any successful VNIs before re-raising
            logger.error(f"VNI creation failed for {node_config['node_name']}, initiating cleanup")
            self._cleanup_partial_vnis(vnis)
            raise Exception(f"VNI creation failed: {str(e)}")
    
    def _cleanup_partial_vnis(self, vnis):
        """Clean up partially created VNIs when creation fails"""
        for vni_type, vni_info in vnis.items():
            try:
                self.ibm_cloud.delete_virtual_network_interface(vni_info['id'])
                logger.info(f"Cleaned up VNI: {vni_info['name']}")
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup VNI {vni_info['name']}: {str(cleanup_error)}")
    
    def update_config_database(self, node_data, ip_allocation, vnis):
        """Update configuration database with new node"""
        logger.info(f"Updating database for {node_data['node_config']['node_name']}")
        
        node_config = {
            'node_name': node_data['node_config']['node_name'],
            'server_profile': node_data['node_config']['server_profile'],
            'cluster_role': node_data['node_config']['cluster_role'],
            'deployment_status': 'provisioning',
            'management_vni': {
                'vni_id': vnis['management_vni']['id'],
                'ip': ip_allocation['management']['ip_address'],
                'dns_name': f"{node_data['node_config']['node_name']}-mgmt.{self.config.DNS_ZONE_NAME}"
            },
            'workload_vni': {
                'vni_id': vnis['workload_vni']['id'],
                'ip': ip_allocation['workload']['ip_address'],
                'dns_name': f"{node_data['node_config']['node_name']}-workload.{self.config.DNS_ZONE_NAME}"
            },
            'nutanix_config': {
                'ahv_ip': ip_allocation['ahv']['ip_address'],
                'ahv_dns': f"{node_data['node_config']['node_name']}-ahv.{self.config.DNS_ZONE_NAME}",
                'cvm_ip': ip_allocation['cvm']['ip_address'],
                'cvm_dns': f"{node_data['node_config']['node_name']}-cvm.{self.config.DNS_ZONE_NAME}",
                'cluster_ip': ip_allocation.get('cluster', {}).get('ip_address'),
                'cluster_dns': f'cluster01.{self.config.DNS_ZONE_NAME}' if ip_allocation.get('cluster') else None,
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
        """Deploy the bare metal server with custom iPXE image"""
        logger.info(f"Deploying bare metal server for node ID {node_id}")
        
        node_config = self.db.get_node(node_id)
        
        try:
            # Get custom iPXE image
            ipxe_image = self.ibm_cloud.get_custom_image_by_name('nutanix-ipxe-boot')
            
            # Generate user data
            user_data = self.generate_user_data(node_id)
            
            # Deploy bare metal server with VNIs
            deployment_result = self.ibm_cloud.create_bare_metal_server(
                name=node_config['node_name'],
                profile=node_config['server_profile'],
                image_id=ipxe_image['id'],
                primary_vni_id=vnis['management_vni']['id'],
                ssh_key_ids=[self.config.SSH_KEY_ID],
                additional_vnis=[vnis['workload_vni']],
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
        user_data = {
            'node_id': node_id,
            'pxe_server': self.config.PXE_SERVER_DNS,
            'config_endpoint': f'http://{self.config.PXE_SERVER_DNS}:8081/server-config'
        }
        
        return base64.b64encode(json.dumps(user_data).encode()).decode()
    
    def start_deployment_monitoring(self, node_id):
        """Initialize deployment monitoring for the node"""
        self.db.log_deployment_event(
            node_id, 
            'monitoring_start', 
            'success', 
            'Deployment monitoring initialized'
        )
        logger.info(f"Monitoring started for node {node_id}")
    
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