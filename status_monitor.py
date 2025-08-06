"""
Status monitoring service for deployment progress tracking
"""
import logging
from datetime import datetime, timedelta
from database import Database
from config import Config

logger = logging.getLogger(__name__)

class StatusMonitor:
    def __init__(self):
        self.db = Database()
        self.config = Config()
        self.deployment_phases = [
            'ipxe_boot',
            'config_download',
            'foundation_start',
            'storage_discovery',
            'image_download',
            'installation',
            'cluster_formation',
            'dns_registration',
            'health_validation'
        ]
    
    def get_deployment_status(self, server_ip):
        """Get current deployment status for a server"""
        node = self.db.get_node_by_management_ip(server_ip)
        
        if not node:
            logger.error(f"Status requested for unknown server: {server_ip}")
            return None
        
        # Get latest status
        current_status = self.db.get_latest_deployment_status(node['id'])
        
        if not current_status:
            # No status found, return default
            current_status = {
                'phase': 'pending',
                'status': 'waiting',
                'message': 'Deployment not started',
                'timestamp': datetime.now()
            }
        
        # Calculate elapsed time and progress
        deployment_start = self.get_deployment_start_time(node['id'])
        elapsed_time = (datetime.now() - deployment_start).total_seconds() if deployment_start else 0
        
        # Determine if deployment has timed out
        total_timeout = sum(Config.DEPLOYMENT_TIMEOUTS.values())
        timed_out = elapsed_time > total_timeout
        
        # Calculate progress percentage
        progress_percent = self.calculate_progress_percentage(
            current_status['phase'],
            elapsed_time
        )
        
        response = {
            'server_ip': server_ip,
            'server_name': node['node_name'],
            'node_id': node['id'],
            'deployment_id': node.get('bare_metal_id'),
            'current_phase': current_status['phase'],
            'phase_status': current_status['status'],
            'progress_percent': progress_percent,
            'elapsed_time_seconds': int(elapsed_time),
            'estimated_remaining_seconds': max(0, total_timeout - elapsed_time),
            'timed_out': timed_out,
            'last_update': current_status['timestamp'].isoformat(),
            'message': current_status['message']
        }
        
        return response
    
    def update_deployment_phase(self, data):
        """Receive phase updates from deploying servers"""
        required_fields = ['server_ip', 'phase', 'status', 'message']
        for field in required_fields:
            if field not in data:
                raise ValueError(f'Missing required field: {field}')
        
        node = self.db.get_node_by_management_ip(data['server_ip'])
        if not node:
            raise ValueError(f"Server {data['server_ip']} not found")
        
        # Log the phase update
        self.db.log_deployment_event(
            node['id'],
            data['phase'],
            data['status'],
            data['message']
        )
        
        # Update server deployment status in main table
        new_status = ''
        if data['phase'] in ['health_validation'] and data['status'] == 'success':
            new_status = 'deployed'
            self.db.update_node_status(node['id'], new_status)
            logger.info(f"Server {node['node_name']} status changed to: RUNNING")
        elif data['status'] == 'failed':
            new_status = 'failed'
            self.db.update_node_status(node['id'], new_status)
            logger.info(f"Server {node['node_name']} status changed to: FAILED")
        else:
            new_status = f"{data['phase']}_{data['status']}"
            self.db.update_node_status(node['id'], new_status)
            
            # Log specific state transitions
            if data['phase'] == 'ipxe_boot' and data['status'] == 'in_progress':
                logger.info(f"Server {node['node_name']} status changed to: STARTING")
            elif data['phase'] == 'foundation_start' and data['status'] == 'in_progress':
                logger.info(f"Server {node['node_name']} status changed to: INSTALLING")

        # Log detailed status information
        if data['status'] == 'failed':
            logger.info(f"Deployment failed for {node['node_name']}: {data['message']}")
        elif data['phase'] == 'cluster_formation' and data['status'] == 'success':
            logger.info(f"Cluster formation successful for {node['node_name']}")
        elif data['phase'] == 'health_validation' and data['status'] == 'success':
            logger.info(f"Health validation successful for {node['node_name']}")
            
        # Log all status changes with details
        logger.info(f"Server {node['node_name']} status update: phase={data['phase']}, status={data['status']}, new_state={new_status}")

        logger.info(f"Phase update for {node['node_name']}: {data['phase']} - {data['status']}")
        
        # Check if this is a bare metal server status update
        if 'server_status' in data:
            # Log IBM Cloud server lifecycle state transitions
            server_status = data['server_status']
            logger.info(f"Server {node['node_name']} IBM Cloud status changed to: {server_status.upper()}")
            
            # Log specific state transitions with more visibility
            if server_status == 'starting':
                logger.info(f"⚡ SERVER STARTING: {node['node_name']} is booting up")
                # Log to deployment history table
                self.db.log_deployment_event(
                    node['id'],
                    'ibm_cloud_status',
                    'starting',
                    f"Server is starting up"
                )
            elif server_status == 'running':
                logger.info(f"✅ SERVER RUNNING: {node['node_name']} is now active and running")
                # Log to deployment history table
                self.db.log_deployment_event(
                    node['id'],
                    'ibm_cloud_status',
                    'success',
                    f"Server is now running"
                )
            elif server_status == 'stopped':
                logger.info(f"⏹️ SERVER STOPPED: {node['node_name']} is currently stopped")
                # Log to deployment history table
                self.db.log_deployment_event(
                    node['id'],
                    'ibm_cloud_status',
                    'stopped',
                    f"Server is stopped"
                )
            elif server_status == 'failed':
                logger.error(f"❌ SERVER FAILED: {node['node_name']} deployment has failed")
                # Log to deployment history table
                self.db.log_deployment_event(
                    node['id'],
                    'ibm_cloud_status',
                    'failed',
                    f"Server deployment has failed"
                )
            else:
                # Log any other status changes
                logger.info(f"ℹ️ SERVER STATUS: {node['node_name']} status is {server_status}")
                # Log to deployment history table
                self.db.log_deployment_event(
                    node['id'],
                    'ibm_cloud_status',
                    'in_progress',
                    f"Server status changed to {server_status}"
                )
        
        return {'message': 'Status updated successfully'}

    def collect_and_store_health_metrics(self, node_id):
        """Collect and store health metrics for a node"""
        try:
            # Simulate health metric collection
            cpu_usage = self.get_cpu_usage(node_id)
            memory_usage = self.get_memory_usage(node_id)
            disk_space = self.get_disk_space(node_id)
            network_latency = self.get_network_latency(node_id)
            custom_metrics = self.get_custom_metrics(node_id)

            # Store health metrics in the database
            self.db.insert_node_health(
                node_id,
                cpu_usage,
                memory_usage,
                disk_space,
                network_latency,
                custom_metrics
            )
        except Exception as e:
            logger.error(f"Failed to collect and store health metrics for node {node_id}: {str(e)}")
            raise

    def get_cpu_usage(self, node_id):
        """Simulate getting CPU usage"""
        return 50.0  # Placeholder value

    def get_memory_usage(self, node_id):
        """Simulate getting memory usage"""
        return 75.0  # Placeholder value

    def get_disk_space(self, node_id):
        """Simulate getting disk space"""
        return 80.0  # Placeholder value

    def get_network_latency(self, node_id):
        """Simulate getting network latency"""
        return 10.0  # Placeholder value

    def get_custom_metrics(self, node_id):
        """Simulate getting custom metrics"""
        return {"metric1": 100, "metric2": 200}  # Placeholder value
    
