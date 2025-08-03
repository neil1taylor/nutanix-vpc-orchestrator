#!/usr/bin/env python3
"""
Script to check available methods in IBM Cloud VPC service
"""
import logging
from ibm_cloud_sdk_core.authenticators import VPCInstanceAuthenticator
from ibm_vpc import VpcV1

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_vpc_methods():
    """Check available methods in VPC service"""
    try:
        # Initialize VPC service
        authenticator = VPCInstanceAuthenticator()
        vpc_service = VpcV1(authenticator=authenticator)
        
        # Set service URL (you'll need to set the region)
        region = "us-south"  # Change this to your region
        vpc_service.set_service_url(f'https://{region}.iaas.cloud.ibm.com/v1')
        
        # List available methods
        logger.info("Available methods in VpcV1:")
        methods = [method for method in dir(vpc_service) if not method.startswith('_') and 'subnet' in method.lower()]
        for method in methods:
            logger.info(f"  - {method}")
            
        # Check if list_subnets exists
        if hasattr(vpc_service, 'list_subnets'):
            logger.info("list_subnets method exists")
        else:
            logger.info("list_subnets method does not exist")
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    check_vpc_methods()