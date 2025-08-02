"""
Cleanup service for Nutanix PXE/Config Server
Handles cleanup of IBM Cloud VPC resources for failed or completed deployments
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from database import Database
from ibm_cloud_client import IBMCloudClient
from config import Config

logger = logging.getLogger(__name__)

class CleanupService:
    def __init__(self):
        self.db = Database()
        self.ibm_cloud = IBMCloudClient()
        self.config = Config()
        
        # Track cleanup operations for rollback if needed
        self.cleanup_operations = []
        
        logger.info("CleanupService initialized")
    
    def cleanup_failed_provisioning(self, node_name: str) -> Dict:
        """
        Clean up resources for a failed provisioning
        This is the main entry point for cleanup operations
        """
        logger.warning(f"Starting cleanup for failed provisioning: {node_name}")
        
        try:
            # Get node information
            node = self.get_node_by_name(node_name)
            if not node:
                logger.error(f"Node {node_name} not found for cleanup")
                return {
                    'success': False,
                    'error': f'Node {node_name} not found',
                    'operations': []
                }
            
            # Reset cleanup operations list
            self.cleanup_operations = []
            
            # Perform cleanup in reverse order of creation
            cleanup_results = []
            
            # 1. Delete bare metal server (this will also clean up attached VNIs)
            if node.get('bare_metal_id'):
                result = self.cleanup_bare_metal_server(node)
                cleanup_results.append(result)
            
            # 2. Delete standalone VNIs (if any exist without server)
            vni_result = self.cleanup_virtual_network_interfaces(node_name)
            if vni_result['operations']:
                cleanup_results.append(vni_result)
            
            # 3. Delete DNS records
            dns_result = self.cleanup_dns_records(node_name)
            if dns_result['operations']:
                cleanup_results.append(dns_result)
            
            # 4. Delete IP reservations
            ip_result = self.cleanup_ip_reservations(node_name)
            if ip_result['operations']:
                cleanup_results.append(ip_result)
            
            # 5. Update database status
            db_result = self.cleanup_database_records(node['id'], node_name)
            cleanup_results.append(db_result)
            
            # Calculate overall success
            total_operations = sum(len(result.get('operations', [])) for result in cleanup_results)
            successful_operations = sum(
                len([op for op in result.get('operations', []) if op.get('success', False)])
                for result in cleanup_results
            )
            
            success_rate = (successful_operations / total_operations * 100) if total_operations > 0 else 100
            
            # Log summary
            logger.info(f"Cleanup completed for {node_name}: {successful_operations}/{total_operations} operations successful ({success_rate:.1f}%)")
            
            return {
                'success': success_rate > 80,  # Consider successful if >80% operations succeeded
                'node_name': node_name,
                'total_operations': total_operations,
                'successful_operations': successful_operations,
                'success_rate': f"{success_rate:.1f}%",
                'results': cleanup_results,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error during cleanup for {node_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'node_name': node_name,
                'operations': self.cleanup_operations,
                'timestamp': datetime.now().isoformat()
            }
    
    def cleanup_deployment(self, deployment_id: str) -> Dict:
        """
        Clean up all resources for an entire deployment
        """
        logger.info(f"Starting deployment cleanup for: {deployment_id}")
        
        try:
            # Find all nodes in this deployment
            nodes = self.get_nodes_by_deployment_id(deployment_id)
            
            if not nodes:
                logger.warning(f"No nodes found for deployment {deployment_id}")
                return {
                    'success': False,
                    'error': f'No nodes found for deployment {deployment_id}',
                    'operations': []
                }
            
            deployment_results = []
            total_success = True
            
            # Clean up each node in the deployment
            for node in nodes:
                node_result = self.cleanup_failed_provisioning(node['node_name'])
                deployment_results.append({
                    'node_name': node['node_name'],
                    'node_id': node['id'],
                    'result': node_result
                })
                
                if not node_result.get('success', False):
                    total_success = False
            
            # Clean up cluster-level resources if this was a cluster deployment
            cluster_result = self.cleanup_cluster_resources(deployment_id)
            if cluster_result['operations']:
                deployment_results.append({
                    'resource_type': 'cluster',
                    'result': cluster_result
                })
            
            return {
                'success': total_success,
                'deployment_id': deployment_id,
                'nodes_cleaned': len(nodes),
                'results': deployment_results,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error during deployment cleanup for {deployment_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'deployment_id': deployment_id,
                'timestamp': datetime.now().isoformat()
            }
    
    def cleanup_bare_metal_server(self, node: Dict) -> Dict:
        """Clean up bare metal server and associated resources"""
        operations = []
        
        try:
            bare_metal_id = node['bare_metal_id']
            
            # Get server details first to understand attached resources
            try:
                server_details = self.ibm_cloud.get_bare_metal_server(bare_metal_id)
                
                # Log attached VNIs for reference
                if 'network_attachments' in server_details:
                    vni_ids = []
                    for attachment in server_details['network_attachments']:
                        if 'virtual_network_interface' in attachment:
                            vni_ids.append(attachment['virtual_network_interface']['id'])
                    
                    if vni_ids:
                        logger.info(f"Server {bare_metal_id} has attached VNIs: {vni_ids}")
                
                operations.append({
                    'type': 'server_details_retrieved',
                    'resource_id': bare_metal_id,
                    'success': True,
                    'message': f'Retrieved server details for {bare_metal_id}'
                })
                
            except Exception as e:
                operations.append({
                    'type': 'server_details_retrieval',
                    'resource_id': bare_metal_id,
                    'success': False,
                    'error': str(e),
                    'message': f'Could not retrieve server details: {str(e)}'
                })
            
            # Delete the bare metal server
            # Note: This should automatically clean up attached VNIs
            try:
                self.ibm_cloud.delete_bare_metal_server(bare_metal_id)
                
                operations.append({
                    'type': 'bare_metal_server_deletion',
                    'resource_id': bare_metal_id,
                    'success': True,
                    'message': f'Deleted bare metal server {bare_metal_id}'
                })
                
                logger.info(f"Successfully deleted bare metal server {bare_metal_id}")
                
            except Exception as e:
                operations.append({
                    'type': 'bare_metal_server_deletion',
                    'resource_id': bare_metal_id,
                    'success': False,
                    'error': str(e),
                    'message': f'Failed to delete server: {str(e)}'
                })
                
                logger.error(f"Failed to delete bare metal server {bare_metal_id}: {str(e)}")
        
        except Exception as e:
            operations.append({
                'type': 'bare_metal_cleanup',
                'resource_id': node.get('bare_metal_id', 'unknown'),
                'success': False,
                'error': str(e),
                'message': f'Bare metal cleanup error: {str(e)}'
            })
        
        return {
            'resource_type': 'bare_metal_server',
            'operations': operations
        }
    
    def cleanup_virtual_network_interfaces(self, node_name: str) -> Dict:
        """Clean up Virtual Network Interfaces for a node"""
        operations = []
        
        try:
            # Get VNI information from database
            vni_info = self.get_vni_info_by_node(node_name)
            
            for vni in vni_info:
                try:
                    self.ibm_cloud.delete_virtual_network_interface(vni['vnic_id'])
                    
                    operations.append({
                        'type': 'vni_deletion',
                        'resource_id': vni['vnic_id'],
                        'resource_name': vni['vnic_name'],
                        'success': True,
                        'message': f'Deleted VNI {vni["vnic_name"]} ({vni["vnic_id"]})'
                    })
                    
                    logger.info(f"Deleted VNI {vni['vnic_name']} for node {node_name}")
                    
                except Exception as e:
                    operations.append({
                        'type': 'vni_deletion',
                        'resource_id': vni['vnic_id'],
                        'resource_name': vni['vnic_name'],
                        'success': False,
                        'error': str(e),
                        'message': f'Failed to delete VNI {vni["vnic_name"]}: {str(e)}'
                    })
                    
                    logger.error(f"Failed to delete VNI {vni['vnic_name']}: {str(e)}")
        
        except Exception as e:
            operations.append({
                'type': 'vni_cleanup',
                'resource_id': 'unknown',
                'success': False,
                'error': str(e),
                'message': f'VNI cleanup error: {str(e)}'
            })
        
        return {
            'resource_type': 'virtual_network_interfaces',
            'operations': operations
        }
    
    def cleanup_dns_records(self, node_name: str) -> Dict:
        """Clean up DNS records for a node"""
        operations = []
        
        try:
            # Get DNS records from database
            dns_records = self.get_dns_records_by_node(node_name)
            
            for record in dns_records:
                try:
                    self.ibm_cloud.delete_dns_record(record['record_id'])
                    
                    operations.append({
                        'type': 'dns_record_deletion',
                        'resource_id': record['record_id'],
                        'resource_name': record['record_name'],
                        'success': True,
                        'message': f'Deleted DNS record {record["record_name"]} ({record["record_type"]})'
                    })
                    
                    logger.info(f"Deleted DNS record {record['record_name']} for node {node_name}")
                    
                except Exception as e:
                    operations.append({
                        'type': 'dns_record_deletion',
                        'resource_id': record['record_id'],
                        'resource_name': record['record_name'],
                        'success': False,
                        'error': str(e),
                        'message': f'Failed to delete DNS record {record["record_name"]}: {str(e)}'
                    })
                    
                    logger.error(f"Failed to delete DNS record {record['record_name']}: {str(e)}")
        
        except Exception as e:
            operations.append({
                'type': 'dns_cleanup',
                'resource_id': 'unknown',
                'success': False,
                'error': str(e),
                'message': f'DNS cleanup error: {str(e)}'
            })
        
        return {
            'resource_type': 'dns_records',
            'operations': operations
        }
    
    def cleanup_ip_reservations(self, node_name: str) -> Dict:
        """Clean up IP reservations for a node"""
        operations = []
        
        try:
            # Get IP reservations from database
            ip_reservations = self.get_ip_reservations_by_node(node_name)
            
            for reservation in ip_reservations:
                try:
                    # Determine subnet ID based on IP type
                    if reservation['ip_type'] == 'workload':
                        subnet_id = self.config.WORKLOAD_SUBNET_ID
                    else:
                        subnet_id = self.config.MANAGEMENT_SUBNET_ID
                    
                    self.ibm_cloud.delete_subnet_reserved_ip(subnet_id, reservation['reservation_id'])
                    
                    operations.append({
                        'type': 'ip_reservation_deletion',
                        'resource_id': reservation['reservation_id'],
                        'resource_name': f"{reservation['ip_address']} ({reservation['ip_type']})",
                        'success': True,
                        'message': f'Deleted IP reservation {reservation["ip_address"]} ({reservation["ip_type"]})'
                    })
                    
                    logger.info(f"Deleted IP reservation {reservation['ip_address']} for node {node_name}")
                    
                except Exception as e:
                    operations.append({
                        'type': 'ip_reservation_deletion',
                        'resource_id': reservation['reservation_id'],
                        'resource_name': f"{reservation['ip_address']} ({reservation['ip_type']})",
                        'success': False,
                        'error': str(e),
                        'message': f'Failed to delete IP reservation {reservation["ip_address"]}: {str(e)}'
                    })
                    
                    logger.error(f"Failed to delete IP reservation {reservation['ip_address']}: {str(e)}")
        
        except Exception as e:
            operations.append({
                'type': 'ip_cleanup',
                'resource_id': 'unknown',
                'success': False,
                'error': str(e),
                'message': f'IP cleanup error: {str(e)}'
            })
        
        return {
            'resource_type': 'ip_reservations',
            'operations': operations
        }
    
    def cleanup_cluster_resources(self, deployment_id: str) -> Dict:
        """Clean up cluster-level resources"""
        operations = []
        
        try:
            # Find cluster DNS records that might need cleanup
            cluster_dns_records = self.get_cluster_dns_records(deployment_id)
            
            for record in cluster_dns_records:
                try:
                    self.ibm_cloud.delete_dns_record(record['record_id'])
                    
                    operations.append({
                        'type': 'cluster_dns_deletion',
                        'resource_id': record['record_id'],
                        'resource_name': record['record_name'],
                        'success': True,
                        'message': f'Deleted cluster DNS record {record["record_name"]}'
                    })
                    
                except Exception as e:
                    operations.append({
                        'type': 'cluster_dns_deletion',
                        'resource_id': record['record_id'],
                        'resource_name': record['record_name'],
                        'success': False,
                        'error': str(e),
                        'message': f'Failed to delete cluster DNS record: {str(e)}'
                    })
        
        except Exception as e:
            operations.append({
                'type': 'cluster_cleanup',
                'resource_id': 'unknown',
                'success': False,
                'error': str(e),
                'message': f'Cluster cleanup error: {str(e)}'
            })
        
        return {
            'resource_type': 'cluster_resources',
            'operations': operations
        }
    
    def cleanup_database_records(self, node_id: int, node_name: str) -> Dict:
        """Clean up database records for a node"""
        operations = []
        
        try:
            # Mark node as cleaned up
            self.db.update_node_status(node_id, 'cleanup_completed')
            
            operations.append({
                'type': 'node_status_update',
                'resource_id': str(node_id),
                'resource_name': node_name,
                'success': True,
                'message': f'Updated node status to cleanup_completed'
            })
            
            # Log cleanup completion
            self.db.log_deployment_event(
                node_id,
                'cleanup_completed',
                'success',
                f'Resource cleanup completed for {node_name}'
            )
            
            operations.append({
                'type': 'cleanup_event_logged',
                'resource_id': str(node_id),
                'resource_name': node_name,
                'success': True,
                'message': f'Logged cleanup completion event'
            })
            
        except Exception as e:
            operations.append({
                'type': 'database_cleanup',
                'resource_id': str(node_id),
                'resource_name': node_name,
                'success': False,
                'error': str(e),
                'message': f'Database cleanup error: {str(e)}'
            })
        
        return {
            'resource_type': 'database_records',
            'operations': operations
        }
    
    def generate_cleanup_script(self, deployment_id: str) -> str:
        """Generate manual cleanup script for a deployment"""
        try:
            # Get deployment information
            nodes = self.get_nodes_by_deployment_id(deployment_id)
            
            if not nodes:
                return self.generate_empty_cleanup_script(deployment_id)
            
            script_lines = [
                "#!/bin/bash",
                f"# Cleanup script for deployment {deployment_id}",
                f"# Generated on {datetime.now().isoformat()}",
                "",
                "set -e",
                "",
                "# Color codes for output",
                'RED="\\033[0;31m"',
                'GREEN="\\033[0;32m"',
                'YELLOW="\\033[1;33m"',
                'NC="\\033[0m" # No Color',
                "",
                "# Configuration",
                f'DEPLOYMENT_ID="{deployment_id}"',
                f'DNS_INSTANCE_ID="{self.config.DNS_INSTANCE_ID}"',
                f'DNS_ZONE_ID="{self.config.DNS_ZONE_ID}"',
                f'MANAGEMENT_SUBNET_ID="{self.config.MANAGEMENT_SUBNET_ID}"',
                f'WORKLOAD_SUBNET_ID="{self.config.WORKLOAD_SUBNET_ID}"',
                "",
                "log_success() {",
                '    echo -e "${GREEN}✓ SUCCESS${NC}: $1"',
                "}",
                "",
                "log_error() {",
                '    echo -e "${RED}✗ ERROR${NC}: $1"',
                "}",
                "",
                "log_warning() {",
                '    echo -e "${YELLOW}⚠ WARNING${NC}: $1"',
                "}",
                "",
                f'echo "Starting cleanup for deployment {deployment_id}"',
                f'echo "Nodes to clean up: {len(nodes)}"',
                "echo"
            ]
            
            # Add cleanup commands for each node
            for node in nodes:
                script_lines.extend(self.generate_node_cleanup_commands(node))
            
            # Add final verification
            script_lines.extend([
                "",
                "echo",
                f'echo "Cleanup completed for deployment {deployment_id}"',
                "echo",
                "echo \"Manual verification recommended:\"",
                "echo \"1. Check IBM Cloud console for remaining resources\"",
                "echo \"2. Verify DNS records have been removed\"",
                "echo \"3. Check for any orphaned IP reservations\"",
                "echo \"4. Review VPC for unused security groups\"",
                ""
            ])
            
            return "\n".join(script_lines)
            
        except Exception as e:
            logger.error(f"Error generating cleanup script: {str(e)}")
            return self.generate_error_cleanup_script(deployment_id, str(e))
    
    def generate_node_cleanup_commands(self, node: Dict) -> List[str]:
        """Generate cleanup commands for a specific node"""
        commands = [
            f"",
            f"echo \"Cleaning up node {node['node_name']}...\"",
            ""
        ]
        
        # Bare metal server cleanup
        if node.get('bare_metal_id'):
            commands.extend([
                f"# Delete bare metal server {node['bare_metal_id']}",
                f'if ibmcloud is bare-metal-server {node["bare_metal_id"]} >/dev/null 2>&1; then',
                f'    echo "Deleting bare metal server {node["bare_metal_id"]}..."',
                f'    if ibmcloud is bare-metal-server-delete {node["bare_metal_id"]} --force; then',
                f'        log_success "Deleted bare metal server {node["bare_metal_id"]}"',
                f'    else',
                f'        log_error "Failed to delete bare metal server {node["bare_metal_id"]}"',
                f'    fi',
                f'else',
                f'    log_warning "Bare metal server {node["bare_metal_id"]} not found"',
                f'fi',
                ""
            ])
        
        # DNS records cleanup
        commands.extend([
            f"# Delete DNS records for {node['node_name']}",
            f'echo "Cleaning up DNS records for {node["node_name"]}..."',
            f'DNS_RECORDS=$(ibmcloud dns resource-records --instance $DNS_INSTANCE_ID --zone $DNS_ZONE_ID --output json | jq -r \'.[] | select(.name | contains("{node["node_name"]}")) | .id\' 2>/dev/null || echo "")',
            f'if [ -n "$DNS_RECORDS" ]; then',
            f'    echo "$DNS_RECORDS" | while read record_id; do',
            f'        if [ -n "$record_id" ] && [ "$record_id" != "null" ]; then',
            f'            if ibmcloud dns resource-record-delete $DNS_INSTANCE_ID $DNS_ZONE_ID $record_id --force >/dev/null 2>&1; then',
            f'                log_success "Deleted DNS record $record_id"',
            f'            else',
            f'                log_error "Failed to delete DNS record $record_id"',
            f'            fi',
            f'        fi',
            f'    done',
            f'else',
            f'    log_warning "No DNS records found for {node["node_name"]}"',
            f'fi',
            ""
        ])
        
        # IP reservations cleanup
        if node.get('management_ip') or node.get('workload_ip'):
            commands.extend([
                f"# Delete IP reservations for {node['node_name']}",
                f'echo "Cleaning up IP reservations for {node["node_name"]}..."'
            ])
            
            if node.get('management_ip'):
                commands.extend([
                    f'# Management IP cleanup',
                    f'MGMT_RESERVATIONS=$(ibmcloud is subnet-reserved-ips $MANAGEMENT_SUBNET_ID --output json | jq -r \'.[] | select(.address == "{node["management_ip"]}") | .id\' 2>/dev/null || echo "")',
                    f'if [ -n "$MGMT_RESERVATIONS" ]; then',
                    f'    echo "$MGMT_RESERVATIONS" | while read reservation_id; do',
                    f'        if [ -n "$reservation_id" ] && [ "$reservation_id" != "null" ]; then',
                    f'            if ibmcloud is subnet-reserved-ip-delete $MANAGEMENT_SUBNET_ID $reservation_id --force >/dev/null 2>&1; then',
                    f'                log_success "Deleted management IP reservation $reservation_id"',
                    f'            else',
                    f'                log_error "Failed to delete management IP reservation $reservation_id"',
                    f'            fi',
                    f'        fi',
                    f'    done',
                    f'fi'
                ])
            
            if node.get('workload_ip'):
                commands.extend([
                    f'# Workload IP cleanup',
                    f'WORKLOAD_RESERVATIONS=$(ibmcloud is subnet-reserved-ips $WORKLOAD_SUBNET_ID --output json | jq -r \'.[] | select(.address == "{node["workload_ip"]}") | .id\' 2>/dev/null || echo "")',
                    f'if [ -n "$WORKLOAD_RESERVATIONS" ]; then',
                    f'    echo "$WORKLOAD_RESERVATIONS" | while read reservation_id; do',
                    f'        if [ -n "$reservation_id" ] && [ "$reservation_id" != "null" ]; then',
                    f'            if ibmcloud is subnet-reserved-ip-delete $WORKLOAD_SUBNET_ID $reservation_id --force >/dev/null 2>&1; then',
                    f'                log_success "Deleted workload IP reservation $reservation_id"',
                    f'            else',
                    f'                log_error "Failed to delete workload IP reservation $reservation_id"',
                    f'            fi',
                    f'        fi',
                    f'    done',
                    f'fi'
                ])
        
        commands.append("")
        return commands
    
    def generate_empty_cleanup_script(self, deployment_id: str) -> str:
        """Generate script when no nodes found"""
        return f"""#!/bin/bash
