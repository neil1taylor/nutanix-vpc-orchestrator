# Application Code Changes Implementation Plan

## Overview
This plan outlines the necessary changes to the Nutanix VPC Orchestrator application code to support the new Nginx reverse proxy architecture with path-based routing and consolidated services.

## Implementation Phases

### Phase 1: Preparation and Analysis
1. **Codebase Assessment**
   - Review current Flask application structure
   - Analyze existing route definitions and URL patterns
   - Identify dependencies on specific ports or URLs
   - Document current API endpoints and their usage

2. **Impact Analysis**
   - Identify all files that need modification
   - Assess impact on existing clients and integrations
   - Review backward compatibility requirements
   - Document testing requirements

3. **Branching Strategy**
   - Create feature branch for changes
   - Set up continuous integration for testing
   - Prepare development environment

### Phase 2: Route Restructuring
1. **Path-Based Routing Implementation**
   - Update route decorators to use new path structure
   - Implement URL generation functions for new paths
   - Update internal links and redirects
   - Maintain backward compatibility during transition

2. **API Endpoint Organization**
   - Group related endpoints under common path prefixes
   - Implement consistent naming conventions
   - Add API versioning support
   - Update documentation

### Phase 3: Configuration Updates
1. **Environment Configuration**
   - Update configuration to support new URL structure
   - Add settings for path prefixes
   - Update SSL and security settings
   - Configure caching settings

2. **Service Integration**
   - Update service classes to use new paths
   - Modify internal API calls to use consolidated endpoints
   - Update webhook URLs and callback endpoints
   - Test service integrations

### Phase 4: Web Interface Updates
1. **Template Modifications**
   - Update template URLs to use new path structure
   - Modify form actions and link destinations
   - Update JavaScript AJAX calls
   - Test responsive design

2. **Frontend JavaScript Updates**
   - Update API endpoint URLs in JavaScript code
   - Modify WebSocket connection URLs
   - Update AJAX request paths
   - Test interactive features

### Phase 5: Testing and Validation
1. **Unit Testing**
   - Update existing unit tests for new routes
   - Add tests for backward compatibility
   - Test error handling and edge cases
   - Validate security features

2. **Integration Testing**
   - Test API endpoints with new path structure
   - Validate web interface functionality
   - Test service integrations
   - Verify SSL and security features

### Phase 6: Production Deployment
1. **Deployment Steps**
   - Schedule maintenance window
   - Deploy updated application code
   - Update configuration files
   - Restart application service
   - Monitor for issues

2. **Post-Deployment Validation**
   - Verify application functionality
   - Test all API endpoints
   - Validate web interface
   - Monitor performance metrics

## Detailed Code Changes

### 1. Route Restructuring
```python
# app.py - Updated route structure

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
```

### 2. Configuration Updates
```python
# config.py - Updated configuration

class Config:
    # ... existing configuration ...
    
    # API Path Configuration
    API_BASE_PATH = '/api'
    BOOT_BASE_PATH = '/boot'
    
    # Service Path Configuration
    CONFIG_API_PATH = '/api/config'
    STATUS_API_PATH = '/api/status'
    DNS_API_PATH = '/api/dns'
    CLEANUP_API_PATH = '/api/cleanup'
    BOOT_API_PATH = '/boot'
    
    # URL Generation Helper
    @classmethod
    def get_api_url(cls, service, endpoint):
        """Generate API URL for a specific service and endpoint"""
        service_paths = {
            'config': cls.CONFIG_API_PATH,
            'status': cls.STATUS_API_PATH,
            'dns': cls.DNS_API_PATH,
            'cleanup': cls.CLEANUP_API_PATH,
            'boot': cls.BOOT_API_PATH
        }
        
        if service in service_paths:
            return f"{service_paths[service]}{endpoint}"
        else:
            return endpoint
```

### 3. Web Interface Updates
```python
# web_routes.py - Updated web routes

def register_web_routes(app, db, node_provisioner, status_monitor):
    """Register web UI routes with updated paths"""
    
    @app.route('/')
    def dashboard():
        """Dashboard view"""
        # Implementation remains the same
        pass
    
    @app.route('/provision', methods=['GET'])
    def provision_form():
        """Node provisioning form"""
        # Implementation remains the same
        pass
    
    @app.route('/provision', methods=['POST'])
    def provision_node():
        """Process node provisioning form"""
        # Transform form data to API format
        api_data = transform_form_to_api(request.form)
        
        # Use updated API endpoint
        result = node_provisioner.provision_node(api_data)
        
        if result.get('success'):
            flash('Node provisioning started successfully!', 'success')
            return redirect(url_for('deployments'))
        else:
            flash(f'Error: {result.get("error")}', 'error')
            return render_template('provision_form.html')
    
    # ... other routes with updated path references ...
```

### 4. JavaScript Updates
```javascript
// static/js/main.js - Updated JavaScript

// Update API endpoint URLs
const API_ENDPOINTS = {
    config: '/api/config',
    status: '/api/status',
    dns: '/api/dns',
    cleanup: '/api/cleanup',
    boot: '/boot'
};

// Update AJAX calls to use new paths
async function provisionNode(nodeData) {
    try {
        const response = await fetch(`${API_ENDPOINTS.config}/nodes`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(nodeData)
        });
        
        return await response.json();
    } catch (error) {
        console.error('Provisioning error:', error);
        throw error;
    }
}

// Update status monitoring
async function getNodeStatus(nodeId) {
    try {
        const response = await fetch(`${API_ENDPOINTS.status}/nodes/${nodeId}`);
        return await response.json();
    } catch (error) {
        console.error('Status check error:', error);
        throw error;
    }
}
```

## Backward Compatibility
1. **Maintain Old Endpoints Temporarily**
   - Keep old endpoints functional with deprecation warnings
   - Implement redirects from old paths to new paths
   - Provide migration period for clients

2. **Deprecation Strategy**
   - Add deprecation headers to old endpoints
   - Log usage of deprecated endpoints
   - Plan for removal in future version

## Rollback Procedure
1. **In Case of Issues**
   - Revert to previous application code
   - Restore previous configuration
   - Restart application service
   - Verify functionality

2. **Monitoring During Deployment**
   - Monitor application logs
   - Check for errors in new endpoints
   - Watch system resources
   - Monitor response times

## Timeline
- **Preparation**: 2 hours
- **Code Implementation**: 8 hours
- **Testing**: 4 hours
- **Production Deployment**: 2 hours
- **Post-Deployment Monitoring**: 2 hours

## Success Criteria
- All services accessible through new path structure
- Backward compatibility maintained during transition
- No service interruptions
- Successful rollback capability
- Proper logging and error handling
- Compatibility with updated Nginx and Gunicorn configurations

This implementation plan will result in a restructured application that works efficiently with the new Nginx reverse proxy architecture.