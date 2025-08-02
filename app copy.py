"""
Main Flask application for Nutanix PXE/Config Server
"""
from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_from_directory, jsonify
from web_routes import register_web_routes
from flask_cors import CORS
import logging
import os
from datetime import datetime

from config import Config
from database import Database
from node_provisioner import NodeProvisioner
from boot_service import BootService
from status_monitor import StatusMonitor

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
app.secret_key = os.environ.get('SECRET_KEY', 'nutanix-orchestrator-secret-key')

# Initialize services
db = Database()
node_provisioner = NodeProvisioner()
boot_service = BootService()
status_monitor = StatusMonitor()

# Register web UI routes
register_web_routes(app, db, node_provisioner, status_monitor)

# ============================================================================
# BOOT SERVER ENDPOINTS (Consolidated under /boot/)
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
    """Get detailed server configuration for Foundation"""
    try:
        config = boot_service.get_server_config(server_ip)
        if config:
            return jsonify(config)
        else:
            return jsonify({'error': 'Server not found'}), 404
    except Exception as e:
        logger.error(f"Server config error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/boot/images/<filename>', methods=['GET'])
def api_serve_boot_image(filename):
    """Serve boot images (kernel, initrd, etc.)"""
    try:
        # Security check - only allow approved files
        allowed_files = [
            'vmlinuz-foundation',
            'initrd-foundation.img',
            'nutanix-ce-installer.iso'
        ]
        
        if filename not in allowed_files:
            return jsonify({'error': 'File not allowed'}), 403
        
        return send_from_directory(Config.BOOT_IMAGES_PATH, filename)
    except Exception as e:
        logger.error(f"Image serve error: {str(e)}")
        return jsonify({'error': str(e)}), 404

@app.route('/boot/scripts/<script_name>', methods=['GET'])
def api_serve_boot_script(script_name):
    """Serve boot scripts and configuration files"""
    try:
        allowed_scripts = [
            'foundation-init.sh',
            'network-config.sh',
            'post-install.sh'
        ]
        
        if script_name not in allowed_scripts:
            return jsonify({'error': 'Script not allowed'}), 403
        
        return send_from_directory(Config.BOOT_SCRIPTS_PATH, script_name)
    except Exception as e:
        logger.error(f"Script serve error: {str(e)}")
        return jsonify({'error': str(e)}), 404

# ============================================================================
# CONFIGURATION API ENDPOINTS (Consolidated under /api/config/)
# ============================================================================

@app.route('/api/config/nodes', methods=['POST'])
def api_provision_node():
    """Provision a new Nutanix node"""
    try:
        data = request.get_json()
        
        # Validate request
        if not data or 'node_config' not in data:
            return jsonify({'error': 'Missing node_config'}), 400
        
        required_fields = ['node_name', 'server_profile']
        node_config = data['node_config']
        
        for field in required_fields:
            if field not in node_config:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Start provisioning
        result = node_provisioner.provision_node(data)
        
        return jsonify({
            'message': 'Node provisioning initiated successfully',
            'node_id': result['node_id'],
            'deployment_id': result['deployment_id'],
            'estimated_completion': result['estimated_completion'],
            'monitoring_endpoint': result['monitoring_endpoint']
        }), 202
        
    except Exception as e:
        logger.error(f"Node provisioning error: {str(e)}")
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
            'management_ip': str(node['management_ip']),
            'workload_ip': str(node['workload_ip']),
            'created_at': node['created_at'].isoformat(),
            'updated_at': node['updated_at'].isoformat()
        }
        
        return jsonify(safe_node)
        
    except Exception as e:
        logger.error(f"Get node error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/nodes', methods=['GET'])
def api_list_nodes():
    """List all nodes"""
    try:
        # This would require adding a method to Database class
        nodes = []  # db.get_all_nodes()
        return jsonify({'nodes': nodes})
    except Exception as e:
        logger.error(f"List nodes error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# STATUS MONITORING ENDPOINTS (Consolidated under /api/status/)
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

# ============================================================================
# DNS REGISTRATION ENDPOINTS (Consolidated under /api/dns/)
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
        
        # This would use the IBMCloudClient to create DNS records
        # record = ibm_cloud.create_dns_record(...)
        
        return jsonify({'message': 'DNS record created successfully'}), 201
        
    except Exception as e:
        logger.error(f"DNS record creation error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dns/records/<record_name>', methods=['DELETE'])
def api_delete_dns_record(record_name):
    """Delete a DNS record"""
    try:
        # Implementation would go here
        return jsonify({'message': 'DNS record deleted successfully'})
    except Exception as e:
        logger.error(f"DNS record deletion error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# CLEANUP MANAGEMENT ENDPOINTS (Consolidated under /api/cleanup/)
# ============================================================================

@app.route('/api/cleanup/node/<int:node_id>', methods=['POST'])
def api_cleanup_node(node_id):
    """Clean up resources for a specific node"""
    try:
        node = db.get_node(node_id)
        if not node:
            return jsonify({'error': 'Node not found'}), 404
        
        # Implementation would clean up:
        # - DNS records
        # - IP reservations
        # - vNICs
        # - Bare metal server
        
        return jsonify({'message': f'Cleanup initiated for node {node_id}'})
        
    except Exception as e:
        logger.error(f"Node cleanup error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cleanup/deployment/<deployment_id>', methods=['POST'])
def api_cleanup_deployment(deployment_id):
    """Clean up all resources for a deployment"""
    try:
        # Implementation would clean up entire deployment
        return jsonify({'message': f'Deployment cleanup initiated for {deployment_id}'})
    except Exception as e:
        logger.error(f"Deployment cleanup error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cleanup/script/<deployment_id>', methods=['GET'])
def api_generate_cleanup_script(deployment_id):
    """Generate cleanup script for manual execution"""
    try:
        # Implementation would generate shell script
        script_content = f"""#!/bin/bash
# Cleanup script for deployment {deployment_id}
# Generated on {datetime.now().isoformat()}

echo "Manual cleanup required for deployment {deployment_id}"
echo "This is a placeholder - full implementation needed"
"""
        
        return Response(
            script_content,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename=cleanup-{deployment_id}.sh'
            }
        )
    except Exception as e:
        logger.error(f"Cleanup script generation error: {str(e)}")
        return jsonify({'error': str(e)}), 500

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

@app.route('/api/v1/info', methods=['GET'])
def api_get_server_info():
    """Get PXE server information"""
    return jsonify({
        'server_name': 'Nutanix PXE/Config Server',
        'version': '1.0.0',
        'services': {
            'boot_server': 'https://{}'.format(Config.PXE_SERVER_DNS),
            'config_api': 'https://{}'.format(Config.PXE_SERVER_DNS),
            'status_monitor': 'https://{}'.format(Config.PXE_SERVER_DNS),
            'dns_service': 'https://{}'.format(Config.PXE_SERVER_DNS),
            'cleanup_service': 'https://{}'.format(Config.PXE_SERVER_DNS)
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
    logger.info(f"Boot server: http://{Config.PXE_SERVER_IP}:8080")
    logger.info(f"Config API: http://{Config.PXE_SERVER_IP}:8081")
    logger.info(f"Status Monitor: http://{Config.PXE_SERVER_IP}:8082")
    logger.info(f"DNS Service: http://{Config.PXE_SERVER_IP}:8083")
    logger.info(f"Cleanup Service: http://{Config.PXE_SERVER_IP}:8084")
    
    # Run in development mode - use gunicorn for production
    app.run(
        host='0.0.0.0',
        port=8080,
        debug=Config.DEBUG
    )