#!/usr/bin/env python3
"""
Script to list all nodes in the database
"""

import os
import sys
import json

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import Database

def list_nodes():
    """List all nodes in the database"""
    db = Database()
    
    try:
        nodes = db.get_all_nodes()
        
        if not nodes:
            print("No nodes found in the database.")
            return
        
        # Print nodes in a simple table format
        print(f"{'ID':<5} {'Name':<25} {'Server Profile':<20} {'Cluster Role':<15} {'Status':<15} {'Management IP':<15} {'Workload IP':<15} {'Created At':<20}")
        print("-" * 140)
        
        for node in nodes:
            created_at = node['created_at'].strftime('%Y-%m-%d %H:%M:%S') if node['created_at'] else 'N/A'
            print(f"{node['id']:<5} {node['node_name']:<25} {node['server_profile']:<20} {node['cluster_role']:<15} {node['deployment_status']:<15} {str(node['management_ip']) if node['management_ip'] else 'N/A':<15} {str(node['workload_ip']) if node['workload_ip'] else 'N/A':<15} {created_at:<20}")
        
        print(f"\nTotal nodes: {len(nodes)}")
        
    except Exception as e:
        print(f"Error listing nodes: {str(e)}")
        sys.exit(1)

def get_node_details(node_id):
    """Get detailed information for a specific node"""
    db = Database()
    
    try:
        node = db.get_node(node_id)
        
        if not node:
            print(f"Node with ID {node_id} not found.")
            return
        
        print(f"Node Details for ID {node_id}:")
        print("=" * 40)
        for key, value in node.items():
            if key == 'nutanix_config' and isinstance(value, dict):
                print(f"{key}:")
                for sub_key, sub_value in value.items():
                    print(f"  {sub_key}: {sub_value}")
            else:
                print(f"{key}: {value}")
        
    except Exception as e:
        print(f"Error getting node details: {str(e)}")
        sys.exit(1)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='List nodes in the database')
    parser.add_argument('--details', type=int, help='Show detailed information for a specific node ID')
    
    args = parser.parse_args()
    
    if args.details:
        get_node_details(args.details)
    else:
        list_nodes()

if __name__ == "__main__":
    main()