def get_deployment_history(self, server_ip):
    """Get complete deployment history for a server"""
    node = self.db.get_node_by_management_ip(server_ip)
    
    if not node:
        return None
    
    history = self.db.get_deployment_history(node['id'])
    
    return {
        'server_ip': server_ip,
        'node_name': node['node_name'],
        'deployment_history': [
            {
                'phase': event['phase'],
                'status': event['status'],
                'message': event['message'],
                'timestamp': event['timestamp'].isoformat()
            }
            for event in history
        ]
    }

def calculate_progress_percentage(self, current_phase, elapsed_time):
    """Calculate deployment progress as percentage"""
    if current_phase not in self.deployment_phases:
        return 0
    
    # Calculate total expected time
    total_expected_time = sum(Config.DEPLOYMENT_TIMEOUTS.values())
    
    # Calculate time for completed phases
    current_phase_index = self.deployment_phases.index(current_phase)
    completed_phases_time = sum(
        Config.DEPLOYMENT_TIMEOUTS[self.deployment_phases[i]]
        for i in range(current_phase_index)
    )
    
    # Add progress within current phase (estimate based on elapsed time)
    current_phase_timeout = Config.DEPLOYMENT_TIMEOUTS[current_phase]
    phase_start_time = completed_phases_time
    current_phase_elapsed = max(0, elapsed_time - phase_start_time)
    current_phase_progress = min(100, (current_phase_elapsed / current_phase_timeout) * 100)
    
    # Calculate overall progress
    completed_progress = (completed_phases_time / total_expected_time) * 100
    current_phase_weight = (current_phase_timeout / total_expected_time) * 100
    current_phase_contribution = (current_phase_progress / 100) * current_phase_weight
    
    total_progress = completed_progress + current_phase_contribution
    
    return min(100, max(0, int(total_progress)))

