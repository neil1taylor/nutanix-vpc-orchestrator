"""
Node provisioning service for Nutanix PXE/Config Server
Updated to use Virtual Network Interfaces (VNI) and proper SDK methods
Configuration loaded from environment variables set by cloud-init
"""
import os
import ipaddress
import base64
import json
import logging
from database import Database
from ibm_cloud_client import IBMCloudClient

logger = logging.getLogger(__name__)

class NodeProvisioner:
    def __init__(self):
        self.db = Database()
        self.ibm_cloud = IBMCloudClient()
        
        # Load configuration from environment variables
        self.load_config_from_env()
    
    def load_config_from_env(self):
        """Load configuration from environment variables"""
        # Required environment variables
        required_vars = [
            'MANAGEMENT_SUBNET_ID', 'WORKLOAD_SUBNET_ID', 'DNS_ZONE_NAME',
            'MANAGEMENT_SECURITY_GROUP_ID', 'WORKLOAD_SECURITY_GROUP_ID',
            'INTRA_NODE_SECURITY_GROUP_ID', 'PXE_SERVER_DNS', 'SSH_KEY_ID'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        # Load configuration
        self.MANAGEMENT_SUBNET_ID = os.getenv('MANAGEMENT_SUBNET_ID')
        self.WORKLOAD_SUBNET_ID = os.getenv('WORKLOAD_SUBNET_ID')
        self.DNS_ZONE_NAME = os.getenv('DNS_ZONE_NAME')
        self.MANAGEMENT_SECURITY_GROUP_ID = os.getenv('MANAGEMENT_SECURITY_GROUP_ID')
        self.WORKLOAD_SECURITY_GROUP_ID = os.getenv('WORKLOAD_SECURITY_GROUP_ID')
        self.INTRA_NODE_SECURITY_GROUP_ID = os.getenv('INTRA_NODE_SECURITY_GROUP_ID')
        self.PXE_SERVER_DNS = os.getenv('PXE_SERVER_DNS')
        self.SSH_KEY_ID = os.getenv('SSH_KEY_ID')
        
        # Optional configuration with defaults
        self.IP_RANGES = {
            'management': (int(os.getenv('MGMT_IP_START', '10')), int(os.getenv('MGMT_IP_END', '50'))),
            'ahv': (int(os.getenv('AHV_IP_START', '51')), int(os.getenv('AHV_IP_END', '100'))),
            'cvm': (int(os.getenv('CVM_IP_START', '101')), int(os.getenv('CVM_IP_END', '150'))),
            'workload': (int(os.getenv('WORKLOAD_IP_START', '10')), int(os.getenv('WORKLOAD_IP_END', '200'))),
            'cluster': (int(os.getenv('CLUSTER_IP_START', '200')), int(os.getenv('CLUSTER_IP_END', '210')))
        }
        
        self.DEPLOYMENT_TIMEOUTS = {
            'ip_reservation': int(os.getenv('TIMEOUT_IP_RESERVATION', '300')),
            'dns_registration': int(os.getenv('TIMEOUT_DNS_REGISTRATION', '180')),
            'vni_creation': int(os.getenv('TIMEOUT_VNI_CREATION', '600')),
            'server_deployment': int(os.getenv('TIMEOUT_SERVER_DEPLOYMENT', '1800')),
            'total_deployment': int(os.getenv('TIMEOUT_TOTAL_DEPLOYMENT', '3600'))
        }
        
        logger.info("Configuration loaded from environment variables")
    
    def provision_node(self, node_request):
        """Main node provisioning orchestration"""
        try:
            logger.info(f"Starting provisioning for node {node_request['node_config']['node_name']}")
            
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
                'monitoring_endpoint': f'/api/v1/nodes/{node_id}/status'
            }
            
        except Exception as e:
            logger.error(f"Node provisioning failed: {str(e)}")
            # Cleanup on failure
            try:
                self.cleanup_failed_provisioning(node_request['node_config']['node_name'])
            except:
                pass  # Don't fail on cleanup errors
            raise
    
    def reserve_node_ips(self, node_config):
        """Reserve IP addresses for all node components"""
        logger.info(f"Reserving IPs for node {node_config['node_name']}")
        
        # Get subnet information
        mgmt_subnet = self.ibm_cloud.get_subnet_info(self.MANAGEMENT_SUBNET_ID)
        workload_subnet = self.ibm_cloud.get_subnet_info(self.WORKLOAD_SUBNET_ID)
        
        # Get existing reserved IPs to avoid conflicts
        mgmt_reserved_ips = self.ibm_cloud.get_subnet_reserved_ips(self.MANAGEMENT_SUBNET_ID)
        workload_reserved_ips = self.ibm_cloud.get_subnet_reserved_ips(self.WORKLOAD_SUBNET_ID)
        
        ip_allocation = {}
        
        try:
            # Reserve management interface IP
            mgmt_ip = self.get_next_available_ip(
                mgmt_subnet['ipv4_cidr_block'], 
                'management', 
                mgmt_reserved_ips
            )
            ip_allocation['management'] = self.ibm_cloud.create_subnet_reserved_ip(
                self.MANAGEMENT_SUBNET_ID,
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
                self.MANAGEMENT_SUBNET_ID,
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
                self.MANAGEMENT_SUBNET_ID,
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
                self.WORKLOAD_SUBNET_ID,
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
                    self.MANAGEMENT_SUBNET_ID,
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
            # Cleanup any successful reservations
            for ip_type, ip_info in ip_allocation.items():
                if ip_info:
                    try:
                        subnet_id = self.MANAGEMENT_SUBNET_ID if ip_type != 'workload' else self.WORKLOAD_SUBNET_ID
                        self.ibm_cloud.delete_subnet_reserved_ip(subnet_id, ip_info['reservation_id'])
                    except:
                        pass
            raise Exception(f"IP reservation failed: {str(e)}")
    
    def get_next_available_ip(self, subnet_cidr, ip_type, existing_ips):
        """Get next available IP in the specified range"""
        subnet = ipaddress.IPv4Network(subnet_cidr)
        start_range, end_range = self.IP_RANGES[ip_type]
        
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
            # Cleanup any successful DNS records
            for record in dns_records:
                try:
                    self.ibm_cloud.delete_dns_record(record['id'])
                except:
                    pass
            raise Exception(f"DNS registration failed: {str(e)}")
    
    def create_node_vnis(self, ip_allocation, node_config):
        """Create Virtual Network Interfaces (VNIs) for the bare metal server"""
        logger.info(f"Creating VNIs for {node_config['node_name']}")
        
        vnis = {}
        
        try:
            # Create management VNI
            mgmt_vni = self.ibm_cloud.create_virtual_network_interface(
                self.MANAGEMENT_SUBNET_ID,
                f"{node_config['node_name']}-mgmt-vni",
                ip_allocation['management']['reservation_id'],
                [self.MANAGEMENT_SECURITY_GROUP_ID, self.INTRA_NODE_SECURITY_GROUP_ID]
            )
            vnis['management_vni'] = mgmt_vni
            
            # Create workload VNI
            workload_vni = self.ibm_cloud.create_virtual_network_interface(
                self.WORKLOAD_SUBNET_ID,
                f"{node_config['node_name']}-workload-vni",
                ip_allocation['workload']['reservation_id'],
                [self.WORKLOAD_SECURITY_GROUP_ID]
            )
            vnis['workload_vni'] = workload_vni
            
            # Store VNI info for cleanup
            self.db.store_vni_info(node_config['node_name'], vnis)
            
            logger.info(f"VNI creation completed for {node_config['node_name']}")
            return vnis
            
        except Exception as e:
            # Cleanup any successful VNIs
            for vni_type, vni_info in vnis.items():
                try:
                    self.ibm_cloud.delete_virtual_network_interface(vni_info['id'])
                except:
                    pass
            raise Exception(f"VNI creation failed: {str(e)}")
    
    def update_config_database(self, node_data, ip_allocation, vnis):
        """Update configuration database with new node"""
        logger.info(f"Updating database for {node_data['node_config']['node_name']}")
        
        node_config = {
            'node_name': node_data['node_config']['node_name'],
            'node_position': node_data['node_config']['node_position'],
            'server_profile': node_data['node_config']['server_profile'],
            'cluster_role': node_data['node_config']['cluster_role'],
            'deployment_status': 'provisioning',
            'management_vni': {
                'vni_id': vnis['management_vni']['id'],
                'ip': ip_allocation['management']['ip_address'],
                'dns_name': f"{node_data['node_config']['node_name']}-mgmt.{self.DNS_ZONE_NAME}"
            },
            'workload_vni': {
                'vni_id': vnis['workload_vni']['id'],
                'ip': ip_allocation['workload']['ip_address'],
                'dns_name': f"{node_data['node_config']['node_name']}-workload.{self.DNS_ZONE_NAME}"
            },
            'nutanix_config': {
                'ahv_ip': ip_allocation['ahv']['ip_address'],
                'ahv_dns': f"{node_data['node_config']['node_name']}-ahv.{self.DNS_ZONE_NAME}",
                'cvm_ip': ip_allocation['cvm']['ip_address'],
                'cvm_dns': f"{node_data['node_config']['node_name']}-cvm.{self.DNS_ZONE_NAME}",
                'cluster_ip': ip_allocation.get('cluster', {}).get('ip_address'),
                'cluster_dns': f'cluster01.{self.DNS_ZONE_NAME}' if ip_allocation.get('cluster') else None,
                'storage_config': node_data['node_config']['storage_config']
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
                ssh_key_ids=[self.SSH_KEY_ID],
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
            'pxe_server': self.PXE_SERVER_DNS,
            'config_endpoint': f'http://{self.PXE_SERVER_DNS}:8081/server-config'
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
        total_timeout = sum(self.DEPLOYMENT_TIMEOUTS.values())
        from datetime import datetime, timedelta
        return (datetime.now() + timedelta(seconds=total_timeout)).isoformat()
    
    def cleanup_failed_provisioning(self, node_name):
        """Clean up resources for a failed provisioning"""
        logger.warning(f"Cleaning up failed provisioning for {node_name}")
        
        try:
            # This will be implemented in the cleanup service
            # For now, just log the need for cleanup
            logger.error(f"Manual cleanup required for {node_name}")
        except Exception as e:
            logger.error(f"Cleanup failed for {node_name}: {str(e)}")