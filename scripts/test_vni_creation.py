#!/usr/bin/env python3
"""
Test script to simulate VNI creation process
"""
import logging
import os
from ibm_cloud_client import IBMCloudClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_vni_creation():
    """Test VNI creation process"""
    try:
        # Initialize IBM Cloud client
        logger.info("Initializing IBM Cloud client...")
        ibm_cloud = IBMCloudClient()
        
        # Log some info about the client
        logger.info(f"VPC service type: {type(ibm_cloud.vpc_service)}")
        logger.info(f"VPC service URL: {ibm_cloud.vpc_service.service_url}")
        
        # Check if create_virtual_network_interface method exists
        has_method = hasattr(ibm_cloud.vpc_service, 'create_virtual_network_interface')
        logger.info(f"Has create_virtual_network_interface method: {has_method}")
        
        if has_method:
            logger.info("Method exists, but we won't actually call it to avoid creating resources")
        else:
            logger.error("Method does not exist!")
            
    except Exception as e:
        logger.error(f"Error in test: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_vni_creation()