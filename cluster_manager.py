"""
Cluster management service for Nutanix PXE/Config Server
Handles cluster creation and configuration after node deployment
"""
import logging
import json
import time
import requests
from requests.exceptions import RequestException
from database import Database
from config import Config

logger = logging.getLogger(__name__)

# Set up more detailed logging for debugging
logger.setLevel(logging.DEBUG)

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
        logger.debug(f"Validating cluster type: {cluster_type} with {len(nodes)} nodes")
        
        if cluster_type == 'single_node' and len(nodes) > 1:
            logger.error(f"Attempted to create single node cluster with {len(nodes)} nodes")
            raise Exception("Single node cluster can only be created with one node")
        elif cluster_type == 'standard' and len(nodes) < 3:
            logger.error(f"Attempted to create standard cluster with only {len(nodes)} nodes")
            raise Exception("Standard cluster requires at least 3 nodes")
        elif cluster_type == 'standard' and len(nodes) > 4:
            logger.warning(f"Creating a standard cluster with {len(nodes)} nodes. Nutanix CE typically supports 1, 3, or 4 node clusters.")
        
        # Log important note about single-node clusters
        if cluster_type == 'single_node':
            logger.warning("IMPORTANT: Single-node clusters cannot be expanded to multi-node clusters later. "
                          "To expand to a multi-node cluster, you must create a new cluster.")
        
        # Get CVM IPs for cluster creation
        cvm_ips = [node['nutanix_config']['cvm_ip'] for node in nodes]
        cvm_ip_list = ','.join(cvm_ips)
        
        # Determine redundancy factor based on node count and cluster type
        if cluster_type == 'single_node':
            redundancy_factor = 1
        elif len(nodes) == 3:
            redundancy_factor = 2
        else:  # 4 or more nodes
            redundancy_factor = 2  # Could be set to 3 for larger clusters if needed
        
        logger.debug(f"Setting redundancy factor to {redundancy_factor} for {cluster_type} cluster with {len(nodes)} nodes")
        
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
        logger.info(f"Creating single-node cluster '{cluster_name}' with node {node['id']}")
        logger.debug(f"Single-node cluster configuration: RF={redundancy_factor}, DNS={dns_servers}")
        
        # Get CVM IP for API calls
        cvm_ip = node['nutanix_config']['cvm_ip']
        
        # First register the cluster in the database
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
        logger.debug(f"Single node cluster details: {cluster_config}")
        
        # Now attempt to create the actual cluster via Prism API
        try:
            # Prepare cluster creation payload for Prism API
            prism_cluster_config = {
                "name": cluster_name,
                "external_ip": cluster_config['cluster_ip'],
                "redundancy_factor": redundancy_factor,
                "cluster_functions": ["AOS"],
                "timezone": "UTC",
                "dns_servers": dns_servers.split(',')
            }
            
            # Make API call to create cluster
            logger.debug(f"Calling Prism API to create single-node cluster on CVM {cvm_ip}")
            response = self._call_prism_api(cvm_ip, prism_cluster_config)
            
            if response:
                logger.info(f"Successfully initiated cluster creation via Prism API")
                # Start monitoring cluster creation in background (in a real implementation)
                # For now, we'll just update the status
                self._update_cluster_status(cluster_id, 'creating')
                
                return {
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'cluster_ip': cluster_config['cluster_ip'],
                    'status': 'creating',
                    'message': 'Single node cluster creation initiated via Prism API.'
                }
            else:
                logger.warning(f"Failed to initiate cluster creation via Prism API, falling back to post-install script")
                return {
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'cluster_ip': cluster_config['cluster_ip'],
                    'status': 'creating',
                    'message': 'Single node cluster registered. Post-install script will create the cluster.'
                }
        except Exception as e:
            logger.error(f"Error creating cluster via Prism API: {str(e)}")
            logger.info("Falling back to post-install script method")
            return {
                'cluster_id': cluster_id,
                'cluster_name': cluster_name,
                'cluster_ip': cluster_config['cluster_ip'],
                'status': 'creating',
                'message': 'Single node cluster registered. Post-install script will create the cluster.'
            }
    
    def _create_standard_cluster(self, nodes, redundancy_factor, dns_servers, cluster_name):
        """Create a standard multi-node cluster"""
        logger.info(f"Creating standard cluster '{cluster_name}' with {len(nodes)} nodes")
        logger.debug(f"Standard cluster configuration: RF={redundancy_factor}, DNS={dns_servers}")
        
        # Get CVM IP for API calls (using first node)
        cvm_ip = nodes[0]['nutanix_config']['cvm_ip']
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
        logger.debug(f"Standard cluster details: {cluster_config}")
        
        # Now attempt to create the actual cluster via Prism API
        try:
            # Prepare cluster creation payload for Prism API
            prism_cluster_config = {
                "name": cluster_name,
                "external_ip": cluster_config['cluster_ip'],
                "redundancy_factor": redundancy_factor,
                "cluster_functions": ["AOS"],
                "timezone": "UTC",
                "dns_servers": dns_servers.split(',')
            }
            
            # Make API call to create cluster
            logger.debug(f"Calling Prism API to create standard cluster on CVM {cvm_ip}")
            response = self._call_prism_api(cvm_ip, prism_cluster_config)
            
            if response:
                logger.info(f"Successfully initiated cluster creation via Prism API")
                # Start monitoring cluster creation in background (in a real implementation)
                # For now, we'll just update the status
                self._update_cluster_status(cluster_id, 'creating')
                
                return {
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'cluster_ip': cluster_config['cluster_ip'],
                    'status': 'creating',
                    'message': 'Standard cluster creation initiated via Prism API.'
                }
            else:
                logger.warning(f"Failed to initiate cluster creation via Prism API, falling back to Foundation")
                return {
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'cluster_ip': cluster_config['cluster_ip'],
                    'status': 'creating',
                    'message': 'Standard cluster registered. Foundation will create the cluster during node deployment.'
                }
        except Exception as e:
            logger.error(f"Error creating cluster via Prism API: {str(e)}")
            logger.info("Falling back to Foundation method")
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
            logger.debug(f"Updating node {node_id} with cluster info for cluster {cluster_id}")
            self.db.update_node_with_cluster_info(node_id, cluster_id, cluster_config)
            logger.debug(f"Successfully updated node {node_id} with cluster info")
        except Exception as e:
            logger.error(f"Failed to update node {node_id} with cluster info: {str(e)}")
            logger.debug(f"Cluster config that failed: {cluster_config}")
            raise
    
    def get_cluster(self, cluster_id):
        """Get cluster information"""
        try:
            logger.debug(f"Retrieving information for cluster {cluster_id}")
            cluster = self.db.get_cluster_by_id(cluster_id)
            if not cluster:
                logger.error(f"Cluster {cluster_id} not found in database")
                raise Exception(f"Cluster {cluster_id} not found")
            logger.debug(f"Successfully retrieved cluster {cluster_id}")
            return cluster
        except Exception as e:
            logger.error(f"Failed to get cluster {cluster_id}: {str(e)}")
            raise
    
    def list_clusters(self):
        """List all clusters"""
        try:
            logger.debug("Listing all clusters")
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM clusters ORDER BY created_at DESC")
                    clusters = cur.fetchall()
                    cluster_list = [{'id': c[0], 'name': c[1], 'status': c[6]} for c in clusters]
                    logger.debug(f"Found {len(cluster_list)} clusters")
                    return cluster_list
        except Exception as e:
            logger.error(f"Failed to list clusters: {str(e)}")
            raise
    
    def delete_cluster(self, cluster_id):
        """Delete cluster information (does not delete actual cluster)"""
        try:
            logger.info(f"Deleting cluster {cluster_id} from database (not deleting actual cluster)")
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM clusters WHERE id = %s", (cluster_id,))
                    conn.commit()
                    logger.info(f"Cluster {cluster_id} deleted from database")
        except Exception as e:
            logger.error(f"Failed to delete cluster {cluster_id}: {str(e)}")
            raise
            
    def _call_prism_api(self, cvm_ip, cluster_config, timeout=30):
        """Call Prism API to create a cluster"""
        try:
            prism_url = f"https://{cvm_ip}:9440"
            
            logger.debug(f"Making API call to {prism_url} with config: {json.dumps(cluster_config)}")
            
            # In a real implementation, this would make an actual API call
            # For now, we'll simulate a successful response
            logger.debug("Simulating successful API response (in real implementation, this would call the actual API)")
            
            # Uncomment the following code to make the actual API call
            """
            response = requests.post(
                f"{prism_url}/PrismGateway/services/rest/v2.0/clusters",
                json=cluster_config,
                auth=('admin', 'admin'),  # Default Prism credentials
                verify=False,
                timeout=timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API call failed with status {response.status_code}: {response.text}")
                return None
            """
            
            # Simulated successful response
            return {"status": "accepted"}
            
        except RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in API call: {str(e)}")
            return None
    
    def _update_cluster_status(self, cluster_id, status):
        """Update cluster status in database"""
        try:
            logger.debug(f"Updating cluster {cluster_id} status to '{status}'")
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE clusters SET status = %s WHERE id = %s", (status, cluster_id))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update cluster {cluster_id} status: {str(e)}")
            return False
    
    def monitor_cluster_creation(self, cluster_id, timeout_minutes=30):
        """Monitor cluster creation progress"""
        logger.info(f"Starting to monitor creation progress for cluster {cluster_id}")
        
        try:
            # Get cluster information
            cluster = self.get_cluster(cluster_id)
            if not cluster:
                raise Exception(f"Cluster {cluster_id} not found")
            
            # Get a node from the cluster to access its CVM
            # In a real implementation, we would query the database to get a node
            # For now, we'll assume we have a node with a CVM IP
            cvm_ip = cluster.get('cluster_ip')  # Using cluster IP as a fallback
            
            if not cvm_ip:
                logger.error(f"No CVM IP found for cluster {cluster_id}")
                return False
            
            # Start monitoring loop
            start_time = time.time()
            timeout_seconds = timeout_minutes * 60
            
            while (time.time() - start_time) < timeout_seconds:
                try:
                    # In a real implementation, this would make an API call to check cluster status
                    # For now, we'll simulate a successful response after a delay
                    logger.debug(f"Checking cluster {cluster_id} status via Prism API")
                    
                    # Simulate API call delay
                    time.sleep(2)
                    
                    # Uncomment the following code to make the actual API call
                    """
                    response = requests.get(
                        f"https://{cvm_ip}:9440/PrismGateway/services/rest/v2.0/cluster",
                        auth=('admin', 'admin'),
                        verify=False,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        cluster_status = response.json()
                        if cluster_status.get('cluster_status') == 'UP':
                            logger.info(f"Cluster {cluster_id} is UP and running")
                            self._update_cluster_status(cluster_id, 'created')
                            return True
                        else:
                            logger.debug(f"Cluster status: {cluster_status.get('cluster_status')}")
                    """
                    
                    # Simulate successful cluster creation
                    logger.info(f"Cluster {cluster_id} is UP and running (simulated)")
                    self._update_cluster_status(cluster_id, 'created')
                    return True
                    
                except Exception as e:
                    logger.warning(f"Error checking cluster status: {str(e)}")
                
                logger.debug(f"Waiting for cluster {cluster_id} formation...")
                time.sleep(10)
            
            logger.error(f"Cluster creation timed out after {timeout_minutes} minutes")
            self._update_cluster_status(cluster_id, 'error')
            return False
            
        except Exception as e:
            logger.error(f"Failed to monitor cluster {cluster_id} creation: {str(e)}")
            self._update_cluster_status(cluster_id, 'error')
            return False