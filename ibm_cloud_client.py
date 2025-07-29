"""
IBM Cloud VPC and DNS client for Nutanix PXE/Config Server
"""
import requests
import json
import logging
from datetime import datetime, timedelta
from config import Config

logger = logging.getLogger(__name__)

class IBMCloudClient:
    def __init__(self):
        self.api_key = Config.IBM_CLOUD_API_KEY
        self.region = Config.IBM_CLOUD_REGION
        self.vpc_id = Config.VPC_ID
        self.dns_instance_id = Config.DNS_INSTANCE_ID
        self.dns_zone_id = Config.DNS_ZONE_ID
        self.access_token = None
        self.token_expires = None
        
        # API endpoints
        self.iam_url = "https://iam.cloud.ibm.com"
        self.vpc_url = f"https://{self.region}.iaas.cloud.ibm.com/v1"
        self.dns_url = f"https://api.dns-svcs.cloud.ibm.com/v1"
    
    def get_access_token(self):
        """Get IBM Cloud access token"""
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token
        
        try:
            response = requests.post(
                f"{self.iam_url}/identity/token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                },
                data={
                    "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                    "apikey": self.api_key
                }
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                # Token expires in 1 hour, refresh 5 minutes early
                self.token_expires = datetime.now() + timedelta(seconds=token_data['expires_in'] - 300)
                logger.info("IBM Cloud access token obtained")
                return self.access_token
            else:
                logger.error(f"Failed to get access token: {response.text}")
                raise Exception(f"Token request failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error getting access token: {str(e)}")
            raise
    
    def make_vpc_request(self, method, endpoint, data=None, params=None):
        """Make authenticated VPC API request"""
        token = self.get_access_token()
        url = f"{self.vpc_url}{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers)
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            if response.status_code in [200, 201, 202, 204]:
                return response.json() if response.content else {}
            else:
                logger.error(f"VPC API request failed: {response.status_code} - {response.text}")
                raise Exception(f"VPC API error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"VPC API request error: {str(e)}")
            raise
    
    def make_dns_request(self, method, endpoint, data=None, params=None):
        """Make authenticated DNS API request"""
        token = self.get_access_token()
        url = f"{self.dns_url}{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers)
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            if response.status_code in [200, 201, 202, 204]:
                return response.json() if response.content else {}
            else:
                logger.error(f"DNS API request failed: {response.status_code} - {response.text}")
                raise Exception(f"DNS API error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"DNS API request error: {str(e)}")
            raise
    
    # VPC Methods
    def create_subnet_reserved_ip(self, subnet_id, address, name):
        """Reserve an IP address in a subnet"""
        data = {
            "address": address,
            "name": name,
            "auto_delete": False
        }
        
        result = self.make_vpc_request('POST', f"/subnets/{subnet_id}/reserved_ips", data)
        logger.info(f"Reserved IP {address} in subnet {subnet_id}")
        return {
            "id": result["id"],
            "ip_address": result["address"],
            "reservation_id": result["id"],
            "subnet_id": subnet_id
        }
    
    def delete_subnet_reserved_ip(self, subnet_id, reserved_ip_id):
        """Delete a reserved IP address"""
        self.make_vpc_request('DELETE', f"/subnets/{subnet_id}/reserved_ips/{reserved_ip_id}")
        logger.info(f"Deleted reserved IP {reserved_ip_id}")
    
    def get_subnet_reserved_ips(self, subnet_id):
        """Get all reserved IPs in a subnet"""
        result = self.make_vpc_request('GET', f"/subnets/{subnet_id}/reserved_ips")
        return [ip["address"] for ip in result.get("reserved_ips", [])]
    
    def create_network_interface(self, subnet_id, name, primary_ip_id, security_group_ids):
        """Create a network interface (vNIC)"""
        data = {
            "name": name,
            "subnet": {"id": subnet_id},
            "primary_ip": {"id": primary_ip_id},
            "security_groups": [{"id": sg_id} for sg_id in security_group_ids]
        }
        
        result = self.make_vpc_request('POST', "/network_interfaces", data)
        logger.info(f"Created network interface {name}")
        return {
            "id": result["id"],
            "name": result["name"],
            "primary_ip": result["primary_ip"]["address"]
        }
    
    def delete_network_interface(self, interface_id):
        """Delete a network interface"""
        self.make_vpc_request('DELETE', f"/network_interfaces/{interface_id}")
        logger.info(f"Deleted network interface {interface_id}")
    
    def create_bare_metal_server(self, name, profile, image_id, primary_interface_id, network_interfaces, user_data=None):
        """Create a bare metal server"""
        data = {
            "name": name,
            "profile": {"name": profile},
            "image": {"id": image_id},
            "primary_network_interface": {"id": primary_interface_id},
            "network_interfaces": [{"id": iface["id"]} for iface in network_interfaces],
            "vpc": {"id": self.vpc_id},
            "zone": {"name": f"{self.region}-1"}
        }
        
        if user_data:
            data["user_data"] = user_data
        
        result = self.make_vpc_request('POST', "/bare_metal_servers", data)
        logger.info(f"Created bare metal server {name}")
        return {
            "id": result["id"],
            "name": result["name"],
            "status": result["status"]
        }
    
    def delete_bare_metal_server(self, server_id):
        """Delete a bare metal server"""
        self.make_vpc_request('DELETE', f"/bare_metal_servers/{server_id}")
        logger.info(f"Deleted bare metal server {server_id}")
    
    def get_bare_metal_server(self, server_id):
        """Get bare metal server details"""
        return self.make_vpc_request('GET', f"/bare_metal_servers/{server_id}")
    
    def get_subnet_info(self, subnet_id):
        """Get subnet information"""
        return self.make_vpc_request('GET', f"/subnets/{subnet_id}")
    
    # DNS Methods
    def create_dns_record(self, record_type, name, rdata, ttl=300):
        """Create a DNS record"""
        data = {
            "name": name,
            "type": record_type,
            "rdata": {record_type.lower(): rdata},
            "ttl": ttl
        }
        
        result = self.make_dns_request('POST', f"/instances/{self.dns_instance_id}/dnszones/{self.dns_zone_id}/resource_records", data)
        logger.info(f"Created DNS record {name} -> {rdata}")
        return {
            "id": result["id"],
            "name": name,
            "type": record_type,
            "rdata": rdata
        }
    
    def delete_dns_record(self, record_id):
        """Delete a DNS record"""
        self.make_dns_request('DELETE', f"/instances/{self.dns_instance_id}/dnszones/{self.dns_zone_id}/resource_records/{record_id}")
        logger.info(f"Deleted DNS record {record_id}")
    
    def get_dns_records(self):
        """Get all DNS records in the zone"""
        result = self.make_dns_request('GET', f"/instances/{self.dns_instance_id}/dnszones/{self.dns_zone_id}/resource_records")
        return result.get("resource_records", [])
    
    def get_custom_image_by_name(self, image_name):
        """Get custom image by name"""
        result = self.make_vpc_request('GET', "/images", params={"name": image_name})
        images = result.get("images", [])
        if images:
            return images[0]
        else:
            raise Exception(f"Custom image {image_name} not found")