#!/usr/bin/env python3
"""
Script to stop a bare metal server and reinitialize it with an IP address.

This script:
1. Takes a server hostname as input
2. Stops the bare metal server
3. Waits for it to be in a stopped state
4. Reinitializes the server with an IP using the specified boot configuration
"""

import os
import sys
import time
import argparse
import logging
import traceback  # Import traceback module for error handling
from datetime import datetime

# Add the parent directory to the Python path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import required modules
from ibm_cloud_client import IBMCloudClient
from database import Database
from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def get_server_by_hostname(hostname):
    """
    Get server details from the database by hostname
    
    Args:
        hostname (str): The hostname of the server
        
    Returns:
        dict: Server details if found, None otherwise
    """
    db = Database()
    try:
        # Try to get the node by name
        node = db.get_node_by_name(hostname)
        if node:
            logger.info(f"Found server in database: {hostname}")
            return node
        else:
            logger.error(f"Server not found in database: {hostname}")
            return None
    except Exception as e:
        logger.error(f"Error retrieving server from database: {str(e)}")
        return None

def stop_server(server_id):
    """
    Stop a bare metal server
    
    Args:
        server_id (str): The ID of the bare metal server
        
    Returns:
        bool: True if successful, False otherwise
    """
    ibm_cloud = IBMCloudClient()
    
    # Log available methods for debugging
    bare_metal_methods = [m for m in dir(ibm_cloud.vpc_service) if 'bare_metal' in m.lower()]
    logger.info(f"Available bare metal methods in VPC SDK: {bare_metal_methods}")
    
    try:
        # Get current server state
        server_details = ibm_cloud.get_bare_metal_server(server_id)
        current_state = server_details.get('status', '')
        
        logger.info(f"Current server state: {current_state}")
        
        # If server is already stopped, return success
        if current_state.lower() == 'stopped':
            logger.info(f"Server {server_id} is already stopped")
            return True
            
        # If server is already stopping, we'll wait for it
        if current_state.lower() == 'stopping':
            logger.info(f"Server {server_id} is already in stopping state")
            return True
            
        # Stop the server using the VPC SDK
        logger.info(f"Stopping server {server_id}...")
        
        # Use the VPC SDK to stop the server
        # The method name might vary based on the SDK version
        try:
            # Try the standard method name first with the required 'type' parameter
            # Based on the error message, 'type' is a required parameter
            ibm_cloud.vpc_service.stop_bare_metal_server(id=server_id, type='hard')
        except TypeError as te:
            # If there's a different TypeError, log it and try alternatives
            logger.warning(f"TypeError when calling stop_bare_metal_server: {str(te)}")
            try:
                # Try with different parameter combinations
                ibm_cloud.vpc_service.stop_bare_metal_server(id=server_id, type='soft')
            except Exception as e2:
                logger.warning(f"Failed with soft stop: {str(e2)}")
                # Try one more approach
                try:
                    # Try with a prototype object
                    ibm_cloud.vpc_service.stop_bare_metal_server(
                        id=server_id,
                        bare_metal_server_stop_prototype={'type': 'hard'}
                    )
                except Exception as e3:
                    logger.warning(f"Failed with prototype: {str(e3)}")
                    raise
        except AttributeError:
            # If the method doesn't exist, try alternative method names
            try:
                # Try alternative method name
                ibm_cloud.vpc_service.bare_metal_server_stop(id=server_id, type='hard')
            except AttributeError:
                # If that also fails, log available methods and raise an error
                logger.error("Could not find stop method for bare metal server")
                logger.error(f"Available methods: {[m for m in dir(ibm_cloud.vpc_service) if 'bare_metal' in m.lower()]}")
                raise Exception("Stop method for bare metal server not found in VPC SDK")
        
        logger.info(f"Stop request sent for server {server_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to stop server {server_id}: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return False

def wait_for_server_state(server_id, target_state='stopped', timeout_minutes=30):
    """
    Wait for a server to reach the target state
    
    Args:
        server_id (str): The ID of the bare metal server
        target_state (str): The target state to wait for (default: 'stopped')
        timeout_minutes (int): Maximum time to wait in minutes
        
    Returns:
        bool: True if server reached the target state, False if timeout or error
    """
    ibm_cloud = IBMCloudClient()
    
    logger.info(f"Waiting for server {server_id} to reach '{target_state}' state...")
    
    # Calculate timeout in seconds
    timeout_seconds = timeout_minutes * 60
    start_time = time.time()
    
    # Poll until server reaches target state or timeout
    while (time.time() - start_time) < timeout_seconds:
        try:
            # Get current server state
            server_details = ibm_cloud.get_bare_metal_server(server_id)
            current_state = server_details.get('status', '').lower()
            
            logger.info(f"Current server state: {current_state}")
            
            # Check if server reached target state
            if current_state == target_state.lower():
                logger.info(f"Server {server_id} reached '{target_state}' state")
                return True
                
            # Wait before polling again
            time.sleep(30)  # Poll every 30 seconds
        except Exception as e:
            logger.error(f"Error checking server state: {str(e)}")
            # Continue polling despite errors
            time.sleep(30)
    
    # If we get here, we've timed out
    logger.error(f"Timeout waiting for server {server_id} to reach '{target_state}' state")
    return False

def reinitialize_server(server_id, management_ip):
    """
    Reinitialize a server with the specified IP
    
    Args:
        server_id (str): The ID of the bare metal server
        management_ip (str): The management IP address to use
        
    Returns:
        bool: True if successful, False otherwise
    """
    ibm_cloud = IBMCloudClient()
    try:
        # Just use the URL as the user data
        # The ${net0/ip} variable will be expanded by the iPXE client on the bare metal server
        user_data = "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/config?mgmt_ip=${net0/ip}"
        
        logger.info(f"Using URL for network boot: {user_data}")
        
        # Start the server with the boot configuration
        logger.info(f"Starting server {server_id} with boot configuration: {boot_config_url}")
        
        # Get the current server initialization to extract image and keys
        try:
            # Get the current initialization
            current_init = ibm_cloud.vpc_service.get_bare_metal_server_initialization(id=server_id).get_result()
            logger.info(f"Retrieved current server initialization")
            
            # Import required classes
            from ibm_vpc.vpc_v1 import (
                BareMetalServerInitializationPrototype,
                ImageIdentityById,
                KeyIdentityById
            )
            
            # Extract image and keys from current initialization
            image_id = current_init.get('image', {}).get('id')
            key_ids = [key.get('id') for key in current_init.get('keys', [])]
            
            if not image_id or not key_ids:
                raise ValueError("Could not extract image or keys from current initialization")
                
            logger.info(f"Using image ID: {image_id} and key IDs: {key_ids}")
            
            # Create initialization prototype with all required parameters
            init_prototype = BareMetalServerInitializationPrototype(
                image=ImageIdentityById(id=image_id),
                keys=[KeyIdentityById(id=key_id) for key_id in key_ids],
                user_data=user_data
            )
            
            # Replace the server initialization - pass the required parameters directly
            logger.info(f"Updating server initialization with user data for network boot")
            ibm_cloud.vpc_service.replace_bare_metal_server_initialization(
                id=server_id,
                image=ImageIdentityById(id=image_id),
                keys=[KeyIdentityById(id=key_id) for key_id in key_ids],
                user_data=user_data
            )
            
            # Now start the server
            logger.info(f"Starting server {server_id} with network boot configuration")
            ibm_cloud.vpc_service.start_bare_metal_server(id=server_id)
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to update initialization and start server: {error_msg}")
            logger.error("Cannot proceed without proper network boot configuration")
            # Use the imported traceback module
            import traceback as tb  # Import with alias to avoid any confusion
            logger.error(f"Full traceback: {tb.format_exc()}")
            raise Exception(f"Failed to set network boot configuration: {error_msg}")
        
        logger.info(f"Server {server_id} reinitialization initiated")
        return True
    except Exception as e:
        logger.error(f"Failed to reinitialize server {server_id}: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return False

def main():
    """Main function to process command line arguments and execute the script"""
    parser = argparse.ArgumentParser(description='Stop and reinitialize a bare metal server')
    parser.add_argument('hostname', help='Hostname of the server to reinitialize')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout in minutes for server to stop (default: 30)')
    
    args = parser.parse_args()
    
    # Create a todo list for the steps
    logger.info("Starting server reinitialization process")
    logger.info(f"1. Get server details for hostname: {args.hostname}")
    logger.info("2. Stop the server")
    logger.info("3. Wait for server to reach stopped state")
    logger.info("4. Reinitialize the server with IP")
    
    # Step 1: Get server details
    server = get_server_by_hostname(args.hostname)
    if not server:
        logger.error(f"Could not find server with hostname: {args.hostname}")
        sys.exit(1)
    
    server_id = server.get('bare_metal_id')
    management_ip = server.get('management_ip')
    
    if not server_id:
        logger.error(f"Server {args.hostname} does not have a bare metal ID")
        sys.exit(1)
        
    if not management_ip:
        logger.error(f"Server {args.hostname} does not have a management IP")
        sys.exit(1)
    
    logger.info(f"Found server: {args.hostname}")
    logger.info(f"  Bare Metal ID: {server_id}")
    logger.info(f"  Management IP: {management_ip}")
    
    # Step 2: Stop the server
    if not stop_server(server_id):
        logger.error(f"Failed to stop server {args.hostname}")
        sys.exit(1)
    
    # Step 3: Wait for server to reach stopped state
    if not wait_for_server_state(server_id, 'stopped', args.timeout):
        logger.error(f"Server {args.hostname} did not reach stopped state within timeout")
        sys.exit(1)
    
    # Step 4: Reinitialize the server with IP
    if not reinitialize_server(server_id, management_ip):
        logger.error(f"Failed to reinitialize server {args.hostname}")
        sys.exit(1)
    
    logger.info(f"Server {args.hostname} reinitialization process completed successfully")
    logger.info(f"The server is being reinitialized with IP: {management_ip}")
    logger.info("Please allow a few minutes for the server to complete the boot process")

if __name__ == "__main__":
    main()