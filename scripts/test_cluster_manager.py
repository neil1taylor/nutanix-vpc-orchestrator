#!/usr/bin/env python3
"""
Test script for cluster_manager.py
Simulates cluster creation and verifies the updated implementation
"""
import sys
import os
import logging
import json
from unittest.mock import MagicMock, patch

# Add parent directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cluster_manager import ClusterManager

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MockDatabase:
    """Mock Database class for testing"""
    
    def __init__(self):
        self.clusters = {}
        self.nodes = {}
        self.cluster_id_counter = 1
    
    def register_cluster(self, cluster_config):
        """Register a cluster in the mock database"""
        cluster_id = self.cluster_id_counter
        self.cluster_id_counter += 1
        
        self.clusters[cluster_id] = {
            'id': cluster_id,
            'name': cluster_config['cluster_name'],
            'cluster_ip': cluster_config['cluster_ip'],
            'cluster_dns': cluster_config['cluster_dns'],
            'created_by_node': cluster_config['created_by_node'],
            'node_count': cluster_config['node_count'],
            'status': cluster_config['status']
        }
        
        return cluster_id
    
    def update_node_with_cluster_info(self, node_id, cluster_id, cluster_config):
        """Update node with cluster information"""
        if node_id not in self.nodes:
            self.nodes[node_id] = {'id': node_id}
        
        self.nodes[node_id]['cluster_id'] = cluster_id
        self.nodes[node_id]['cluster_name'] = cluster_config['cluster_name']
        self.nodes[node_id]['cluster_ip'] = cluster_config['cluster_ip']
    
    def get_cluster_by_id(self, cluster_id):
        """Get cluster by ID"""
        return self.clusters.get(cluster_id)
    
    def get_node_by_name(self, node_name):
        """Get node by name"""
        # Create a mock node if it doesn't exist
        if node_name not in self.nodes:
            node_id = len(self.nodes) + 1
            self.nodes[node_name] = {
                'id': node_id,
                'name': node_name,
                'deployment_status': 'deployed',
                'nutanix_config': {
                    'cvm_ip': f'10.240.0.{100 + node_id}',
                    'cluster_ip': '10.240.0.200',
                    'dns_servers': ['8.8.8.8']
                }
            }
        
        return self.nodes[node_name]
    
    def get_connection(self):
        """Get a mock database connection"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        return mock_conn

def test_create_single_node_cluster():
    """Test creating a single-node cluster"""
    logger.info("Testing single-node cluster creation")
    
    # Create a ClusterManager with a mock database
    db = MockDatabase()
    manager = ClusterManager()
    manager.db = db
    
    # Create a cluster request
    cluster_request = {
        'cluster_config': {
            'cluster_type': 'single_node',
            'cluster_name': 'test-single-node',
            'nodes': ['node1']
        }
    }
    
    # Create the cluster
    result = manager.create_cluster(cluster_request)
    
    # Verify the result
    logger.info(f"Single-node cluster creation result: {json.dumps(result, indent=2)}")
    assert result['cluster_name'] == 'test-single-node'
    assert result['status'] == 'creating'
    
    # Test monitoring cluster creation
    monitor_result = manager.monitor_cluster_creation(result['cluster_id'])
    logger.info(f"Monitoring result: {monitor_result}")
    
    logger.info("Single-node cluster test completed successfully")
    return result['cluster_id']

def test_create_standard_cluster(node_count=3):
    """Test creating a standard cluster"""
    logger.info(f"Testing standard cluster creation with {node_count} nodes")
    
    # Create a ClusterManager with a mock database
    db = MockDatabase()
    manager = ClusterManager()
    manager.db = db
    
    # Create node names
    nodes = [f'node{i+1}' for i in range(node_count)]
    
    # Create a cluster request
    cluster_request = {
        'cluster_config': {
            'cluster_type': 'standard',
            'cluster_name': f'test-standard-{node_count}-node',
            'nodes': nodes
        }
    }
    
    # Create the cluster
    result = manager.create_cluster(cluster_request)
    
    # Verify the result
    logger.info(f"Standard cluster creation result: {json.dumps(result, indent=2)}")
    assert result['cluster_name'] == f'test-standard-{node_count}-node'
    assert result['status'] == 'creating'
    
    # Test monitoring cluster creation
    monitor_result = manager.monitor_cluster_creation(result['cluster_id'])
    logger.info(f"Monitoring result: {monitor_result}")
    
    logger.info(f"Standard {node_count}-node cluster test completed successfully")
    return result['cluster_id']

def main():
    """Main test function"""
    logger.info("Starting cluster manager tests")
    
    # Test creating a single-node cluster
    single_node_cluster_id = test_create_single_node_cluster()
    
    # Test creating a standard cluster with 3 nodes
    standard_3_node_cluster_id = test_create_standard_cluster(3)
    
    # Test creating a standard cluster with 4 nodes
    standard_4_node_cluster_id = test_create_standard_cluster(4)
    
    logger.info("All tests completed successfully")
    logger.info(f"Created clusters: single-node={single_node_cluster_id}, "
                f"standard-3-node={standard_3_node_cluster_id}, "
                f"standard-4-node={standard_4_node_cluster_id}")

if __name__ == "__main__":
    main()