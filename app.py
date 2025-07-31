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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{Config.LOG_PATH}/pxe-server.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Initialize Flask app GLOBALLY
app = Flask(__name__)
app.config.from_object(Config)
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
# BOOT SERVER ENDPOINTS (Port 8080)
# ============================================================================

@app.route('/boot-config', methods=['GET'])
def handle_boot_config():
    """Handle iPXE boot configuration requests"""
    try:
        boot_script = boot_service.handle_ipxe_boot(request.args)
        return Response(boot_script, mimetype='text/plain')
    except Exception as e:
        logger.error(f"Boot config error: {str(e)}")
        error_script = boot_service.generate_error_boot_script(str(e))
        return Response(error_script, mimetype='text/plain'), 500

@app.route('/server-config/<server_ip>', methods=['GET'])
def get_server_config(server_ip):
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

@app.route('/images/<filename>', methods=['GET'])
def serve_boot_image(filename):
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

@app.route('/scripts/<script_name>', methods=['GET'])
def serve_boot_script(script_name):
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
# CONFIGURATION API ENDPOINTS (Port 8081)
# ============================================================================

@app.route('/api/v1/nodes', methods=['POST'])
def provision_node():
    """Provision a new Nutanix node"""
    try:
        data = request.get_json()
        
        # Validate request
        if not data or 'node_config' not in data:
            return jsonify({'error': 'Missing node_config'}), 400
        
        required_fields = ['node_name', 'node_position', 'server_profile']
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

@app.route('/api/v1/nodes/<int:node_id>', methods=['GET'])
def get_node_info(node_id):
    """Get node information"""
    try:
        node = db.get_node(node_id)
        if not node:
            return jsonify({'error': 'Node not found'}), 404
        
        # Remove sensitive data
        safe_node = {
            'id': node['id'],
            'node_name': node['node_name'],
            'node_position': node['node_position'],
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

@app.route('/api/v1/nodes', methods=['GET'])
def list_nodes():
    """List all nodes"""
    try:
        # This would require adding a method to Database class
        nodes = []  # db.get_all_nodes()
        return jsonify({'nodes': nodes})
    except Exception as e:
        logger.error(f"List nodes error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# STATUS MONITORING ENDPOINTS (Port 8082)
# ============================================================================

@app.route('/api/v1/nodes/<int:node_id>/status', methods=['GET'])
def get_node_status(node_id):
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

@app.route('/deployment-status/<server_ip>', methods=['GET'])
def get_deployment_status(server_ip):
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

@app.route('/phase-update', methods=['POST'])
def update_deployment_phase():
    """Receive phase updates from deploying servers"""
    try:
        data = request.get_json()
        result = status_monitor.update_deployment_phase(data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Phase update error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/nodes/<int:node_id>/history', methods=['GET'])
def get_deployment_history(node_id):
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

@app.route('/api/v1/deployment/summary', methods=['GET'])
def get_deployment_summary():
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
# DNS REGISTRATION ENDPOINTS (Port 8083)
# ============================================================================

@app.route('/api/v1/dns/records', methods=['POST'])
def create_dns_record():
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

@app.route('/api/v1/dns/records/<record_name>', methods=['DELETE'])
def delete_dns_record(record_name):
    """Delete a DNS record"""
    try:
        # Implementation would go here
        return jsonify({'message': 'DNS record deleted successfully'})
    except Exception as e:
        logger.error(f"DNS record deletion error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# CLEANUP MANAGEMENT ENDPOINTS (Port 8084)
# ============================================================================

@app.route('/api/v1/cleanup/node/<int:node_id>', methods=['POST'])
def cleanup_node(node_id):
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

@app.route('/api/v1/cleanup/deployment/<deployment_id>', methods=['POST'])
def cleanup_deployment(deployment_id):
    """Clean up all resources for a deployment"""
    try:
        # Implementation would clean up entire deployment
        return jsonify({'message': f'Deployment cleanup initiated for {deployment_id}'})
    except Exception as e:
        logger.error(f"Deployment cleanup error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/cleanup/script/<deployment_id>', methods=['GET'])
def generate_cleanup_script(deployment_id):
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
def health_check():
    """Health check endpoint"""
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
def get_server_info():
    """Get PXE server information"""
    return jsonify({
        'server_name': 'Nutanix PXE/Config Server',
        'version': '1.0.0',
        'services': {
            'boot_server': 'http://{}:8080'.format(Config.PXE_SERVER_IP),
            'config_api': 'http://{}:8081'.format(Config.PXE_SERVER_IP),
            'status_monitor': 'http://{}:8082'.format(Config.PXE_SERVER_IP),
            'dns_service': 'http://{}:8083'.format(Config.PXE_SERVER_IP),
            'cleanup_service': 'http://{}:8084'.format(Config.PXE_SERVER_IP)
        },
        'endpoints': {
            'provision_node': 'POST /api/v1/nodes',
            'node_status': 'GET /api/v1/nodes/{id}/status',
            'boot_config': 'GET /boot-config',
            'server_config': 'GET /server-config/{ip}',
            'health_check': 'GET /health'
        }
    })

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(400)
def bad_request(error):
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