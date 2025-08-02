#!/usr/bin/env python3
"""
Test script to simulate VNI creation process with detailed error handling
"""
import logging
import os
import sys

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set dummy environment variables for testing
os.environ['IBM_CLOUD_REGION'] = 'us-south'
os.environ['VPC_ID'] = 'dummy-vpc-id'
os.environ['DNS_INSTANCE_GUID'] = 'dummy-dns-instance-guid'
os.environ['DNS_ZONE_ID'] = 'dummy-dns-zone-id'
os.environ['MANAGEMENT_SUBNET_ID'] = 'dummy-management-subnet-id'
os.environ['WORKLOAD_SUBNET_ID'] = 'dummy-workload-subnet-id'
os.environ['MANAGEMENT_SECURITY_GROUP_ID'] = 'dummy-management-sg-id'
os.environ['INTRA_NODE_SECURITY_GROUP_ID'] = 'dummy-intra-node-sg-id'
os.environ['WORKLOAD_SECURITY_GROUP_ID'] = 'dummy-workload-sg-id'
os.environ['SSH_KEY_ID'] = 'dummy-ssh-key-id'
os.environ['PXE_SERVER_DNS'] = 'dummy-pxe-server-dns'

from ibm_cloud_client import IBMCloudClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_vni_creation_detailed():
    """Test VNI creation process with detailed error handling"""
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
            logger.info("Method exists, trying to call it with dummy parameters...")
            try:
                # Try to call the method with dummy parameters
                # This won't actually create a VNI because we're using dummy IDs
                result = ibm_cloud.vpc_service.create_virtual_network_interface(
                    name='test-vni',
                    subnet={'id': 'dummy-subnet-id'},
                    primary_ip={'id': 'dummy-ip-id'},
                    security_groups=[{'id': 'dummy-sg-id'}]
                )
                logger.info("Method call succeeded (unexpectedly)")
                logger.info(f"Result: {result}")
            except Exception as e:
                logger.info(f"Method call failed as expected with dummy parameters: {str(e)}")
                logger.info(f"Exception type: {type(e).__name__}")
                import traceback
                logger.info(f"Full traceback: {traceback.format_exc()}")
        else:
            logger.error("Method does not exist!")
            
    except Exception as e:
        logger.error(f"Error in test: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_vni_creation_detailed()