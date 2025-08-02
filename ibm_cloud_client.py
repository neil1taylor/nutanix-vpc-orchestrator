"""
IBM Cloud VPC and DNS client for Nutanix PXE/Config Server
Uses Trusted Profile authentication via metadata service
Configuration loaded from Config class
"""
import logging

from ibm_cloud_sdk_core.authenticators import VPCInstanceAuthenticator
from ibm_vpc import VpcV1
from ibm_cloud_networking_services import DnsSvcsV1
from config import Config

logger = logging.getLogger(__name__)

class IBMCloudClient:
    def __init__(self):
        # Load configuration from Config class instead of direct os.getenv
        self.region = Config.IBM_CLOUD_REGION
        self.vpc_id = Config.VPC_ID
        self.dns_instance_guid = Config.DNS_INSTANCE_GUID
        self.dns_zone_id = Config.DNS_ZONE_ID
        
        # Validate required configuration using Config class method
        Config.validate_required_config()
        
        # Initialize VPC service with trusted profile authentication
        try:
            self.vpc_authenticator = VPCInstanceAuthenticator()
            self.vpc_service = VpcV1(authenticator=self.vpc_authenticator)
            self.vpc_service.set_service_url(f'https://{self.region}.iaas.cloud.ibm.com/v1')
            
            # Debug: Log available methods in VpcV1
            logger.info(f"Available methods in VpcV1: {[method for method in dir(self.vpc_service) if not method.startswith('_')]}")
            logger.info(f"VpcV1 version: {getattr(self.vpc_service, '__version__', 'Unknown')}")
            logger.info(f"VpcV1 service URL: {self.vpc_service.service_url}")
        except Exception as e:
            logger.error(f"Failed to initialize VPC service: {str(e)}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception args: {e.args}")
            # Log the full traceback
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
        
        # Initialize DNS service with trusted profile authentication
        self.dns_authenticator = VPCInstanceAuthenticator()
        self.dns_service = DnsSvcsV1(authenticator=self.dns_authenticator)
        self.dns_service.set_service_url('https://api.dns-svcs.cloud.ibm.com/v1')
        
        logger.info("IBM Cloud client initialized with Config class and trusted profile authentication")
    
    # VPC Methods using SDK
    def create_subnet_reserved_ip(self, subnet_id, address, name):
        """Reserve an IP address in a subnet using VPC SDK"""
        try:
            # Correct method call - pass parameters directly, not as prototype object
            result = self.vpc_service.create_subnet_reserved_ip(
                subnet_id=subnet_id,
                address=address,
                name=name,
                auto_delete=False
            ).get_result()
            
            logger.info(f"Reserved IP {address} in subnet {subnet_id}")
            return {
                "id": result["id"],
                "ip_address": result["address"],
                "reservation_id": result["id"],
                "subnet_id": subnet_id
            }
        except Exception as e:
            logger.error(f"Failed to reserve IP {address}: {str(e)}")
            raise
    
    def delete_subnet_reserved_ip(self, subnet_id, reserved_ip_id):
        """Delete a reserved IP address using VPC SDK"""
        try:
            self.vpc_service.delete_subnet_reserved_ip(
                subnet_id=subnet_id,
                id=reserved_ip_id
            )
            logger.info(f"Deleted reserved IP {reserved_ip_id}")
        except Exception as e:
            logger.error(f"Failed to delete reserved IP {reserved_ip_id}: {str(e)}")
            raise
    
    def get_subnet_reserved_ips(self, subnet_id):
        """Get all reserved IPs in a subnet using VPC SDK"""
        try:
            result = self.vpc_service.list_subnet_reserved_ips(
                subnet_id=subnet_id
            ).get_result()
            
            return [ip["address"] for ip in result.get("reserved_ips", [])]
        except Exception as e:
            logger.error(f"Failed to get reserved IPs for subnet {subnet_id}: {str(e)}")
            raise
    
    def create_virtual_network_interface(self, subnet_id, name, primary_ip_id, security_group_ids):
        """Create a virtual network interface using VPC SDK"""
        try:
            # Debug: Check if the method exists
            logger.info(f"Checking if create_virtual_network_interface method exists: {hasattr(self.vpc_service, 'create_virtual_network_interface')}")
            
            # Debug: Log the VpcV1 object type and methods
            logger.info(f"VpcV1 object type: {type(self.vpc_service)}")
            logger.info(f"VpcV1 object methods: {[method for method in dir(self.vpc_service) if 'virtual_network_interface' in method]}")
            
            result = self.vpc_service.create_virtual_network_interface(
                name=name,
                subnet={'id': subnet_id},
                primary_ip={'id': primary_ip_id},
                security_groups=[{'id': sg_id} for sg_id in security_group_ids]
            ).get_result()
            
            logger.info(f"Created virtual network interface {name}")
            return {
                "id": result["id"],
                "name": result["name"],
                "primary_ip": result["primary_ip"]["address"]
            }
        except Exception as e:
            logger.error(f"Failed to create VNI {name}: {str(e)}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception args: {e.args}")
            # Log the full traceback
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    def delete_virtual_network_interface(self, vni_id):
        """Delete a virtual network interface using VPC SDK"""
        try:
            self.vpc_service.delete_virtual_network_interface(id=vni_id)
            logger.info(f"Deleted virtual network interface {vni_id}")
        except Exception as e:
            logger.error(f"Failed to delete VNI {vni_id}: {str(e)}")
            raise
    
    def create_bare_metal_server(self, name, profile, image_id, primary_vni_id, ssh_key_ids, additional_vnis=None, user_data=None):
        """Create a bare metal server using VPC SDK"""
        try:
            # Primary network attachment
            primary_network_attachment = {
                'name': f"{name}-primary-attachment",
                'virtual_network_interface': {'id': primary_vni_id}
            }
            
            # Additional network attachments
            network_attachments = [primary_network_attachment]
            if additional_vnis:
                for i, vni in enumerate(additional_vnis):
                    attachment = {
                        'name': f"{name}-attachment-{i+1}",
                        'virtual_network_interface': {'id': vni['id']}
                    }
                    network_attachments.append(attachment)
            
            bare_metal_server_prototype = {
                'name': name,
                'profile': {'name': profile},
                'image': {'id': image_id},
                'primary_network_attachment': primary_network_attachment,
                'network_attachments': network_attachments,
                'vpc': {'id': self.vpc_id},
                'zone': {'name': f"{self.region}-1"},
                'keys': [{'id': key_id} for key_id in ssh_key_ids]
            }
            
            if user_data:
                bare_metal_server_prototype['user_data'] = user_data
            
            result = self.vpc_service.create_bare_metal_server(
                bare_metal_server_prototype=bare_metal_server_prototype
            ).get_result()
            
            logger.info(f"Created bare metal server {name}")
            return {
                "id": result["id"],
                "name": result["name"],
                "status": result["status"]
            }
        except Exception as e:
            logger.error(f"Failed to create bare metal server {name}: {str(e)}")
            raise
    
    def delete_bare_metal_server(self, server_id):
        """Delete a bare metal server using VPC SDK"""
        try:
            self.vpc_service.delete_bare_metal_server(id=server_id)
            logger.info(f"Deleted bare metal server {server_id}")
        except Exception as e:
            logger.error(f"Failed to delete bare metal server {server_id}: {str(e)}")
            raise
    
    def get_bare_metal_server(self, server_id):
        """Get bare metal server details using VPC SDK"""
        try:
            result = self.vpc_service.get_bare_metal_server(id=server_id).get_result()
            return result
        except Exception as e:
            logger.error(f"Failed to get bare metal server {server_id}: {str(e)}")
            raise
    
    def get_subnet_info(self, subnet_id):
        """Get subnet information using VPC SDK"""
        try:
            result = self.vpc_service.get_subnet(id=subnet_id).get_result()
            return result
        except Exception as e:
            logger.error(f"Failed to get subnet info {subnet_id}: {str(e)}")
            raise
    
    def get_custom_image_by_name(self, image_name):
        """Get custom image by name using VPC SDK"""
        try:
            result = self.vpc_service.list_images(name=image_name).get_result()
            images = result.get("images", [])
            if images:
                return images[0]
            else:
                raise Exception(f"Custom image {image_name} not found")
        except Exception as e:
            logger.error(f"Failed to get custom image {image_name}: {str(e)}")
            raise
    
    # DNS Methods using SDK
    def create_dns_record(self, record_type, name, rdata, ttl=300):
        """Create a DNS record using DNS Services SDK"""
        try:
            logger.info(f"Attempting to create DNS record: {name} ({record_type}) -> {rdata}")
            logger.info(f"DNS instance GUID: {self.dns_instance_guid}")
            logger.info(f"DNS zone ID: {self.dns_zone_id}")
            logger.info(f"DNS service URL: {self.dns_service.service_url}")
            
            # Log the parameters being passed to the API
            logger.info(f"API call parameters: instance_id={self.dns_instance_guid}, dnszone_id={self.dns_zone_id}, name={name}, type={record_type.upper()}, rdata={{'ip': {rdata}}}, ttl={ttl}")
            
            # Fixed: Pass parameters directly instead of using prototype object
            if record_type.upper() == 'A':
                result = self.dns_service.create_resource_record(
                    instance_id=self.dns_instance_guid,
                    dnszone_id=self.dns_zone_id,
                    name=name,
                    type=record_type.upper(),
                    rdata={'ip': rdata},
                    ttl=ttl
                ).get_result()
            else:
                result = self.dns_service.create_resource_record(
                    instance_id=self.dns_instance_guid,
                    dnszone_id=self.dns_zone_id,
                    name=name,
                    type=record_type.upper(),
                    rdata={record_type.lower(): rdata},
                    ttl=ttl
                ).get_result()
            
            logger.info(f"Created DNS record {name} -> {rdata}")
            return {
                "id": result["id"],
                "name": name,
                "type": record_type,
                "rdata": rdata
            }
        except Exception as e:
            logger.error(f"Failed to create DNS record {name}: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error args: {e.args}")
            # Log the full exception traceback
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    def delete_dns_record(self, record_id):
        """Delete a DNS record using DNS Services SDK"""
        try:
            self.dns_service.delete_resource_record(
                instance_id=self.dns_instance_guid,
                dnszone_id=self.dns_zone_id,
                record_id=record_id
            )
            logger.info(f"Deleted DNS record {record_id}")
        except Exception as e:
            logger.error(f"Failed to delete DNS record {record_id}: {str(e)}")
            raise
    
    def get_dns_records(self):
        """Get all DNS records in the zone using DNS Services SDK"""
        try:
            result = self.dns_service.list_resource_records(
                instance_id=self.dns_instance_guid,
                dnszone_id=self.dns_zone_id
            ).get_result()
            
            return result.get("resource_records", [])
        except Exception as e:
            logger.error(f"Failed to get DNS records: {str(e)}")
            raise