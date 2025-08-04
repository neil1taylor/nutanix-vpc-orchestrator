#!/usr/bin/env python3
"""
Script to populate the database with bare metal server details for reinitialization
without going through the full provisioning process.

This script allows you to add an existing bare metal server to the database so that
it can be reinitialized without provisioning a new server.
"""

import os
import sys
import json
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import Config
from database import Database

def populate_bare_metal_server(node_name, management_ip, server_profile, cluster_role='compute-storage', 
                              bare_metal_id=None, management_vnic_id=None, workload_vnic_id=None, 
                              workload_ip=None):
    """
    Populate the database with bare metal server details
    
    Args:
        node_name (str): Name of the node
        management_ip (str): Management IP address of the server
        server_profile (str): Server profile (e.g., 'cx3d-metal-48x128')
        cluster_role (str): Cluster role (default: 'compute-storage')
        bare_metal_id (str): IBM Cloud bare metal server ID (optional)
        management_vnic_id (str): Management VNIC ID (optional)
        workload_vnic_id (str): Workload VNIC ID (optional)
        workload_ip (str): Workload IP address (optional)
    """
    
    # Initialize database connection
    db = Database()
    
    try:
        # Prepare node configuration
        node_config = {
            'node_name': node_name,
            'server_profile': server_profile,
            'cluster_role': cluster_role,
            'deployment_status': 'deployed',  # Mark as already deployed
            'management_vnic_id': management_vnic_id,
            'management_ip': management_ip,
            'workload_vnic_id': workload_vnic_id,
            'workload_ip': workload_ip,
            'workload_vnics': {},
            'nutanix_config': {
                'ahv_ip': '',  # Will be populated later if needed
                'ahv_dns': '',
                'cvm_ip': '',  # Will be populated later if needed
                'cvm_dns': '',
                'cluster_ip': '',  # Will be populated later if needed
                'cluster_dns': '',
                'storage_config': {},
                'cluster_type': 'multi_node'
            }
        }
        
        # Insert node into database
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO nodes (
                        node_name, server_profile, cluster_role,
                        deployment_status, bare_metal_id, management_vnic_id, management_ip,
                        workload_vnic_id, workload_ip, workload_vnics, nutanix_config
                    ) VALUES (
                        %(node_name)s, %(server_profile)s, %(cluster_role)s,
                        %(deployment_status)s, %(bare_metal_id)s, %(management_vnic_id)s, %(management_ip)s,
                        %(workload_vnic_id)s, %(workload_ip)s, %(workload_vnics)s, %(nutanix_config)s
                    ) RETURNING id;
                """, {
                    'node_name': node_config['node_name'],
                    'server_profile': node_config['server_profile'],
                    'cluster_role': node_config['cluster_role'],
                    'deployment_status': node_config['deployment_status'],
                    'bare_metal_id': bare_metal_id or None,
                    'management_vnic_id': node_config['management_vnic_id'] or None,
                    'management_ip': node_config['management_ip'],
                    'workload_vnic_id': node_config['workload_vnic_id'] or None,
                    'workload_ip': node_config['workload_ip'] or None,
                    'workload_vnics': json.dumps(node_config['workload_vnics']),
                    'nutanix_config': json.dumps(node_config['nutanix_config'])
                })
                
                node_id = cur.fetchone()[0]
                
        print(f"Successfully added bare metal server '{node_name}' to database with ID {node_id}")
        print(f"Management IP: {management_ip}")
        print(f"Server Profile: {server_profile}")
        print(f"Deployment Status: {node_config['deployment_status']}")
        
        # Add a deployment history entry
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO deployment_history (
                        node_id, phase, status, message
                    ) VALUES (
                        %s, %s, %s, %s
                    )
                """, (
                    node_id,
                    'manual_registration',
                    'success',
                    f'Manually registered existing bare metal server {node_name}'
                ))
                
        print("Added deployment history entry for manual registration")
        
        return node_id
        
    except Exception as e:
        print(f"Error populating bare metal server: {str(e)}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Populate database with bare metal server details')
    parser.add_argument('--node-name', required=True, help='Name of the node')
    parser.add_argument('--management-ip', required=True, help='Management IP address of the server')
    parser.add_argument('--server-profile', required=True, help='Server profile (e.g., cx3d-metal-48x128)')
    parser.add_argument('--cluster-role', default='compute-storage', help='Cluster role (default: compute-storage)')
    parser.add_argument('--bare-metal-id', help='IBM Cloud bare metal server ID (optional)')
    parser.add_argument('--management-vnic-id', help='Management VNIC ID (optional)')
    parser.add_argument('--workload-vnic-id', help='Workload VNIC ID (optional)')
    parser.add_argument('--workload-ip', help='Workload IP address (optional)')
    
    args = parser.parse_args()
    
    # Validate IP address format
    import ipaddress
    try:
        ipaddress.ip_address(args.management_ip)
        if args.workload_ip:
            ipaddress.ip_address(args.workload_ip)
    except ValueError as e:
        print(f"Invalid IP address: {e}")
        sys.exit(1)
    
    # Populate the database
    node_id = populate_bare_metal_server(
        node_name=args.node_name,
        management_ip=args.management_ip,
        server_profile=args.server_profile,
        cluster_role=args.cluster_role,
        bare_metal_id=args.bare_metal_id,
        management_vnic_id=args.management_vnic_id,
        workload_vnic_id=args.workload_vnic_id,
        workload_ip=args.workload_ip
    )
    
    print(f"\nServer successfully registered with node ID: {node_id}")
    print("You can now reinitialize the server without provisioning a new one.")

if __name__ == "__main__":
    main()