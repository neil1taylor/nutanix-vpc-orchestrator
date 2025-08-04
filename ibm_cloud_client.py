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
        self.config = Config
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
            # logger.info(f"Available methods in VpcV1: {[method for method in dir(self.vpc_service) if not method.startswith('_')]}")
            # logger.info(f"VpcV1 version: {getattr(self.vpc_service, '__version__', 'Unknown')}")
            # logger.info(f"VpcV1 service URL: {self.vpc_service.service_url}")
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
            # Don't log 404 (not found) or 409 (in use) errors as errors since they're handled by cleanup service
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str:
                logger.info(f"Reserved IP {reserved_ip_id} not found (404), skipping deletion")
            elif "409" in error_str or "in use" in error_str:
                logger.info(f"Reserved IP {reserved_ip_id} is in use (409), cannot delete")
            else:
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
            #logger.info(f"VpcV1 object type: {type(self.vpc_service)}")
            #logger.info(f"VpcV1 object methods: {[method for method in dir(self.vpc_service) if 'virtual_network_interface' in method]}")
            
            result = self.vpc_service.create_virtual_network_interface(
                name=name,
                subnet={'id': subnet_id},
                primary_ip={'id': primary_ip_id},
                security_groups=[{'id': sg_id} for sg_id in security_group_ids],
                resource_group={'id': self.config.RESOURCE_GROUP_ID}
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
    
    def delete_virtual_network_interfaces(self, vni_id):
        """Delete a virtual network interface using VPC SDK"""
        try:
            # Based on the available methods in VpcV1, the correct method is:
            self.vpc_service.delete_virtual_network_interfaces(id=vni_id)
            logger.info(f"Deleted virtual network interface {vni_id}")
        except Exception as e:
            # Don't log 404 (not found) or 409 (in use) errors as errors since they're handled by cleanup service
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str:
                logger.info(f"VNI {vni_id} not found (404), skipping deletion")
            elif "409" in error_str or "in use" in error_str:
                logger.info(f"VNI {vni_id} is in use (409), cannot delete")
            else:
                logger.error(f"Failed to delete VNI {vni_id}: {str(e)}")
            raise
    
    def get_virtual_network_interface(self, vni_id):
        """Get a virtual network interface details using VPC SDK"""
        try:
            # Based on the available methods in VpcV1, the correct method is:
            response = self.vpc_service.get_virtual_network_interface(id=vni_id)
            return response.get_result()
        except Exception as e:
            logger.error(f"Failed to get VNI {vni_id}: {str(e)}")
            raise
    
    def create_bare_metal_server(self, name, profile, image_id, primary_vni_id, ssh_key_ids, additional_vnis=None, user_data=None):
        """Create a bare metal server using VPC SDK"""
        try:
            from ibm_vpc.vpc_v1 import (
                BareMetalServerPrototype,
                BareMetalServerProfileIdentityByName,
                BareMetalServerInitializationPrototype,
                ImageIdentityById,
                KeyIdentityById,
                VPCIdentityById,
                ZoneIdentityByName,
                BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterface,
                BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById,
                BareMetalServerPrototypeBareMetalServerByNetworkAttachment
            )
            
            # Build network attachments list
            # Include primary network attachment and any additional ones
            network_attachments = []
            
            # Primary network attachment
            primary_attachment = BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById(
                id=primary_vni_id
            )
            network_attachments.append(primary_attachment)
            
            # Additional network attachments
            if additional_vnis:
                for i, vni in enumerate(additional_vnis):
                    attachment = BareMetalServerNetworkAttachmentPrototypeVirtualNetworkInterfaceVirtualNetworkInterfaceIdentityVirtualNetworkInterfaceIdentityById(
                        id=vni['id']
                    )
                    network_attachments.append(attachment)
            
            # Create initialization prototype
            initialization = BareMetalServerInitializationPrototype(
                image=ImageIdentityById(id=image_id),
                keys=[KeyIdentityById(id=key_id) for key_id in ssh_key_ids]
            )
            
            if user_data:
                initialization.user_data = user_data
            
            # Create bare metal server prototype
            bare_metal_server_prototype = BareMetalServerPrototypeBareMetalServerByNetworkAttachment(
                name=name,
                profile=BareMetalServerProfileIdentityByName(name=profile),
                initialization=initialization,
                primary_network_attachment=network_attachments[0] if network_attachments else None,
                network_attachments=network_attachments,
                vpc=VPCIdentityById(id=self.vpc_id),
                zone=ZoneIdentityByName(name=f"{self.region}-1")
            )
            
            # Debug logging to see what parameters are being passed
            logger.info(f"Bare metal server prototype: {bare_metal_server_prototype.to_dict()}")
            
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
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception args: {e.args}")
            # Log the full traceback
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    def delete_bare_metal_server(self, server_id):
        """Delete a bare metal server using VPC SDK"""
        try:
            self.vpc_service.delete_bare_metal_server(id=server_id)
            logger.info(f"Deleted bare metal server {server_id}")
        except Exception as e:
            # Don't log 404 (not found) or 409 (in use) errors as errors since they're handled by cleanup service
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str:
                logger.info(f"Bare metal server {server_id} not found (404), skipping deletion")
            elif "409" in error_str or "in use" in error_str:
                logger.info(f"Bare metal server {server_id} is in use (409), cannot delete")
            else:
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
    
    def get_custom_image(self, image_identifier):
        """Get custom image by name or ID using VPC SDK"""
        try:
            # Check if the identifier is an ID (starts with "r006-")
            if image_identifier.startswith('r006-'):
                # Get image by ID using get_image method
                result = self.vpc_service.get_image(id=image_identifier).get_result()
                return result
            else:
                # Filter by name using list_images
                result = self.vpc_service.list_images(name=image_identifier).get_result()
                images = result.get("images", [])
                if images:
                    return images[0]
                else:
                    raise Exception(f"Custom image {image_identifier} not found")
        except Exception as e:
            logger.error(f"Failed to get custom image {image_identifier}: {str(e)}")
            raise
    
    # DNS Methods using SDK
    def create_dns_record(self, record_type, name, rdata, ttl=300):
        """Create a DNS record using DNS Services SDK"""
        try:
            logger.info(f"Attempting to create DNS record: {name} ({record_type}) -> {rdata}")
            
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
            # Don't log 404 (not found) or 409 (in use) errors as errors since they're handled by cleanup service
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str:
                logger.info(f"DNS record {record_id} not found (404), skipping deletion")
            elif "409" in error_str or "in use" in error_str:
                logger.info(f"DNS record {record_id} is in use (409), cannot delete")
            else:
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
    
    def list_subnets(self):
        """List all subnets in the VPC using VPC SDK"""
        try:
            result = self.vpc_service.list_subnets().get_result()
            return result.get("subnets", [])
        except Exception as e:
            logger.error(f"Failed to list subnets: {str(e)}")
            raise