"""
Configuration settings for Nutanix PXE/Config Server
Loads configuration from environment variables set by /etc/profile.d/app-vars.sh
"""
import os
import socket

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'nutanix-pxe-config-secret-key')
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # Database settings
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://nutanix:nutanix@localhost/nutanix_pxe')
    
    # IBM Cloud settings
    IBM_CLOUD_API_KEY = os.environ.get('IBM_CLOUD_API_KEY')
    IBM_CLOUD_REGION = os.environ.get('IBM_CLOUD_REGION')
    VPC_ID = os.environ.get('VPC_ID')
    DNS_INSTANCE_ID = os.environ.get('DNS_INSTANCE_ID')
    DNS_ZONE_ID = os.environ.get('DNS_ZONE_ID')
    DNS_ZONE_NAME = os.environ.get('DNS_ZONE_NAME')
    
    # Network configuration
    MANAGEMENT_SUBNET_ID = os.environ.get('MANAGEMENT_SUBNET_ID')
    WORKLOAD_SUBNET_ID = os.environ.get('WORKLOAD_SUBNET_ID')
    MANAGEMENT_SECURITY_GROUP_ID = os.environ.get('MANAGEMENT_SECURITY_GROUP_ID')
    WORKLOAD_SECURITY_GROUP_ID = os.environ.get('WORKLOAD_SECURITY_GROUP_ID')
    INTRA_NODE_SECURITY_GROUP_ID = os.environ.get('INTRA_NODE_SECURITY_GROUP_ID')
    
    # SSH Key
    SSH_KEY_ID = os.environ.get('SSH_KEY_ID')
    
    # PXE Server settings - auto-detect IP if not set
    @property
    def PXE_SERVER_IP(self):
        env_ip = os.environ.get('PXE_SERVER_IP')
        if env_ip:
            return env_ip
        # Auto-detect server IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return '127.0.0.1'
    
    PXE_SERVER_DNS = os.environ.get('PXE_SERVER_DNS', 'nutanix-pxe-config.nutanix-ce-poc.cloud')
    
    # IP allocation ranges
    IP_RANGES = {
        'management': (int(os.environ.get('MGMT_IP_START', '10')), int(os.environ.get('MGMT_IP_END', '50'))),
        'ahv': (int(os.environ.get('AHV_IP_START', '51')), int(os.environ.get('AHV_IP_END', '100'))),
        'cvm': (int(os.environ.get('CVM_IP_START', '101')), int(os.environ.get('CVM_IP_END', '150'))),
        'workload': (int(os.environ.get('WORKLOAD_IP_START', '10')), int(os.environ.get('WORKLOAD_IP_END', '200'))),
        'cluster': (int(os.environ.get('CLUSTER_IP_START', '200')), int(os.environ.get('CLUSTER_IP_END', '210')))
    }
    
    # Deployment timeouts (seconds)
    DEPLOYMENT_TIMEOUTS = {
        'ipxe_boot': int(os.environ.get('TIMEOUT_IPXE_BOOT', '300')),
        'config_download': int(os.environ.get('TIMEOUT_CONFIG_DOWNLOAD', '120')),
        'foundation_start': int(os.environ.get('TIMEOUT_FOUNDATION_START', '180')),
        'storage_discovery': int(os.environ.get('TIMEOUT_STORAGE_DISCOVERY', '300')),
        'image_download': int(os.environ.get('TIMEOUT_IMAGE_DOWNLOAD', '900')),
        'installation': int(os.environ.get('TIMEOUT_INSTALLATION', '1200')),
        'cluster_formation': int(os.environ.get('TIMEOUT_CLUSTER_FORMATION', '600')),
        'dns_registration': int(os.environ.get('TIMEOUT_DNS_REGISTRATION', '120')),
        'health_validation': int(os.environ.get('TIMEOUT_HEALTH_VALIDATION', '300'))
    }
    
    # File paths
    BOOT_IMAGES_PATH = os.environ.get('BOOT_IMAGES_PATH', '/var/www/pxe/images')
    BOOT_SCRIPTS_PATH = os.environ.get('BOOT_SCRIPTS_PATH', '/var/www/pxe/scripts')
    CONFIG_TEMPLATES_PATH = os.environ.get('CONFIG_TEMPLATES_PATH', '/var/www/pxe/configs')
    LOG_PATH = os.environ.get('LOG_PATH', '/var/log/nutanix-pxe')
    
    # HTTPS Configuration
    HTTPS_ENABLED = os.environ.get('HTTPS_ENABLED', 'false').lower() == 'true'
    SSL_CERT_PATH = os.environ.get('SSL_CERT_PATH', '/opt/nutanix-pxe/ssl/nutanix-orchestrator.crt')
    SSL_KEY_PATH = os.environ.get('SSL_KEY_PATH', '/opt/nutanix-pxe/ssl/nutanix-orchestrator.key')
    FORCE_HTTPS = os.environ.get('FORCE_HTTPS', 'false').lower() == 'true'
    
    @classmethod
    def validate_required_config(cls):
        """Validate that all required configuration is present"""
        required_vars = [
            'IBM_CLOUD_REGION', 'VPC_ID', 'DNS_INSTANCE_ID', 'DNS_ZONE_ID', 'DNS_ZONE_NAME',
            'MANAGEMENT_SUBNET_ID', 'WORKLOAD_SUBNET_ID', 'SSH_KEY_ID',
            'MANAGEMENT_SECURITY_GROUP_ID', 'WORKLOAD_SECURITY_GROUP_ID', 'INTRA_NODE_SECURITY_GROUP_ID'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required configuration: {', '.join(missing_vars)}")
        
        return True