# Cleanup script for deployment {deployment_id}
# Generated on {datetime.now().isoformat()}

echo "No nodes found for deployment {deployment_id}"
echo "Nothing to clean up"
"""
    
    def generate_error_cleanup_script(self, deployment_id: str, error: str) -> str:
        """Generate script when error occurred"""
        return f"""#!/bin/bash
# Cleanup script for deployment {deployment_id}
# Generated on {datetime.now().isoformat()}

echo "Error generating cleanup script: {error}"
echo "Manual cleanup required for deployment {deployment_id}"
echo "Please check the following resources in IBM Cloud console:"
echo "1. Bare metal servers"
echo "2. Virtual network interfaces"
echo "3. DNS records"
echo "4. IP reservations"
"""
    
    # Database helper methods
    def get_node_by_name(self, node_name: str) -> Optional[Dict]:
        """Get node information by name"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, node_name, bare_metal_id, management_ip, workload_ip,
                               management_vnic_id, workload_vnic_id, deployment_status
                        FROM nodes WHERE node_name = %s
                    """, (node_name,))
                    
                    row = cur.fetchone()
                    if row:
                        return {
                            'id': row[0],
                            'node_name': row[1],
                            'bare_metal_id': row[2],
                            'management_ip': str(row[3]) if row[3] else None,
                            'workload_ip': str(row[4]) if row[4] else None,
                            'management_vnic_id': row[5],
                            'workload_vnic_id': row[6],
                            'deployment_status': row[7]
                        }
                    return None
        except Exception as e:
            logger.error(f"Error getting node by name {node_name}: {str(e)}")
            return None
    
    def get_nodes_by_deployment_id(self, deployment_id: str) -> List[Dict]:
        """Get all nodes in a deployment"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    # Try to find nodes by bare_metal_id first, then by node name pattern
                    cur.execute("""
                        SELECT id, node_name, bare_metal_id, management_ip, workload_ip,
                               management_vnic_id, workload_vnic_id, deployment_status
                        FROM nodes 
                        WHERE bare_metal_id = %s OR node_name LIKE %s
                        ORDER BY created_at
                    """, (deployment_id, f"%{deployment_id}%"))
                    
                    nodes = []
                    for row in cur.fetchall():
                        nodes.append({
                            'id': row[0],
                            'node_name': row[1],
                            'bare_metal_id': row[2],
                            'management_ip': str(row[3]) if row[3] else None,
                            'workload_ip': str(row[4]) if row[4] else None,
                            'management_vnic_id': row[5],
                            'workload_vnic_id': row[6],
                            'deployment_status': row[7]
                        })
                    
                    return nodes
        except Exception as e:
            logger.error(f"Error getting nodes by deployment ID {deployment_id}: {str(e)}")
            return []
    
    def get_vni_info_by_node(self, node_name: str) -> List[Dict]:
        """Get VNI information for a node"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT vnic_name, vnic_id, vnic_type
                        FROM vnic_info WHERE node_name = %s
                    """, (node_name,))
                    
                    return [
                        {
                            'vnic_name': row[0],
                            'vnic_id': row[1],
                            'vnic_type': row[2]
                        }
                        for row in cur.fetchall()
                    ]
        except Exception as e:
            logger.error(f"Error getting VNI info for node {node_name}: {str(e)}")
            return []
    
    def get_dns_records_by_node(self, node_name: str) -> List[Dict]:
        """Get DNS records for a node"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT record_name, record_type, rdata, record_id
                        FROM dns_records WHERE node_name = %s
                    """, (node_name,))
                    
                    return [
                        {
                            'record_name': row[0],
                            'record_type': row[1],
                            'rdata': row[2],
                            'record_id': row[3]
                        }
                        for row in cur.fetchall()
                    ]
        except Exception as e:
            logger.error(f"Error getting DNS records for node {node_name}: {str(e)}")
            return []
    
    def get_ip_reservations_by_node(self, node_name: str) -> List[Dict]:
        """Get IP reservations for a node"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT ip_address, ip_type, reservation_id, subnet_id
                        FROM ip_reservations WHERE node_name = %s
                    """, (node_name,))
                    
                    return [
                        {
                            'ip_address': str(row[0]),
                            'ip_type': row[1],
                            'reservation_id': row[2],
                            'subnet_id': row[3]
                        }
                        for row in cur.fetchall()
                    ]
        except Exception as e:
            logger.error(f"Error getting IP reservations for node {node_name}: {str(e)}")
            return []
    
    def get_cluster_dns_records(self, deployment_id: str) -> List[Dict]:
        """Get cluster-level DNS records for a deployment"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    # Look for cluster DNS records (like cluster01.domain.com)
                    cur.execute("""
                        SELECT DISTINCT record_name, record_type, rdata, record_id
                        FROM dns_records 
                        WHERE record_name LIKE 'cluster%' 
                        AND node_name IN (
                            SELECT node_name FROM nodes 
                            WHERE bare_metal_id = %s OR node_name LIKE %s
                        )
                    """, (deployment_id, f"%{deployment_id}%"))
                    
                    return [
                        {
                            'record_name': row[0],
                            'record_type': row[1],
                            'rdata': row[2],
                            'record_id': row[3]
                        }
                        for row in cur.fetchall()
                    ]
        except Exception as e:
            logger.error(f"Error getting cluster DNS records for deployment {deployment_id}: {str(e)}")
            return []
    
    def cleanup_orphaned_resources(self, max_age_hours: int = 24) -> Dict:
        """
        Clean up orphaned resources older than specified hours
        This is useful for cleaning up resources from failed deployments
        """
        logger.info(f"Starting orphaned resource cleanup (older than {max_age_hours} hours)")
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cleanup_results = []
        
        try:
            # Find nodes that have been in failed states for too long
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT node_name, id, bare_metal_id 
                        FROM nodes 
                        WHERE deployment_status IN ('failed', 'error', 'timeout')
                        AND updated_at < %s
                    """, (cutoff_time,))
                    
                    orphaned_nodes = cur.fetchall()
            
            for node_name, node_id, bare_metal_id in orphaned_nodes:
                logger.info(f"Cleaning up orphaned node: {node_name}")
                result = self.cleanup_failed_provisioning(node_name)
                cleanup_results.append({
                    'node_name': node_name,
                    'node_id': node_id,
                    'result': result
                })
            
            return {
                'success': True,
                'orphaned_nodes_cleaned': len(orphaned_nodes),
                'results': cleanup_results,
                'cutoff_time': cutoff_time.isoformat(),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error during orphaned resource cleanup: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'results': cleanup_results,
                'timestamp': datetime.now().isoformat()
            }
    
    def validate_cleanup_completion(self, node_name: str) -> Dict:
        """
        Validate that cleanup was completed successfully
        """
        logger.info(f"Validating cleanup completion for {node_name}")
        
        validation_results = []
        all_clean = True
        
        try:
            # Check if bare metal server still exists
            node = self.get_node_by_name(node_name)
            if node and node.get('bare_metal_id'):
                try:
                    server = self.ibm_cloud.get_bare_metal_server(node['bare_metal_id'])
                    if server:
                        validation_results.append({
                            'check': 'bare_metal_server',
                            'status': 'FAIL',
                            'message': f'Bare metal server {node["bare_metal_id"]} still exists'
                        })
                        all_clean = False
                    else:
                        validation_results.append({
                            'check': 'bare_metal_server',
                            'status': 'PASS',
                            'message': 'Bare metal server successfully deleted'
                        })
                except Exception:
                    # If we get an error, the server probably doesn't exist (good)
                    validation_results.append({
                        'check': 'bare_metal_server',
                        'status': 'PASS',
                        'message': 'Bare metal server not found (successfully deleted)'
                    })
            
            # Check DNS records
            try:
                all_dns_records = self.ibm_cloud.get_dns_records()
                node_dns_records = [r for r in all_dns_records if node_name in r.get('name', '')]
                
                if node_dns_records:
                    validation_results.append({
                        'check': 'dns_records',
                        'status': 'FAIL',
                        'message': f'Found {len(node_dns_records)} remaining DNS records'
                    })
                    all_clean = False
                else:
                    validation_results.append({
                        'check': 'dns_records',
                        'status': 'PASS',
                        'message': 'All DNS records successfully deleted'
                    })
            except Exception as e:
                validation_results.append({
                    'check': 'dns_records',
                    'status': 'ERROR',
                    'message': f'Could not validate DNS records: {str(e)}'
                })
            
            # Check IP reservations
            try:
                mgmt_ips = self.ibm_cloud.get_subnet_reserved_ips(self.config.MANAGEMENT_SUBNET_ID)
                workload_ips = self.ibm_cloud.get_subnet_reserved_ips(self.config.WORKLOAD_SUBNET_ID)
                
                # Get expected IPs for this node
                expected_ips = []
                if node and node.get('management_ip'):
                    expected_ips.append(node['management_ip'])
                if node and node.get('workload_ip'):
                    expected_ips.append(node['workload_ip'])
                
                remaining_ips = [ip for ip in expected_ips if ip in mgmt_ips or ip in workload_ips]
                
                if remaining_ips:
                    validation_results.append({
                        'check': 'ip_reservations',
                        'status': 'FAIL',
                        'message': f'Found remaining IP reservations: {remaining_ips}'
                    })
                    all_clean = False
                else:
                    validation_results.append({
                        'check': 'ip_reservations',
                        'status': 'PASS',
                        'message': 'All IP reservations successfully deleted'
                    })
            except Exception as e:
                validation_results.append({
                    'check': 'ip_reservations',
                    'status': 'ERROR',
                    'message': f'Could not validate IP reservations: {str(e)}'
                })
            
            return {
                'node_name': node_name,
                'cleanup_complete': all_clean,
                'validation_results': validation_results,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error validating cleanup for {node_name}: {str(e)}")
            return {
                'node_name': node_name,
                'cleanup_complete': False,
                'error': str(e),
                'validation_results': validation_results,
                'timestamp': datetime.now().isoformat()
            }
    
    def get_cleanup_status(self, node_name: str = None, deployment_id: str = None) -> Dict:
        """
        Get cleanup status for node(s) or deployment
        """
        try:
            if node_name:
                # Get status for specific node
                node = self.get_node_by_name(node_name)
                if not node:
                    return {
                        'error': f'Node {node_name} not found',
                        'timestamp': datetime.now().isoformat()
                    }
                
                return {
                    'node_name': node_name,
                    'current_status': node['deployment_status'],
                    'cleanup_needed': node['deployment_status'] in ['failed', 'error', 'timeout'],
                    'cleanup_completed': node['deployment_status'] == 'cleanup_completed',
                    'timestamp': datetime.now().isoformat()
                }
            
            elif deployment_id:
                # Get status for entire deployment
                nodes = self.get_nodes_by_deployment_id(deployment_id)
                if not nodes:
                    return {
                        'error': f'No nodes found for deployment {deployment_id}',
                        'timestamp': datetime.now().isoformat()
                    }
                
                node_statuses = []
                cleanup_needed_count = 0
                cleanup_completed_count = 0
                
                for node in nodes:
                    cleanup_needed = node['deployment_status'] in ['failed', 'error', 'timeout']
                    cleanup_completed = node['deployment_status'] == 'cleanup_completed'
                    
                    if cleanup_needed:
                        cleanup_needed_count += 1
                    if cleanup_completed:
                        cleanup_completed_count += 1
                    
                    node_statuses.append({
                        'node_name': node['node_name'],
                        'current_status': node['deployment_status'],
                        'cleanup_needed': cleanup_needed,
                        'cleanup_completed': cleanup_completed
                    })
                
                return {
                    'deployment_id': deployment_id,
                    'total_nodes': len(nodes),
                    'cleanup_needed_count': cleanup_needed_count,
                    'cleanup_completed_count': cleanup_completed_count,
                    'node_statuses': node_statuses,
                    'timestamp': datetime.now().isoformat()
                }
            
            else:
                # Get overall cleanup status
                with self.db.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT deployment_status, COUNT(*) 
                            FROM nodes 
                            GROUP BY deployment_status
                        """)
                        
                        status_counts = dict(cur.fetchall())
                
                return {
                    'overall_status': status_counts,
                    'cleanup_needed': status_counts.get('failed', 0) + status_counts.get('error', 0) + status_counts.get('timeout', 0),
                    'cleanup_completed': status_counts.get('cleanup_completed', 0),
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting cleanup status: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }