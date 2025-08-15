"""
Cluster management service for Nutanix PXE/Config Server
Handles cluster creation and configuration after node deployment using SSH
"""
import logging
import json
import time
import subprocess
import paramiko
from database import Database
from config import Config

logger = logging.getLogger(__name__)

# Set up more detailed logging for debugging
logger.setLevel(logging.DEBUG)

class ClusterManager:
    def __init__(self):
        self.db = Database()
        self.config = Config
        self.default_ssh_user = 'nutanix'
        self.default_ssh_password = 'nutanix/4u'
    
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
        
        # Create cluster using SSH approach
        cluster_name = cluster_config.get('cluster_name', f'cluster-{len(nodes)}-node')
        
        if cluster_type == 'single_node':
            return self._create_single_node_cluster_ssh(nodes[0], redundancy_factor, dns_servers, cluster_name)
        else:
            return self._create_standard_cluster_ssh(nodes, redundancy_factor, dns_servers, cluster_name)
    
    def _create_single_node_cluster_ssh(self, node, redundancy_factor, dns_servers, cluster_name):
        """Create a single node cluster using SSH to CVM"""
        logger.info(f"Creating single-node cluster '{cluster_name}' with node {node['id']} using SSH")
        logger.debug(f"Single-node cluster configuration: RF={redundancy_factor}, DNS={dns_servers}")
        
        # Get CVM IP for SSH connection
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
        
        # Now create the actual cluster via SSH
        try:
            logger.info(f"Connecting to CVM {cvm_ip} via SSH to create single-node cluster")
            
            # Create the cluster using SSH command
            ssh_result = self._execute_cluster_create_ssh(cvm_ip, [cvm_ip], cluster_name)
            
            if ssh_result['success']:
                logger.info(f"Successfully initiated single-node cluster creation via SSH")
                self._update_cluster_status(cluster_id, 'creating')
                
                return {
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'cluster_ip': cluster_config['cluster_ip'],
                    'status': 'creating',
                    'message': f'Single node cluster creation initiated via SSH. Output: {ssh_result["output"]}'
                }
            else:
                logger.error(f"Failed to create cluster via SSH: {ssh_result['error']}")
                self._update_cluster_status(cluster_id, 'error')
                raise Exception(f"SSH cluster creation failed: {ssh_result['error']}")
                
        except Exception as e:
            logger.error(f"Error creating single-node cluster via SSH: {str(e)}")
            self._update_cluster_status(cluster_id, 'error')
            raise Exception(f"Failed to create single-node cluster: {str(e)}")
    
    def _create_standard_cluster_ssh(self, nodes, redundancy_factor, dns_servers, cluster_name):
        """Create a standard multi-node cluster using SSH to CVM"""
        logger.info(f"Creating standard cluster '{cluster_name}' with {len(nodes)} nodes using SSH")
        logger.debug(f"Standard cluster configuration: RF={redundancy_factor}, DNS={dns_servers}")
        
        # Get CVM IPs for SSH connection (use first node for SSH, but include all in cluster create)
        primary_cvm_ip = nodes[0]['nutanix_config']['cvm_ip']
        cvm_ips = [node['nutanix_config']['cvm_ip'] for node in nodes]
        
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
        
        # Now create the actual cluster via SSH
        try:
            logger.info(f"Connecting to primary CVM {primary_cvm_ip} via SSH to create standard cluster")
            
            # Create the cluster using SSH command with all CVM IPs
            ssh_result = self._execute_cluster_create_ssh(primary_cvm_ip, cvm_ips, cluster_name)
            
            if ssh_result['success']:
                logger.info(f"Successfully initiated standard cluster creation via SSH")
                self._update_cluster_status(cluster_id, 'creating')
                
                return {
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'cluster_ip': cluster_config['cluster_ip'],
                    'status': 'creating',
                    'message': f'Standard cluster creation initiated via SSH. Output: {ssh_result["output"]}'
                }
            else:
                logger.error(f"Failed to create cluster via SSH: {ssh_result['error']}")
                self._update_cluster_status(cluster_id, 'error')
                raise Exception(f"SSH cluster creation failed: {ssh_result['error']}")
                
        except Exception as e:
            logger.error(f"Error creating standard cluster via SSH: {str(e)}")
            self._update_cluster_status(cluster_id, 'error')
            raise Exception(f"Failed to create standard cluster: {str(e)}")
    
    def _execute_cluster_create_ssh(self, primary_cvm_ip, cvm_ips, cluster_name=None):
        """Execute cluster create command via SSH"""
        try:
            # Create SSH client
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            logger.debug(f"Connecting to CVM {primary_cvm_ip} via SSH")
            
            # Connect to the primary CVM
            ssh_client.connect(
                hostname=primary_cvm_ip,
                username=self.default_ssh_user,
                password=self.default_ssh_password,
                timeout=30,
                allow_agent=False,
                look_for_keys=False
            )
            
            # Construct the cluster create command
            if len(cvm_ips) == 1:
                # Single node cluster
                cluster_cmd = f"cluster -s {cvm_ips[0]} create"
            else:
                # Multi-node cluster
                cvm_ip_list = ','.join(cvm_ips)
                cluster_cmd = f"cluster -s {cvm_ip_list} create"
            
            if cluster_name:
                cluster_cmd += f" --cluster-name {cluster_name}"
            
            logger.info(f"Executing cluster creation command: {cluster_cmd}")
            
            # Execute the command
            stdin, stdout, stderr = ssh_client.exec_command(cluster_cmd, timeout=300)
            
            # Get command output
            output = stdout.read().decode('utf-8').strip()
            error = stderr.read().decode('utf-8').strip()
            exit_code = stdout.channel.recv_exit_status()
            
            logger.debug(f"SSH command exit code: {exit_code}")
            logger.debug(f"SSH command output: {output}")
            if error:
                logger.debug(f"SSH command stderr: {error}")
            
            # Close SSH connection
            ssh_client.close()
            
            if exit_code == 0:
                return {
                    'success': True,
                    'output': output,
                    'error': error
                }
            else:
                return {
                    'success': False,
                    'output': output,
                    'error': error or f"Command failed with exit code {exit_code}"
                }
                
        except paramiko.AuthenticationException as e:
            logger.error(f"SSH authentication failed: {str(e)}")
            return {
                'success': False,
                'output': '',
                'error': f"SSH authentication failed: {str(e)}"
            }
        except paramiko.SSHException as e:
            logger.error(f"SSH connection error: {str(e)}")
            return {
                'success': False,
                'output': '',
                'error': f"SSH connection error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error during SSH cluster creation: {str(e)}")
            return {
                'success': False,
                'output': '',
                'error': f"Unexpected error: {str(e)}"
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
        """Monitor cluster creation progress via SSH status checks"""
        logger.info(f"Starting to monitor creation progress for cluster {cluster_id}")
        
        try:
            # Get cluster information
            cluster = self.get_cluster(cluster_id)
            if not cluster:
                raise Exception(f"Cluster {cluster_id} not found")
            
            # Get the primary CVM IP for status checks
            # In a real implementation, we would get this from the cluster's nodes
            primary_cvm_ip = cluster.get('cluster_ip')  # Using cluster IP as fallback
            
            if not primary_cvm_ip:
                logger.error(f"No CVM IP found for cluster {cluster_id}")
                return False
            
            # Start monitoring loop
            start_time = time.time()
            timeout_seconds = timeout_minutes * 60
            
            while (time.time() - start_time) < timeout_seconds:
                try:
                    logger.debug(f"Checking cluster {cluster_id} status via SSH")
                    
                    # Check cluster status via SSH
                    status_result = self._check_cluster_status_ssh(primary_cvm_ip)
                    
                    if status_result['success']:
                        cluster_status = status_result.get('status', '').upper()
                        if 'UP' in cluster_status or 'NORMAL' in cluster_status:
                            logger.info(f"Cluster {cluster_id} is UP and running")
                            self._update_cluster_status(cluster_id, 'created')
                            return True
                        else:
                            logger.debug(f"Cluster status: {cluster_status}")
                    else:
                        logger.debug(f"Status check failed: {status_result.get('error', 'Unknown error')}")
                    
                except Exception as e:
                    logger.warning(f"Error checking cluster status: {str(e)}")
                
                logger.debug(f"Waiting for cluster {cluster_id} formation...")
                time.sleep(30)  # Wait 30 seconds between checks
            
            logger.error(f"Cluster creation monitoring timed out after {timeout_minutes} minutes")
            self._update_cluster_status(cluster_id, 'error')
            return False
            
        except Exception as e:
            logger.error(f"Failed to monitor cluster {cluster_id} creation: {str(e)}")
            self._update_cluster_status(cluster_id, 'error')
            return False
    
    def _check_cluster_status_ssh(self, cvm_ip):
        """Check cluster status via SSH"""
        try:
            # Create SSH client
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect to the CVM
            ssh_client.connect(
                hostname=cvm_ip,
                username=self.default_ssh_user,
                password=self.default_ssh_password,
                timeout=30,
                allow_agent=False,
                look_for_keys=False
            )
            
            # Execute cluster status command
            status_cmd = "cluster status"
            logger.debug(f"Executing status check command: {status_cmd}")
            
            stdin, stdout, stderr = ssh_client.exec_command(status_cmd, timeout=60)
            
            # Get command output
            output = stdout.read().decode('utf-8').strip()
            error = stderr.read().decode('utf-8').strip()
            exit_code = stdout.channel.recv_exit_status()
            
            # Close SSH connection
            ssh_client.close()
            
            if exit_code == 0:
                return {
                    'success': True,
                    'status': output,
                    'error': error
                }
            else:
                return {
                    'success': False,
                    'status': output,
                    'error': error or f"Status check failed with exit code {exit_code}"
                }
                
        except Exception as e:
            logger.error(f"Error checking cluster status via SSH: {str(e)}")
            return {
                'success': False,
                'status': '',
                'error': f"SSH status check error: {str(e)}"
            }