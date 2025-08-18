"""
Main Flask application for Nutanix PXE/Config Server
"""
from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_from_directory, jsonify
from web_routes import register_web_routes, add_database_viewer_routes, register_additional_routes
from flask_cors import CORS
import logging
import os
from datetime import datetime

from config import Config
from database import Database
from node_provisioner import NodeProvisioner
from boot_service import BootService
from status_monitor import StatusMonitor
from ibm_cloud_client import IBMCloudClient
from cluster_manager import ClusterManager

# Configure logging
class ProxyAwareLogHandler(logging.Handler):
    def __init__(self, handler):
        super().__init__()
        self.handler = handler
    
    def emit(self, record):
        # Try to get the real IP from Flask's request context
        try:
            from flask import has_request_context, request
            if has_request_context() and request:
                # Get the real IP from X-Forwarded-For header if available
                forwarded_for = request.headers.get('X-Forwarded-For')
                if forwarded_for:
                    # Get the first IP in the chain (client IP)
                    real_ip = forwarded_for.split(',')[0].strip()
                    record.real_ip = real_ip
                else:
                    # Fallback to remote address
                    record.real_ip = request.remote_addr
            else:
                record.real_ip = 'unknown'
        except:
            record.real_ip = 'unknown'
        
        self.handler.emit(record)

# Custom formatter that includes real IP
class ProxyAwareFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, 'real_ip'):
            record.real_ip = 'unknown'
        return super().format(record)

# Add logging for server startup

# Add logging for server startup

