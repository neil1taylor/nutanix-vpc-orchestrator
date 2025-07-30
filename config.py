"""
Configuration settings for Nutanix PXE/Config Server
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'nutanix-pxe-config-secret-key'
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # Database settings
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://nutanix:nutanix@localhost/nutanix_pxe'
    
    # IBM Cloud settings
    IBM_CLOUD_API_KEY = os.environ.get('IBM_CLOUD_API_KEY')
    IBM_CLOUD_REGION = os.environ.get('IBM_CLOUD_REGION') or 'us-south'
    VPC_ID = os.environ.get('VPC_ID')
    DNS_INSTANCE_ID = os.environ.get('DNS_INSTANCE_ID')
    DNS_ZONE_ID = os.environ.get('DNS_ZONE_ID')
    
    # Network configuration
    MANAGEMENT_SUBNET_ID = os.environ.get('MANAGEMENT_SUBNET_ID')
    WORKLOAD_SUBNET_ID = os.environ.get('WORKLOAD_SUBNET_ID')
    MANAGEMENT_SECURITY_GROUP_ID = os.environ.get('MANAGEMENT_SECURITY_GROUP_ID')
    WORKLOAD_SECURITY_GROUP_ID = os.environ.get('WORKLOAD_SECURITY_GROUP_ID')
    
    # PXE Server settings
    PXE_SERVER_IP = os.environ.get('PXE_SERVER_IP') or '10.240.0.12'
    PXE_SERVER_DNS = os.environ.get('PXE_SERVER_DNS') or 'nutanix-pxe-config.nutanix.cloud'
    
    # DNS settings
    DNS_ZONE_NAME = os.environ.get('DNS_ZONE_NAME') or 'nutanix.internal'
    
    # IP allocation ranges
    IP_RANGES = {
        'management': (20, 29),   # 10.240.0.20-29
        'ahv': (30, 39),         # 10.240.0.30-39
        'cvm': (40, 49),         # 10.240.0.40-49
        'cluster': (50, 59),     # 10.240.0.50-59
        'workload': (20, 100)    # 10.241.0.20-100
    }
    
    # Deployment timeouts (seconds)
    DEPLOYMENT_TIMEOUTS = {
        'ipxe_boot': 300,         # 5 minutes
        'config_download': 120,    # 2 minutes
        'foundation_start': 180,   # 3 minutes
        'storage_discovery': 300,  # 5 minutes
        'image_download': 900,     # 15 minutes
        'installation': 1200,      # 20 minutes
        'cluster_formation': 600,  # 10 minutes
        'dns_registration': 120,   # 2 minutes
        'health_validation': 300   # 5 minutes
    }
    
    # File paths
    BOOT_IMAGES_PATH = '/var/www/pxe/images'
    BOOT_SCRIPTS_PATH = '/var/www/pxe/scripts'
    CONFIG_TEMPLATES_PATH = '/var/www/pxe/configs'
    LOG_PATH = '/var/log/nutanix-pxe'