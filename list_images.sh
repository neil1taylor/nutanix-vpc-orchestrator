#!/usr/bin/env python3
"""
Test script to list available images in IBM Cloud
"""
import logging
from ibm_cloud_sdk_core.authenticators import VPCInstanceAuthenticator
from ibm_vpc import VpcV1

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def list_images():
    """List available images in IBM Cloud"""
    try:
        # Initialize VPC service
        authenticator = VPCInstanceAuthenticator()
        vpc_service = VpcV1(authenticator=authenticator)
        
        # Set service URL (you'll need to set the region)
        region = "us-south"  # Change this to your region
        vpc_service.set_service_url(f'https://{region}.iaas.cloud.ibm.com/v1')
        
        # List all images
        logger.info("Listing all images...")
        result = vpc_service.list_images().get_result()
        images = result.get("images", [])
        
        logger.info(f"Found {len(images)} images:")
        for image in images:
            logger.info(f"  - {image['name']} ({image['id']}) - {image['status']}")
            
        # Filter for CentOS or RHEL images that might support network booting
        network_boot_images = [
            img for img in images 
            if any(keyword in img['name'].lower() for keyword in ['centos', 'rhel', 'red hat', 'ubuntu'])
        ]
        
        logger.info(f"\nFound {len(network_boot_images)} potential network boot images:")
        for image in network_boot_images:
            logger.info(f"  - {image['name']} ({image['id']}) - {image['status']}")
            
    except Exception as e:
        logger.error(f"Error listing images: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    list_images()