# Add logging for server startup
if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = ProxyAwareFormatter('%(asctime)s - %(real_ip)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info("Server is starting up")
    app = Flask(__name__)
    CORS(app)
    config = Config()
    db = Database()
    node_provisioner = NodeProvisioner(db, config)
    boot_service = BootService(db, config)
    status_monitor = StatusMonitor()
    ibm_cloud_client = IBMCloudClient(config)
    cluster_manager = ClusterManager(db, config, node_provisioner, boot_service, status_monitor, ibm_cloud_client)
    register_web_routes(app, db, node_provisioner, status_monitor)
    add_database_viewer_routes(app, db)
    app.run(host=config.server_host, port=config.server_port, debug=config.debug_mode)

# Set up logging with custom formatter
formatter = ProxyAwareFormatter('%(asctime)s - %(name)s - %(levelname)s - %(real_ip)s - %(message)s')

# Create file handler
file_handler = logging.FileHandler(f'{Config.LOG_PATH}/pxe-server.log')
file_handler.setFormatter(formatter)

# Create stream handler
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

# Wrap handlers with proxy-aware handler
proxy_file_handler = ProxyAwareLogHandler(file_handler)
proxy_stream_handler = ProxyAwareLogHandler(stream_handler)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(proxy_file_handler)
root_logger.addHandler(proxy_stream_handler)

logger = logging.getLogger(__name__)

# Initialize Flask app GLOBALLY
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config.from_object(Config)

# Configure Flask to trust proxy headers
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

CORS(app)

# Add secret key for sessions and flash messages
app.secret_key = Config.SECRET_KEY

# Initialize services
db = Database()
node_provisioner = NodeProvisioner()
boot_service = BootService()
status_monitor = StatusMonitor()
ibm_cloud = IBMCloudClient()
cluster_manager = ClusterManager()

# Register web UI routes
register_web_routes(app, db, node_provisioner, status_monitor)
add_database_viewer_routes(app, db)
register_additional_routes(app, db, node_provisioner, status_monitor)

# ============================================================================
# BOOT SERVER ENDPOINTS
# ============================================================================

@app.route('/boot/config', methods=['GET'])
def api_handle_boot_config():
    """Handle iPXE boot configuration requests"""
    try:
        boot_script = boot_service.handle_ipxe_boot(request.args)
        return Response(boot_script, mimetype='text/plain')
    except Exception as e:
        logger.error(f"Boot config error: {str(e)}")
        error_script = boot_service.generate_error_boot_script(str(e))
        return Response(error_script, mimetype='text/plain'), 500

@app.route('/boot/server/<server_ip>', methods=['GET'])
def api_get_server_config(server_ip):
    """Get detailed server configuration for Arizona"""
    # Get client IP for logging
    client_ip = request.remote_addr
    # Check for X-Forwarded-For header
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        client_ip = forwarded_for.split(',')[0].strip()
        
    logger.info(f"Client {client_ip} is requesting server configuration for {server_ip}")
    
    # Log request headers for debugging
    logger.debug(f"Request headers: {dict(request.headers)}")
    
    try:
        # First check if the server IP exists in the database
        from database import Database
        db = Database()
        node = db.get_node_by_management_ip(server_ip)
        
        if not node:
            logger.warning(f"No node found in database for IP: {server_ip}")
            return jsonify({'error': 'Server not found in database'}), 404
        
        logger.info(f"Found node in database: {node.get('node_name', 'unknown')}")
        
        # Now try to get the full configuration
        try:
            config = boot_service.get_server_config(server_ip)
            
            if config:
                # Log successful config retrieval with some details
                logger.info(f"Configuration for {server_ip} sent to {client_ip}")
                
                # Log node name if available
                node_name = config.get('node_name', 'unknown')
                logger.info(f"Node name: {node_name}")
                
                # Log DNS servers for debugging
                dns_servers = config.get('dns_servers', 'unknown')
                logger.info(f"DNS servers: {dns_servers}")
                
                return jsonify(config)
            else:
                logger.warning(f"No configuration generated for server {server_ip}")
                return jsonify({'error': 'Failed to generate server configuration'}), 500
        except Exception as e:
            logger.error(f"Error in boot_service.get_server_config: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({'error': f'Internal server error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Failed to serve configuration for {server_ip}: {str(e)}")
        # Log full traceback for debugging
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        # Return a valid response even if there's an error
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/boot/images/<filename>', methods=['GET'])
def api_serve_boot_image(filename):
    """Serve boot images (kernel, initrd, etc.)"""
    try:
        # Get client IP for logging
        client_ip = request.remote_addr
        # Check for X-Forwarded-For header
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            client_ip = forwarded_for.split(',')[0].strip()
            
        # Log the request with high visibility
        if filename == 'kernel':
            logger.info(f"Client {client_ip} is downloading kernel file")
        elif filename == 'initrd-vpc.img':
            logger.info(f"Client {client_ip} is downloading modified initrd file")
        else:
            logger.info(f"Client {client_ip} is downloading {filename}")
            
        # Log request headers for debugging
        logger.debug(f"Request headers: {dict(request.headers)}")
        
        # Security check - only allow approved files
        allowed_files = [
            'kernel',
            'initrd-vpc.img',
            'squashfs.img',
            'nutanix_installer_package.tar.gz',
            'AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso'
        ]
        
        if filename not in allowed_files:
            logger.warning(f"Client {client_ip} attempted to access unauthorized file: {filename}")
            return jsonify({'error': 'File not allowed'}), 403
        
        # Log successful file serving
        logger.info(f"Serving {filename} to client {client_ip}")
        
        # Serve the file
        response = send_from_directory(Config.BOOT_IMAGES_PATH, filename)
        
        # Log file size for debugging
        file_size = response.headers.get('Content-Length', 'unknown size')
        logger.info(f"Sent {filename} ({file_size} bytes) to {client_ip}")
        
        return response
    except Exception as e:
        logger.error(f"Failed to serve {filename}: {str(e)}")
        # Log full traceback for debugging
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 404

@app.route('/boot/scripts/<script_name>', methods=['GET'])
def api_serve_boot_script(script_name):
    """Serve boot scripts and configuration files"""
    try:
        # Get client IP for logging
        client_ip = request.remote_addr
        # Check for X-Forwarded-For header
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            client_ip = forwarded_for.split(',')[0].strip()
            
        logger.info(f"Client {client_ip} is requesting boot script: {script_name}")
        
        allowed_scripts = [
            'foundation-init.sh',
            'network-config.sh',
            'post-install.sh'
        ]
        
        if script_name not in allowed_scripts:
            logger.warning(f"Client {client_ip} attempted to access unauthorized script: {script_name}")
            return jsonify({'error': 'Script not allowed'}), 403
        
        # Log successful script serving
        logger.info(f"Serving script {script_name} to client {client_ip}")
        
        # Serve the script
        response = send_from_directory(Config.BOOT_SCRIPTS_PATH, script_name)
        
        # Log file size for debugging
        file_size = response.headers.get('Content-Length', 'unknown size')
        logger.info(f"Sent script {script_name} ({file_size} bytes) to {client_ip}")
        
        return response
    except Exception as e:
        logger.error(f"Failed to serve script {script_name}: {str(e)}")
        # Log full traceback for debugging
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 404

# ============================================================================
# CONFIGURATION API ENDPOINTS
# ============================================================================

@app.route('/api/reinitialize', methods=['POST'])
def api_reinitialize_node():
    """Reinitialize a bare metal server with iPXE boot configuration"""
    try:
        # Log incoming request
        logger.info(f"API Request received: {request.method} {request.url}")
        logger.info(f"Request headers: {dict(request.headers)}")
        
        # Get parameters from query string or JSON body
        data = request.get_json() or {}
        node_id = request.args.get('node_id') or data.get('node_id')
        mgmt_ip = request.args.get('mgmt_ip') or data.get('mgmt_ip')
        
        # Validate that at least one parameter is provided
        if not node_id and not mgmt_ip:
            error_response = {'error': 'Either node_id or mgmt_ip must be provided'}
            logger.warning(f"Validation failed: {error_response}")
            return jsonify(error_response), 400
        
        # Get node details from database
        node = None
        if node_id:
            try:
                node_id = int(node_id)
                node = db.get_node(node_id)
                if not node:
                    error_response = {'error': f'Node with ID {node_id} not found'}
                    logger.warning(f"Validation failed: {error_response}")
                    return jsonify(error_response), 404
            except ValueError:
                error_response = {'error': f'Invalid node_id: {node_id}'}
                logger.warning(f"Validation failed: {error_response}")
                return jsonify(error_response), 400
        elif mgmt_ip:
            node = db.get_node_by_management_ip(mgmt_ip)
            if not node:
                error_response = {'error': f'Node with management IP {mgmt_ip} not found'}
                logger.warning(f"Validation failed: {error_response}")
                return jsonify(error_response), 404
        
        # Check if node has a bare metal ID
        if not node.get('bare_metal_id'):
            error_response = {'error': f'Node {node_id} does not have a bare metal server ID'}
            logger.warning(f"Validation failed: {error_response}")
            return jsonify(error_response), 400
        
        # Check if node has a management IP
        if not node.get('management_ip'):
            error_response = {'error': f'Node {node_id} does not have a management IP'}
            logger.warning(f"Validation failed: {error_response}")
            return jsonify(error_response), 400
        
        # Import the reinitialize_server function
        from reinitialize_server import reinitialize_server, stop_server, wait_for_server_state
        
        # Get server details
        server_id = node['bare_metal_id']
        management_ip = node['management_ip']
        
        # Stop the server
        logger.info(f"Stopping server {server_id}")
        if not stop_server(server_id):
            error_response = {'error': f'Failed to stop server {server_id}'}
            logger.error(f"Error: {error_response}")
            return jsonify(error_response), 500
        
        # Wait for server to reach stopped state
        logger.info(f"Waiting for server {server_id} to reach stopped state")
        if not wait_for_server_state(server_id, 'stopped', 30):
            error_response = {'error': f'Timeout waiting for server {server_id} to reach stopped state'}
            logger.error(f"Error: {error_response}")
            return jsonify(error_response), 500
        
        # Reinitialize the server
        logger.info(f"Reinitializing server {server_id} with management IP {management_ip}")
        if not reinitialize_server(server_id, management_ip):
            error_response = {'error': f'Failed to reinitialize server {server_id}'}
            logger.error(f"Error: {error_response}")
            return jsonify(error_response), 500
        
        # Log successful response
        response_data = {
            'message': f'Server {node["node_name"]} reinitialization initiated successfully',
            'node_id': node_id,
            'server_id': server_id,
            'management_ip': management_ip
        }
        logger.info(f"API Response (202): {response_data}")
        
        # Update node status in database
        db.update_node_status(node_id, 'reinitializing')
        
        # Log deployment event
        db.log_deployment_event(
            node_id,
            'reinitialize',
            'in_progress',
            f'Server reinitialization initiated for {node["node_name"]}'
        )
        
        return jsonify(response_data), 202
    except Exception as e:
        logger.error(f"Failed to reinitialize node {node_id}: {str(e)}")
        # Log full traceback for debugging
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/nodes', methods=['POST'])
def api_provision_node():
    """Provision a new Nutanix node"""
    try:
        data = request.get_json()
        
        # Log incoming request data
        logger.info(f"API Request received: {request.method} {request.url}")
        logger.info(f"Request headers: {dict(request.headers)}")
        logger.info(f"Request data: {data}")
        
        # Validate request
        if not data or 'node_config' not in data:
            error_response = {'error': 'Missing node_config'}
            logger.warning(f"Validation failed: {error_response}")
            return jsonify(error_response), 400
        
        required_fields = ['node_name', 'server_profile']
        node_config = data['node_config']
        
        for field in required_fields:
            if field not in node_config:
                error_response = {'error': f'Missing required field: {field}'}
                logger.warning(f"Validation failed: {error_response}")
                return jsonify(error_response), 400
        
        # Add cluster_config if it exists
        if 'cluster_config' in data:
            node_config['cluster_config'] = data['cluster_config']
        
        # Add network_config if it exists
        if 'network_config' in data:
            node_config['network_config'] = data['network_config']
        
        # Log processed configuration
        logger.info(f"Processed node configuration: {node_config}")
        
        # Start provisioning
        result = node_provisioner.provision_node(data)
        
        # Log successful response
        response_data = {
            'message': 'Node provisioning initiated successfully',
            'node_id': result['node_id'],
            'deployment_id': result['deployment_id'],
            'estimated_completion': result['estimated_completion'],
            'monitoring_endpoint': result['monitoring_endpoint']
        }
        logger.info(f"API Response (202): {response_data}")
        
        return jsonify(response_data), 202
        
    except Exception as e:
        error_response = {'error': str(e)}
        logger.error(f"Node provisioning error: {str(e)}")
        logger.error(f"Error response: {error_response}")
        return jsonify(error_response), 500

# ============================================================================
# CLUSTER MANAGEMENT API ENDPOINTS
# ============================================================================

@app.route('/api/config/clusters', methods=['POST'])
def api_create_cluster():
    """Create a new Nutanix cluster from deployed nodes"""
    try:
        data = request.get_json()
        
        # Validate request
        if not data or 'cluster_config' not in data:
            return jsonify({'error': 'Missing cluster_config'}), 400
        
        cluster_config = data['cluster_config']
        required_fields = ['nodes']
        
        for field in required_fields:
            if field not in cluster_config:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Create cluster
        result = cluster_manager.create_cluster(data)
        
        return jsonify({
            'message': 'Cluster creation initiated successfully',
            'cluster_id': result['cluster_id'],
            'cluster_name': result['cluster_name'],
            'cluster_ip': result['cluster_ip'],
            'status': result['status'],
            'message': result['message']
        }), 202
        
    except Exception as e:
        logger.error(f"Cluster creation error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/clusters/<int:cluster_id>', methods=['GET'])
def api_get_cluster_info(cluster_id):
    """Get cluster information"""
    try:
        cluster = cluster_manager.get_cluster(cluster_id)
        if not cluster:
            return jsonify({'error': 'Cluster not found'}), 404
        
        return jsonify(cluster)
        
    except Exception as e:
        logger.error(f"Get cluster error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/clusters', methods=['GET'])
def api_list_clusters():
    """List all clusters"""
    try:
        clusters = cluster_manager.list_clusters()
        return jsonify({'clusters': clusters})
    except Exception as e:
        logger.error(f"List clusters error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/clusters/<int:cluster_id>', methods=['DELETE'])
def api_delete_cluster(cluster_id):
    """Delete cluster information"""
    try:
        cluster_manager.delete_cluster(cluster_id)
        return jsonify({'message': f'Cluster {cluster_id} deleted successfully'})
    except Exception as e:
        logger.error(f"Delete cluster error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/nodes/<int:node_id>', methods=['GET'])
def api_get_node_info(node_id):
    """Get node information"""
    try:
        node = db.get_node(node_id)
        if not node:
            return jsonify({'error': 'Node not found'}), 404
        
        # Remove sensitive data
        safe_node = {
            'id': node['id'],
            'node_name': node['node_name'],
            'server_profile': node['server_profile'],
            'cluster_role': node['cluster_role'],
            'deployment_status': node['deployment_status'],
            'management_ip': str(node['management_ip']) if node.get('management_ip') else None,
            'workload_ip': str(node['workload_ip']) if node.get('workload_ip') else None,
            'created_at': node['created_at'].isoformat() if node.get('created_at') else None,
            'updated_at': node['updated_at'].isoformat() if node.get('updated_at') else None
        }
        
        return jsonify(safe_node)
        
    except Exception as e:
        logger.error(f"Get node error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/nodes', methods=['GET'])
def api_list_nodes():
    """List all nodes"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, node_name, server_profile, cluster_role,
                           deployment_status, management_ip, workload_ip, created_at, updated_at
                    FROM nodes 
                    ORDER BY created_at DESC
                """)
                
                nodes = []
                for row in cur.fetchall():
                    nodes.append({
                        'id': row[0],
                        'node_name': row[1],
                        'server_profile': row[2],
                        'cluster_role': row[3],
                        'deployment_status': row[4],
                        'management_ip': str(row[5]) if row[5] else None,
                        'workload_ip': str(row[6]) if row[6] else None,
                        'created_at': row[7].isoformat() if row[7] else None,
                        'updated_at': row[8].isoformat() if row[8] else None
                    })
                
                return jsonify({'nodes': nodes})
    except Exception as e:
        logger.error(f"List nodes error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# STATUS MONITORING ENDPOINTS
# ============================================================================

@app.route('/api/status/nodes/<int:node_id>', methods=['GET'])
def api_get_node_status(node_id):
    """Get deployment status for a specific node"""
    try:
        node = db.get_node(node_id)
        if not node:
            return jsonify({'error': 'Node not found'}), 404
        
        status = status_monitor.get_deployment_status(str(node['management_ip']))
        if status:
            return jsonify(status)
        else:
            return jsonify({'error': 'Status not available'}), 404
            
    except Exception as e:
        logger.error(f"Node status error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/deployment/<server_ip>', methods=['GET'])
def api_get_deployment_status(server_ip):
    """Get deployment status by server IP (legacy endpoint)"""
    try:
        status = status_monitor.get_deployment_status(server_ip)
        if status:
            return jsonify(status)
        else:
            return jsonify({'error': 'Server not found'}), 404
    except Exception as e:
        logger.error(f"Deployment status error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/phase', methods=['POST'])
def api_update_deployment_phase():
    """Receive phase updates from deploying servers"""
    try:
        data = request.get_json()
        result = status_monitor.update_deployment_phase(data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Phase update error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/history/<int:node_id>', methods=['GET'])
def api_get_deployment_history(node_id):
    """Get deployment history for a node"""
    try:
        node = db.get_node(node_id)
        if not node:
            return jsonify({'error': 'Node not found'}), 404
        
        history = status_monitor.get_deployment_history(str(node['management_ip']))
        if history:
            return jsonify(history)
        else:
            return jsonify({'error': 'History not available'}), 404
            
    except Exception as e:
        logger.error(f"Deployment history error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/summary', methods=['GET'])
def api_get_deployment_summary():
    """Get overall deployment summary"""
    try:
        summary = status_monitor.get_overall_deployment_summary()
        if summary:
            return jsonify(summary)
        else:
            return jsonify({'error': 'Summary not available'}), 500
    except Exception as e:
        logger.error(f"Deployment summary error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# New endpoint for overall deployment status
@app.route('/api/status', methods=['GET'])
@app.route('/api/installation/status', methods=['POST'])
def api_update_installation_status():
    """
    Receive status and log updates from the vpc_ce_installation.py script.
    Updates the server status in the database and logs the message.
    """
    try:
        data = request.get_json()
        logger.info(f"Received status update: {data}")

        if not data:
            return jsonify({'error': 'No JSON data received'}), 400

        # Accept either node_id (for backward compatibility) or management_ip (preferred)
        node_id = data.get('node_id')
        management_ip = data.get('management_ip', node_id)  # Default to node_id if management_ip not provided
        phase = data.get('phase')
        message = data.get('message')

        if (node_id is None and management_ip is None) or phase is None or message is None:
            return jsonify({'error': 'Missing required fields: either node_id or management_ip, plus phase and message'}), 400

        # Use management_ip for logging if available, otherwise use node_id
        identifier = management_ip if management_ip else node_id
        
        # Log the message to the server log file
        log_message = f"Node {identifier} - Phase {phase}: {message}"
        logger.info(log_message) # This will use the configured logger which writes to file and console

        # Update the server status in the database
        # Assuming 'nodes' table and updating 'deployment_status' and 'updated_at'
        status_map = {
            -1: 'LOG', # For log messages
            1: 'INITIALIZING',
            2: 'DOWNLOADING_CONFIG',
            3: 'VALIDATING_CONFIG',
            4: 'DOWNLOADING_PACKAGES',
            5: 'INSTALLING_HYPERVISOR',
            6: 'RUNNING_NUX_INSTALL',
            7: 'REBOOTING'
        }
        deployment_status = status_map.get(phase, 'UNKNOWN')
        
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    # Determine how to look up the node
                    if management_ip:
                        # If management_ip is provided, use it directly
                        update_query = """
                            UPDATE nodes
                            SET deployment_status = %s, updated_at = %s
                            WHERE management_ip = %s
                        """
                        lookup_value = management_ip
                    else:
                        # Otherwise try node_id
                        try:
                            # Try to convert to integer - if it works, use it as ID
                            node_db_id = int(node_id)
                            # Use direct ID lookup
                            update_query = """
                                UPDATE nodes
                                SET deployment_status = %s, updated_at = %s
                                WHERE id = %s
                            """
                            lookup_value = node_db_id
                        except ValueError:
                            # If conversion fails, it's likely an IP address or hostname
                            # Look up the node by management_ip
                            update_query = """
                                UPDATE nodes
                                SET deployment_status = %s, updated_at = %s
                                WHERE management_ip = %s
                            """
                            lookup_value = node_id
                    
                    current_time = datetime.utcnow()
                    cur.execute(update_query, (deployment_status, current_time, lookup_value))
                    conn.commit()
                    
                    # Use the identifier for logging
                    logger.info(f"Database updated for node {identifier}: status set to {deployment_status}")

        except Exception as db_e:
            logger.error(f"Database update failed for node {node_id}: {str(db_e)}")
            return jsonify({'error': f'Database update failed: {str(db_e)}'}), 500

        return jsonify({'message': 'Status update received successfully'}), 200

    except Exception as e:
        logger.error(f"Error processing status update: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# END OF NEWLY ADDED ROUTE
# ============================================================================

def api_get_overall_status():
    """Get overall deployment status"""
    try:
        status_monitor = StatusMonitor()
        summary = status_monitor.get_overall_deployment_summary()
        if summary:
            return jsonify(summary)
        else:
            return jsonify({'error': 'Status summary not available'}), 404
    except Exception as e:
        logger.error(f"Overall status error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# New endpoint for deployment history
@app.route('/api/status/history', methods=['GET'])
def api_get_deployment_history_by_server_ip():
    """Get deployment history"""
    try:
        server_ip = request.args.get('server_ip')
        if not server_ip:
            return jsonify({'error': 'server_ip parameter is required'}), 400
        
        status_monitor = StatusMonitor()
        history = status_monitor.get_deployment_history(server_ip)
        if history:
            return jsonify(history)
        else:
            return jsonify({'error': 'History not available for server IP'}), 404
    except Exception as e:
        logger.error(f"Deployment history error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# DNS REGISTRATION ENDPOINTS
# ============================================================================

@app.route('/api/dns/records', methods=['POST'])
def api_create_dns_record():
    """Create a DNS record"""
    try:
        data = request.get_json()
        required_fields = ['record_type', 'name', 'rdata']
        
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing field: {field}'}), 400
        
        # Use the IBMCloudClient to create DNS records
        record = ibm_cloud.create_dns_record(
            record_type=data['record_type'],
            name=data['name'],
            rdata=data['rdata'],
            ttl=data.get('ttl', 300)
        )
        
        logger.info(f"DNS record created: {data['name']} -> {data['rdata']}")
        return jsonify({
            'message': 'DNS record created successfully',
            'record': record
        }), 201
        
    except Exception as e:
        logger.error(f"DNS record creation error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dns/records/<record_name>', methods=['DELETE'])
def api_delete_dns_record(record_name):
    """Delete a DNS record"""
    try:
        # First, find the record by name
        dns_records = ibm_cloud.get_dns_records()
        target_record = None
        
        for record in dns_records:
            if record.get('name') == record_name:
                target_record = record
                break
        
        if not target_record:
            return jsonify({'error': f'DNS record {record_name} not found'}), 404
        
        # Delete the record using its ID
        ibm_cloud.delete_dns_record(target_record['id'])
        
        logger.info(f"DNS record deleted: {record_name}")
        return jsonify({'message': f'DNS record {record_name} deleted successfully'})
        
    except Exception as e:
        logger.error(f"DNS record deletion error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dns/records', methods=['GET'])
def api_list_dns_records():
    """List all DNS records"""
    try:
        records = ibm_cloud.get_dns_records()
        return jsonify({
            'records': records,
            'count': len(records)
        })
    except Exception as e:
        logger.error(f"DNS records list error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dns/records/<record_name>', methods=['GET'])
def api_get_dns_record(record_name):
    """Get a specific DNS record"""
    try:
        dns_records = ibm_cloud.get_dns_records()
        
        for record in dns_records:
            if record.get('name') == record_name:
                return jsonify(record)
        
        return jsonify({'error': f'DNS record {record_name} not found'}), 404
        
    except Exception as e:
        logger.error(f"DNS record get error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# CLEANUP MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/cleanup/node/<int:node_id>', methods=['POST'])
def api_cleanup_node(node_id):
    """Clean up resources for a specific node"""
    try:
        node = db.get_node(node_id)
        if not node:
            return jsonify({'error': 'Node not found'}), 404
        
        # Import cleanup service
        from cleanup_service import CleanupService
        cleanup_service = CleanupService()
        
        # Perform comprehensive cleanup
        cleanup_result = cleanup_service.cleanup_failed_provisioning(node['node_name'])
        
        if cleanup_result.get('success'):
            return jsonify({
                'message': f'Cleanup completed successfully for node {node_id}',
                'node_name': node['node_name'],
                'summary': {
                    'total_operations': cleanup_result.get('total_operations', 0),
                    'successful_operations': cleanup_result.get('successful_operations', 0),
                    'success_rate': cleanup_result.get('success_rate', '0%')
                },
                'details': cleanup_result.get('results', []),
                'timestamp': cleanup_result.get('timestamp')
            })
        else:
            return jsonify({
                'message': f'Cleanup completed with errors for node {node_id}',
                'node_name': node['node_name'],
                'error': cleanup_result.get('error'),
                'partial_results': cleanup_result.get('results', []),
                'timestamp': cleanup_result.get('timestamp')
            }), 207  # Multi-Status
        
    except Exception as e:
        logger.error(f"Node cleanup error: {str(e)}")
        return jsonify({
            'error': str(e),
            'node_id': node_id,
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/cleanup/deployment/<deployment_id>', methods=['POST'])
def api_cleanup_deployment(deployment_id):
    """Clean up all resources for a deployment"""
    try:
        # Import cleanup service
        from cleanup_service import CleanupService
        cleanup_service = CleanupService()
        
        # Perform deployment cleanup
        cleanup_result = cleanup_service.cleanup_deployment(deployment_id)
        
        if cleanup_result.get('success'):
            return jsonify({
                'message': f'Deployment cleanup completed successfully for {deployment_id}',
                'deployment_id': deployment_id,
                'nodes_cleaned': cleanup_result.get('nodes_cleaned', 0),
                'results': cleanup_result.get('results', []),
                'timestamp': cleanup_result.get('timestamp')
            })
        else:
            return jsonify({
                'message': f'Deployment cleanup completed with errors for {deployment_id}',
                'deployment_id': deployment_id,
                'error': cleanup_result.get('error'),
                'partial_results': cleanup_result.get('results', []),
                'timestamp': cleanup_result.get('timestamp')
            }), 207  # Multi-Status
            
    except Exception as e:
        logger.error(f"Deployment cleanup error: {str(e)}")
        return jsonify({
            'error': str(e),
            'deployment_id': deployment_id,
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/cleanup/script/<deployment_id>', methods=['GET'])
def api_generate_cleanup_script(deployment_id):
    """Generate cleanup script for manual execution"""
    try:
        # Import cleanup service
        from cleanup_service import CleanupService
        cleanup_service = CleanupService()
        
        # Generate cleanup script
        script_content = cleanup_service.generate_cleanup_script(deployment_id)
        
        return Response(
            script_content,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename=cleanup-{deployment_id}.sh'
            }
        )
        
    except Exception as e:
        logger.error(f"Cleanup script generation error: {str(e)}")
        
        # Generate error script
        error_script = f"""#!/bin/bash
# Cleanup script generation failed for deployment {deployment_id}
# Generated on {datetime.now().isoformat()}

echo "Error generating cleanup script: {str(e)}"
echo "Manual cleanup required for deployment {deployment_id}"
echo ""
echo "Please check the following resources in IBM Cloud console:"
echo "1. Bare metal servers"
echo "2. Virtual network interfaces"  
echo "3. DNS records"
echo "4. IP reservations"
echo ""
echo "Use IBM Cloud CLI commands to clean up resources manually"
"""
        
        return Response(
            error_script,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename=cleanup-error-{deployment_id}.sh'
            }
        )

@app.route('/api/cleanup/status', methods=['GET'])
def api_cleanup_status():
    """Get overall cleanup status"""
    try:
        # Import cleanup service
        from cleanup_service import CleanupService
        cleanup_service = CleanupService()
        
        # Get optional query parameters
        node_name = request.args.get('node_name')
        deployment_id = request.args.get('deployment_id')
        
        # Get cleanup status
        status_result = cleanup_service.get_cleanup_status(
            node_name=node_name,
            deployment_id=deployment_id
        )
        
        return jsonify(status_result)
        
    except Exception as e:
        logger.error(f"Cleanup status error: {str(e)}")
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/cleanup/validate/<int:node_id>', methods=['GET'])
def api_validate_cleanup(node_id):
    """Validate cleanup completion for a node"""
    try:
        node = db.get_node(node_id)
        if not node:
            return jsonify({'error': 'Node not found'}), 404
        
        # Import cleanup service
        from cleanup_service import CleanupService
        cleanup_service = CleanupService()
        
        # Validate cleanup
        validation_result = cleanup_service.validate_cleanup_completion(node['node_name'])
        
        return jsonify(validation_result)
        
    except Exception as e:
        logger.error(f"Cleanup validation error: {str(e)}")
        return jsonify({
            'error': str(e),
            'node_id': node_id,
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/cleanup/orphaned', methods=['POST'])
def api_cleanup_orphaned():
    """Clean up orphaned resources from failed deployments"""
    try:
        # Get optional max_age parameter (default 24 hours)
        max_age_hours = int(request.json.get('max_age_hours', 24)) if request.json else 24
        
        # Import cleanup service
        from cleanup_service import CleanupService
        cleanup_service = CleanupService()
        
        # Clean up orphaned resources
        cleanup_result = cleanup_service.cleanup_orphaned_resources(max_age_hours)
        
        if cleanup_result.get('success'):
            return jsonify({
                'message': 'Orphaned resource cleanup completed successfully',
                'orphaned_nodes_cleaned': cleanup_result.get('orphaned_nodes_cleaned', 0),
                'max_age_hours': max_age_hours,
                'results': cleanup_result.get('results', []),
                'timestamp': cleanup_result.get('timestamp')
            })
        else:
            return jsonify({
                'message': 'Orphaned resource cleanup completed with errors',
                'error': cleanup_result.get('error'),
                'partial_results': cleanup_result.get('results', []),
                'timestamp': cleanup_result.get('timestamp')
            }), 207  # Multi-Status
            
    except Exception as e:
        logger.error(f"Orphaned cleanup error: {str(e)}")
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/cleanup/batch', methods=['POST'])
def api_batch_cleanup():
    """Perform batch cleanup operations"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        operation = data.get('operation')
        targets = data.get('targets', [])
        
        if not operation or not targets:
            return jsonify({'error': 'Missing operation or targets'}), 400
        
        # Import cleanup service
        from cleanup_service import CleanupService
        cleanup_service = CleanupService()
        
        batch_results = []
        
        if operation == 'cleanup_nodes':
            # Clean up multiple nodes
            for target in targets:
                if isinstance(target, dict) and 'node_name' in target:
                    node_name = target['node_name']
                elif isinstance(target, str):
                    node_name = target
                else:
                    batch_results.append({
                        'target': target,
                        'success': False,
                        'error': 'Invalid target format'
                    })
                    continue
                
                try:
                    result = cleanup_service.cleanup_failed_provisioning(node_name)
                    batch_results.append({
                        'node_name': node_name,
                        'success': result.get('success', False),
                        'result': result
                    })
                except Exception as e:
                    batch_results.append({
                        'node_name': node_name,
                        'success': False,
                        'error': str(e)
                    })
        
        elif operation == 'cleanup_deployments':
            # Clean up multiple deployments
            for deployment_id in targets:
                try:
                    result = cleanup_service.cleanup_deployment(deployment_id)
                    batch_results.append({
                        'deployment_id': deployment_id,
                        'success': result.get('success', False),
                        'result': result
                    })
                except Exception as e:
                    batch_results.append({
                        'deployment_id': deployment_id,
                        'success': False,
                        'error': str(e)
                    })
        
        elif operation == 'validate_cleanup':
            # Validate cleanup for multiple nodes
            for target in targets:
                if isinstance(target, dict) and 'node_name' in target:
                    node_name = target['node_name']
                elif isinstance(target, str):
                    node_name = target
                else:
                    batch_results.append({
                        'target': target,
                        'success': False,
                        'error': 'Invalid target format'
                    })
                    continue
                
                try:
                    result = cleanup_service.validate_cleanup_completion(node_name)
                    batch_results.append({
                        'node_name': node_name,
                        'cleanup_complete': result.get('cleanup_complete', False),
                        'result': result
                    })
                except Exception as e:
                    batch_results.append({
                        'node_name': node_name,
                        'cleanup_complete': False,
                        'error': str(e)
                    })
        
        else:
            return jsonify({'error': f'Unknown operation: {operation}'}), 400
        
        # Calculate success rate
        successful_operations = len([r for r in batch_results if r.get('success', r.get('cleanup_complete', False))])
        total_operations = len(batch_results)
        success_rate = (successful_operations / total_operations * 100) if total_operations > 0 else 0
        
        return jsonify({
            'message': f'Batch {operation} completed',
            'operation': operation,
            'total_operations': total_operations,
            'successful_operations': successful_operations,
            'success_rate': f"{success_rate:.1f}%",
            'results': batch_results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Batch cleanup error: {str(e)}")
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# ============================================================================
# HEALTH AND INFO ENDPOINTS
# ============================================================================

@app.route('/health', methods=['GET'])
def api_health_check():
    """Health check endpoint - doesn't require authentication"""
    try:
        # Check database connectivity
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0'
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/info', methods=['GET'])
def api_get_server_info():
    """Get PXE server information"""
    return jsonify({
        'server_name': 'Nutanix PXE/Config Server',
        'version': '1.0.0',
        'services': {
            'boot_server': f'https://{Config.PXE_SERVER_DNS}',
            'config_api': f'https://{Config.PXE_SERVER_DNS}',
            'status_monitor': f'https://{Config.PXE_SERVER_DNS}',
            'dns_service': f'https://{Config.PXE_SERVER_DNS}',
            'cleanup_service': f'https://{Config.PXE_SERVER_DNS}'
        },
        'endpoints': {
            'provision_node': 'POST /api/config/nodes',
            'node_status': 'GET /api/status/nodes/{id}',
            'boot_config': 'GET /boot/config',
            'server_config': 'GET /boot/server/{ip}',
            'health_check': 'GET /health'
        }
    })

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def api_not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def api_internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(400)
def api_bad_request(error):
    return jsonify({'error': 'Bad request'}), 400

# ============================================================================
# MAIN APPLICATION
# ============================================================================

if __name__ == '__main__':
    # Create required directories
    os.makedirs(Config.BOOT_IMAGES_PATH, exist_ok=True)
    os.makedirs(Config.BOOT_SCRIPTS_PATH, exist_ok=True)
    os.makedirs(Config.CONFIG_TEMPLATES_PATH, exist_ok=True)
    os.makedirs(Config.LOG_PATH, exist_ok=True)
    
    logger.info("Starting Nutanix PXE/Config Server")
    
    # Run
    app.run(
        host='0.0.0.0',
        port=8080,
        debug=Config.DEBUG
    )