def get_deployment_start_time(self, node_id):
    """Get deployment start time for a node"""
    history = self.db.get_deployment_history(node_id)
    if history:
        return history[0]['timestamp']
    return datetime.now()

def handle_deployment_failure(self, node_id, failure_data):
    """Handle deployment failure"""
    try:
        node = self.db.get_node(node_id)
        
        logger.error(f"Deployment failed for {node['node_name']}: {failure_data['message']}")
        
        # Update node status
        self.db.update_node_status(node_id, 'failed')
        
        # Log detailed failure information
        self.db.log_deployment_event(
            node_id,
            'deployment_failed',
            'failed',
            f"Deployment failed in phase {failure_data['phase']}: {failure_data['message']}"
        )
        
        # Trigger cleanup
        logger.warning(f"Initiating cleanup for failed deployment: {node['node_name']}")
        cleanup_result = self.cleanup_service.cleanup_failed_provisioning(node['node_name'])
        
        if cleanup_result.get('success'):
            logger.info(f"Cleanup completed successfully for {node['node_name']}")
            logger.info(f"Cleanup summary: {cleanup_result.get('successful_operations', 0)}/{cleanup_result.get('total_operations', 0)} operations successful")
        else:
            logger.error(f"Cleanup failed for {node['node_name']}: {cleanup_result.get('error', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Error handling deployment failure for {node_id}: {str(e)}")
        logger.error(f"Failed to update node status or log deployment event: {str(e)}")
        logger.error(f"Failed to trigger cleanup for {node['node_name']}: {str(e)}")

def handle_cluster_formation_complete(self, node_id, completion_data):
    """Handle deployment failure"""
    try:
        node = self.db.get_node(node_id)
        
        logger.error(f"Deployment failed for {node['node_name']}: {failure_data['message']}")
        
        # Update node status
        self.db.update_node_status(node_id, 'failed')
        
        # Log detailed failure information
        self.db.log_deployment_event(
            node_id,
            'deployment_failed',
            'failed',
            f"Deployment failed in phase {failure_data['phase']}: {failure_data['message']}"
        )
        
        # Trigger cleanup
        logger.warning(f"Initiating cleanup for failed deployment: {node['node_name']}")
        cleanup_result = self.cleanup_service.cleanup_failed_provisioning(node['node_name'])
        
        if cleanup_result.get('success'):
            logger.info(f"Cleanup completed successfully for {node['node_name']}")
            logger.info(f"Cleanup summary: {cleanup_result.get('successful_operations', 0)}/{cleanup_result.get('total_operations', 0)} operations successful")
        else:
            logger.error(f"Cleanup failed for {node['node_name']}: {cleanup_result.get('error', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Error handling deployment failure for {node_id}: {str(e)}")
        logger.error(f"Failed to update node status or log deployment event: {str(e)}")
        logger.error(f"Failed to trigger cleanup for {node['node_name']}: {str(e)}")

