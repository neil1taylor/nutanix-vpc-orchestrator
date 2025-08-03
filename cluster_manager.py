"""
Cluster management service for Nutanix PXE/Config Server
Handles cluster creation and configuration after node deployment
"""
import logging
import json
from database import Database
from config import Config

logger = logging.getLogger(__name__)

class ClusterManager:
    def __init__(self):
        self.db = Database()
        self.config = Config
    
    def create_cluster(self, cluster_request):
        """Create a new Nutanix cluster from deployed nodes"""
        cluster_config = cluster_request['cluster_config']
        node_names = cluster_config['nodes']
        
        # Validate nodes exist and are deployed
        nodes = []
        for node_name in node_names:
            node = self.db.get_node_by_name(node_name)
            if not node:
                raise Exception(f"Node {node_name} not found")
            if node['deployment_status'] != 'deployed':
                raise Exception(f"Node {node_name} is not deployed (status: {node['deployment_status']})")
            nodes.append(node)
        
        # Validate cluster type and node count
        cluster_type = cluster_config.get('cluster_type', 'standard')
        if cluster_type == 'single_node' and len(nodes) > 1:
            raise Exception("Single node cluster can only be created with one node")
        elif cluster_type == 'standard' and len(nodes) < 3:
            raise Exception("Standard cluster requires at least 3 nodes")
        
        # Get CVM IPs for cluster creation
        cvm_ips = [node['nutanix_config']['cvm_ip'] for node in nodes]
        cvm_ip_list = ','.join(cvm_ips)
        
        # Determine redundancy factor
        redundancy_factor = 1 if cluster_type == 'single_node' else 2
        
        # Get DNS servers from first node or use defaults
        dns_servers = nodes[0]['nutanix_config'].get('dns_servers', ['8.8.8.8'])
        dns_server_list = ','.join(dns_servers)
        
        # Create cluster using post-install script approach
        cluster_name = cluster_config.get('cluster_name', f'cluster-{len(nodes)}-node')
        
        # For single node cluster, we'll trigger the post-install script
        # For multi-node cluster, we'll need to coordinate with Foundation
        if cluster_type == 'single_node':
            return self._create_single_node_cluster(nodes[0], redundancy_factor, dns_server_list, cluster_name)
        else:
            return self._create_standard_cluster(nodes, redundancy_factor, dns_server_list, cluster_name)
    
    def _create_single_node_cluster(self, node, redundancy_factor, dns_servers, cluster_name):
        """Create a single node cluster by triggering post-install script"""
        # This would typically be handled by the post-install script
        # For now, we'll just register the cluster in the database
        cluster_config = {
            'cluster_name': cluster_name,
            'cluster_ip': node['nutanix_config']['cluster_ip'],
            'cluster_dns': f'{cluster_name}.{self.config.DNS_ZONE_NAME}',
            'created_by_node': node['id'],
            'node_count': 1,
            'status': 'creating'
        }
        
        cluster_id = self.db.register_cluster(cluster_config)
        
        # Update node with cluster information
        self._update_node_with_cluster_info(node['id'], cluster_id, cluster_config)
        
        logger.info(f"Single node cluster {cluster_name} registered (ID: {cluster_id})")
        
        return {
            'cluster_id': cluster_id,
            'cluster_name': cluster_name,
            'cluster_ip': cluster_config['cluster_ip'],
            'status': 'creating',
            'message': 'Single node cluster registered. Post-install script will create the cluster.'
        }
    
    def _create_standard_cluster(self, nodes, redundancy_factor, dns_servers, cluster_name):
        """Create a standard multi-node cluster"""
        # For standard clusters, Foundation handles the creation
        # We'll register the cluster in the database
        cluster_config = {
            'cluster_name': cluster_name,
            'cluster_ip': nodes[0]['nutanix_config']['cluster_ip'],
            'cluster_dns': f'{cluster_name}.{self.config.DNS_ZONE_NAME}',
            'created_by_node': nodes[0]['id'],
            'node_count': len(nodes),
            'status': 'creating'
        }
        
        cluster_id = self.db.register_cluster(cluster_config)
        
        # Update all nodes with cluster information
        for node in nodes:
            self._update_node_with_cluster_info(node['id'], cluster_id, cluster_config)
        
        logger.info(f"Standard cluster {cluster_name} registered (ID: {cluster_id})")
        
        return {
            'cluster_id': cluster_id,
            'cluster_name': cluster_name,
            'cluster_ip': cluster_config['cluster_ip'],
            'status': 'creating',
            'message': 'Standard cluster registered. Foundation will create the cluster during node deployment.'
        }
    
    def _update_node_with_cluster_info(self, node_id, cluster_id, cluster_config):
        """Update node with cluster information"""
        try:
            self.db.update_node_with_cluster_info(node_id, cluster_id, cluster_config)
        except Exception as e:
            logger.error(f"Failed to update node {node_id} with cluster info: {str(e)}")
            raise
    
    def get_cluster(self, cluster_id):
        """Get cluster information"""
        try:
            cluster = self.db.get_cluster_by_id(cluster_id)
            if not cluster:
                raise Exception(f"Cluster {cluster_id} not found")
            return cluster
        except Exception as e:
            logger.error(f"Failed to get cluster {cluster_id}: {str(e)}")
            raise
    
    def list_clusters(self):
        """List all clusters"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM clusters ORDER BY created_at DESC")
                    clusters = cur.fetchall()
                    return [{'id': c[0], 'name': c[1], 'status': c[6]} for c in clusters]
        except Exception as e:
            logger.error(f"Failed to list clusters: {str(e)}")
            raise
    
    def delete_cluster(self, cluster_id):
        """Delete cluster information (does not delete actual cluster)"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM clusters WHERE id = %s", (cluster_id,))
                    conn.commit()
                    logger.info(f"Cluster {cluster_id} deleted from database")
        except Exception as e:
            logger.error(f"Failed to delete cluster {cluster_id}: {str(e)}")
            raise