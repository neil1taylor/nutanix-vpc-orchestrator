#!/usr/bin/env python3
"""
Test script to verify the boot configuration endpoint works correctly
with the fix for the 'net0 is not defined' error.
"""

import requests
import sys
import logging
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Base URL for testing
BASE_URL = "http://localhost:8080"

def test_boot_config(ip_address=None):
    """Test the boot configuration endpoint with a specific IP address"""
    endpoint = "/boot/config"
    if ip_address:
        endpoint += f"?mgmt_ip={ip_address}"
    
    url = urljoin(BASE_URL, endpoint)
    logger.info(f"Testing boot config endpoint: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        
        # Check if endpoint exists and returns valid content
        if response.status_code == 404:
            logger.error(f"Boot config endpoint not found (404)")
            return False
        elif response.status_code >= 500:
            logger.error(f"Server error ({response.status_code}): {response.text}")
            return False
        else:
            # Check if the response contains the expected iPXE script content
            content = response.text
            logger.info(f"Response status code: {response.status_code}")
            
            # Log the first few lines of the response for verification
            content_preview = "\n".join(content.splitlines()[:10])
            logger.info(f"Response content preview:\n{content_preview}")
            
            # Check for the error string
            if "net0 is not defined" in content:
                logger.error("Error still present: 'net0 is not defined'")
                return False
            
            # Check for the correct kernel command line format
            if "kernel ${base-url}/vmlinuz-foundation" in content and "node_id=${node_id}" in content:
                logger.info("Boot script contains correct kernel command line format")
                return True
            else:
                logger.warning("Boot script may not contain the expected kernel command line format")
                return False
            
    except requests.exceptions.ConnectionError:
        logger.error("Connection error - is the server running?")
        return False
    except requests.exceptions.Timeout:
        logger.error("Request timed out")
        return False
    except Exception as e:
        logger.error(f"Error: {e}")
        return False

def main():
    """Main test function"""
    logger.info("Testing boot configuration endpoint")
    logger.info("=" * 50)
    
    # Test with the specific IP that had the issue
    problem_ip = "10.240.0.10"
    logger.info(f"Testing with problem IP: {problem_ip}")
    
    if test_boot_config(problem_ip):
        logger.info("✅ Boot config test passed with problem IP")
    else:
        logger.error("❌ Boot config test failed with problem IP")
        return 1
    
    # Also test without an IP to ensure general functionality works
    logger.info("Testing without specific IP")
    if test_boot_config():
        logger.info("✅ Boot config test passed without specific IP")
    else:
        logger.warning("⚠️ Boot config test without specific IP had issues")
    
    logger.info("=" * 50)
    logger.info("Boot configuration tests completed")
    return 0

if __name__ == "__main__":
    sys.exit(main())