def collect_and_store_health_metrics(self, node_id):
    """Collect and store health metrics for a node"""
    try:
        # Simulate health metric collection
        cpu_usage = self.get_cpu_usage(node_id)
        memory_usage = self.get_memory_usage(node_id)
        disk_space = self.get_disk_space(node_id)
        network_latency = self.get_network_latency(node_id)
        custom_metrics = self.get_custom_metrics(node_id)

        # Store health metrics in the database
        self.db.insert_node_health(
            node_id,
            cpu_usage,
            memory_usage,
            disk_space,
            network_latency,
            custom_metrics
        )
    except Exception as e:
        logger.error(f"Failed to collect and store health metrics for node {node_id}: {str(e)}")
        raise

    def handle_cluster_formation_complete(self, node_id, completion_data):
        """Handle cluster formation completion"""
        node = self.db.get_node(node_id)
        
        # Check if this is the first node (cluster creation)
        if self.db.is_first_node() or not self.db.get_cluster_info():
            self.register_new_cluster(node_id, completion_data)
        else:
            self.handle_node_addition_complete(node_id, completion_data)

    def register_new_cluster(self, node_id, completion_data):
        """Register a new cluster in the database"""
        node = self.db.get_node(node_id)
        
        cluster_config = {
            'cluster_name': completion_data.get('cluster_name', 'cluster01'),
            'cluster_ip': node['nutanix_config']['cluster_ip'],
            'cluster_dns': node['nutanix_config']['cluster_dns'],
            'created_by_node': node_id,
            'node_count': 1,
            'status': 'active'
        }
        
        cluster_id = self.db.register_cluster(cluster_config)
        
        self.db.log_deployment_event(
            node_id,
            'cluster_registered',
            'success',
            f"New cluster {cluster_config['cluster_name']} registered with ID {cluster_id}"
        )
        
        logger.info(f"New cluster {cluster_config['cluster_name']} registered for node {node['node_name']}")

    def handle_node_addition_complete(self, node_id, completion_data):
        """Handle completion of node addition to existing cluster"""
        node = self.db.get_node(node_id)
        cluster_info = self.db.get_cluster_info()
        
        if cluster_info:
            # Increment cluster node count
            # Note: This would require adding the method to Database class
            # self.db.increment_cluster_node_count(cluster_info['id'])
            
            self.db.log_deployment_event(
                node_id,
                'node_added_to_cluster',
                'success',
                f"Node {node['node_name']} added to cluster {cluster_info['cluster_name']}"
            )
            
            logger.info(f"Node {node['node_name']} added to cluster {cluster_info['cluster_name']}")

    def handle_deployment_complete(self, node_id, completion_data):
        """Handle successful deployment completion"""
        node = self.db.get_node(node_id)
        
        # Final status update
        self.db.update_node_status(node_id, 'deployed')
        
        self.db.log_deployment_event(
            node_id,
            'deployment_complete',
            'success',
            f"Deployment completed successfully for {node['node_name']}"
        )
        
        # Send completion notification (this could trigger external systems)
        self.send_completion_notification(node_id)
        
        logger.info(f"Deployment completed successfully for {node['node_name']}")

    def send_completion_notification(self, node_id):
        """Send deployment completion notification"""
        node = self.db.get_node(node_id)
        cluster_info = self.db.get_cluster_info()
        
        notification_data = {
            'event': 'deployment_complete',
            'node_id': node_id,
            'node_name': node['node_name'],
            'cluster_name': cluster_info['cluster_name'] if cluster_info else 'unknown',
            'cluster_ip': cluster_info['cluster_ip'] if cluster_info else node['nutanix_config']['cluster_ip'],
            'prism_url': f"https://{cluster_info['cluster_ip'] if cluster_info else node['nutanix_config']['cluster_ip']}:9440",
            'completion_time': datetime.now().isoformat()
        }
        
        logger.info(f"Deployment notification: {notification_data}")
        # Here you could send to external monitoring systems, webhooks, etc.

    def get_overall_deployment_summary(self):
        """Get summary of all deployments"""
        try:
            # Get all nodes
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT
                            deployment_status,
                            COUNT(*) as count
                        FROM nodes
                        GROUP BY deployment_status
                    """)
                    status_counts = dict(cur.fetchall())
            
            # Get cluster info
            cluster_info = self.db.get_cluster_info()
            
            summary = {
                'total_nodes': sum(status_counts.values()),
                'status_breakdown': status_counts,
                'cluster_info': cluster_info,
                'last_updated': datetime.now().isoformat()
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get deployment summary: {str(e)}")
            return None