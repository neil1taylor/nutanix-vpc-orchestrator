#!/usr/bin/env python3
"""
Test script to check available methods in VpcV1 class
"""
import logging
from ibm_cloud_sdk_core.authenticators import VPCInstanceAuthenticator
from ibm_vpc import VpcV1

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_vpc_methods():
    """Check available methods in VpcV1 class"""
    try:
        # Initialize VPC service
        authenticator = VPCInstanceAuthenticator()
        vpc_service = VpcV1(authenticator=authenticator)
        
        # Get all methods
        all_methods = [method for method in dir(vpc_service) if not method.startswith('_')]
        
        # Filter methods related to network interfaces
        network_methods = [method for method in all_methods if 'network' in method.lower() or 'interface' in method.lower()]
        
        logger.info("All methods in VpcV1:")
        for method in sorted(all_methods):
            logger.info(f"  {method}")
            
        logger.info("\nNetwork-related methods in VpcV1:")
        for method in sorted(network_methods):
            logger.info(f"  {method}")
            
    except Exception as e:
        logger.error(f"Error checking VPC methods: {str(e)}")

if __name__ == "__main__":
    check_vpc_methods()