"""
Web UI routes for Nutanix VPC Orchestrator
Adds web interface to the existing API-based Flask application
"""

from flask import render_template, request, jsonify, redirect, url_for, flash, Response
from datetime import datetime
import json
import logging
import csv
import io
import psycopg2.extras
from server_profiles import ServerProfileConfig


logger = logging.getLogger(__name__)

def register_web_routes(app, db, node_provisioner, status_monitor):
    """Register web UI routes with the Flask application"""
    
    @app.route('/')
    def dashboard():
        """Main dashboard view"""
        try:
            # Get summary statistics
            stats = get_dashboard_stats(db)
            recent_deployments = get_recent_deployments(db, limit=5)
            return render_template('dashboard.html', 
                                 stats=stats, 
                                 recent_deployments=recent_deployments)
        except Exception as e:
            logger.error(f"Error loading dashboard: {e}")
            flash('Error loading dashboard data', 'error')
            return render_template('dashboard.html', stats={}, recent_deployments=[])

    @app.route('/nodes')
    def nodes():
        """Cluster nodes view"""
        try:
            nodes = get_all_nodes(db)
            return render_template('nodes.html', nodes=nodes)
        except Exception as e:
            logger.error(f"Error loading nodes: {e}")
            flash('Error loading nodes data', 'error')
            return render_template('nodes.html', nodes=[])

    @app.route('/deployments')
    def deployments():
        """Deployment history view"""
        try:
            deployments = get_deployment_history(db)
            return render_template('deployments.html', deployments=deployments)
        except Exception as e:
            logger.error(f"Error loading deployments: {e}")
            flash('Error loading deployment data', 'error')
            return render_template('deployments.html', deployments=[])

    @app.route('/monitoring')
    def monitoring():
        """System monitoring view"""
        try:
            health_data = get_system_health()
            return render_template('monitoring.html', health_data=health_data)
        except Exception as e:
            logger.error(f"Error loading monitoring data: {e}")
            flash('Error loading monitoring data', 'error')
            return render_template('monitoring.html', health_data={})

    @app.route('/clusters')
    def clusters():
        """Cluster management view"""
        try:
            # Get all clusters
            clusters = get_all_clusters(db)
            return render_template('clusters.html', clusters=clusters)
        except Exception as e:
            logger.error(f"Error loading clusters: {e}")
            flash('Error loading clusters data', 'error')
            return render_template('clusters.html', clusters=[])

    @app.route('/clusters/create', methods=['GET', 'POST'])
    def web_create_cluster():
        """Create cluster form"""
        if request.method == 'POST':
            try:
                # Get form data
                cluster_config = {
                    'cluster_config': {
                        'cluster_operation': 'create_new',
                        'cluster_name': request.form.get('cluster_name'),
                        'cluster_type': request.form.get('cluster_type'),
                        'nodes': request.form.getlist('nodes')
                    }
                }
                
                # Validate required fields
                if not cluster_config['cluster_config']['cluster_name']:
                    flash('Please enter a cluster name', 'error')
                    return render_template('cluster_form.html', available_nodes=get_available_nodes(db))
                
                if not cluster_config['cluster_config']['nodes']:
                    flash('Please select at least one node', 'error')
                    return render_template('cluster_form.html', available_nodes=get_available_nodes(db))
                
                # Validate node count for multi-node clusters
                if cluster_config['cluster_config']['cluster_type'] == 'multi_node' and len(cluster_config['cluster_config']['nodes']) < 3:
                    flash('Multi-node clusters require at least 3 nodes', 'warning')
                
                # Submit to cluster manager
                try:
                    # Import cluster manager
                    from cluster_manager import ClusterManager
                    cluster_manager = ClusterManager()
                    result = cluster_manager.create_cluster(cluster_config)
                    
                    flash(f'Cluster "{cluster_config["cluster_config"]["cluster_name"]}" creation started successfully!', 'success')
                    return redirect(url_for('clusters'))
                    
                except Exception as e:
                    logger.error(f"Error creating cluster: {e}")
                    flash(f'Error creating cluster: {str(e)}', 'error')
                    
            except Exception as e:
                logger.error(f"Error processing cluster form: {e}")
                flash(f'Error processing form: {str(e)}', 'error')
        
        # GET request - show form
        try:
            available_nodes = get_available_nodes(db)
            return render_template('cluster_form.html', available_nodes=available_nodes)
        except Exception as e:
            logger.error(f"Error loading cluster form: {e}")
            flash('Error loading cluster form', 'error')
            return redirect(url_for('clusters'))

    @app.route('/cluster/<int:cluster_id>')
    def cluster_details(cluster_id):
        """Individual cluster details view"""
        try:
            cluster = get_cluster_by_id(db, cluster_id)
            if not cluster:
                flash('Cluster not found', 'error')
                return redirect(url_for('clusters'))
            
            # Get nodes in this cluster
            nodes = get_nodes_by_cluster(db, cluster_id)
            return render_template('cluster_details.html', cluster=cluster, nodes=nodes)
        except Exception as e:
            logger.error(f"Error loading cluster details: {e}")
            flash('Error loading cluster details', 'error')
            return redirect(url_for('clusters'))

    @app.route('/provision', methods=['GET', 'POST'])
    def web_provision_node():
        """Node provisioning form with server profile integration"""
        if request.method == 'POST':
            try:
                # Get form data
                node_config = {
                    'node_config': {
                        'node_name': request.form.get('node_name'),
                        'server_profile': request.form.get('server_profile'),
                        'cluster_role': request.form.get('cluster_role'),  # Optional - will use recommended if empty
                        'storage_template': request.form.get('storage_template', 'nutanix_default')
                        # Note: storage_config is now auto-generated from server_profile
                    },
                    'network_config': {
                        'management_subnet': 'auto',  # Using config defaults
                        'workload_subnets': request.form.getlist('workload_subnets'),
                        'cluster_operation': request.form.get('cluster_operation')
                    },
                    'cluster_config': {
                        'cluster_type': request.form.get('cluster_type', 'multi_node')
                    }
                }
                
                # Validate required fields
                if not all([
                    node_config['node_config']['node_name'],
                    node_config['node_config']['server_profile'],
                    node_config['network_config']['cluster_operation']
                ]):
                    flash('Please fill in all required fields', 'error')
                    return render_template('provision_form.html', 
                                         server_profiles=get_available_server_profiles(),
                                         storage_templates=get_storage_templates())
                
                # Validate server profile
                server_profiles = ServerProfileConfig()
                if not server_profiles.validate_profile(node_config['node_config']['server_profile']):
                    flash(f'Invalid server profile: {node_config["node_config"]["server_profile"]}', 'error')
                    return render_template('provision_form.html',
                                         server_profiles=get_available_server_profiles(),
                                         storage_templates=get_storage_templates())
                
                # Submit to provisioner
                try:
                    result = node_provisioner.provision_node(node_config)
                    
                    # Get profile info for success message
                    profile_info = result.get('server_profile_info', {})
                    profile_display = profile_info.get('display_name', node_config['node_config']['server_profile'])
                    
                    flash(f'Node "{node_config["node_config"]["node_name"]}" provisioning started successfully on {profile_display}!', 'success')
                    return redirect(url_for('node_details', node_id=result['node_id']))
                    
                except Exception as e:
                    logger.error(f"Error provisioning node: {e}")
                    flash(f'Error provisioning node: {str(e)}', 'error')
                    
            except Exception as e:
                logger.error(f"Error processing provision form: {e}")
                flash(f'Error processing form: {str(e)}', 'error')
        
        # GET request - show form
        try:
            server_profiles = get_available_server_profiles()
            storage_templates = get_storage_templates()
            
            # Get list of workload subnets
            try:
                workload_subnets = ibm_cloud.list_subnets()
                # Filter subnets to only include those in the same VPC
                workload_subnets = [subnet for subnet in workload_subnets if subnet.get('vpc', {}).get('id') == ibm_cloud.vpc_id]
            except Exception as e:
                logger.error(f"Error getting workload subnets: {e}")
                workload_subnets = []
            
            return render_template('provision_form.html',
                                 server_profiles=server_profiles,
                                 storage_templates=storage_templates,
                                 workload_subnets=workload_subnets)
        except Exception as e:
            logger.error(f"Error loading provision form: {e}")
            flash('Error loading provision form', 'error')
            return redirect(url_for('dashboard'))

    @app.route('/node/<int:node_id>')
    def node_details(node_id):
        """Individual node details view"""
        try:
            node = get_node_by_id(db, node_id)
            if not node:
                flash('Node not found', 'error')
                return redirect(url_for('nodes'))
            
            deployment_history = get_node_deployment_history(db, node_id)
            return render_template('node_details.html', 
                                 node=node, 
                                 deployment_history=deployment_history)
        except Exception as e:
            logger.error(f"Error loading node details: {e}")
            flash('Error loading node details', 'error')
            return redirect(url_for('nodes'))

    @app.route('/deployment/<deployment_id>/logs')
    def deployment_logs(deployment_id):
        """Deployment logs view"""
        try:
            logs = get_deployment_logs(db, deployment_id)
            deployment = get_deployment_by_id(db, deployment_id)
            return render_template('deployment_logs.html', 
                                 logs=logs, 
                                 deployment=deployment)
        except Exception as e:
            logger.error(f"Error loading deployment logs: {e}")
            flash('Error loading deployment logs', 'error')
            return redirect(url_for('deployments'))

    # AJAX endpoints for dynamic updates
    @app.route('/api/web/dashboard-stats')
    def ajax_dashboard_stats():
        """AJAX endpoint for dashboard statistics"""
        try:
            stats = get_dashboard_stats(db)
            return jsonify(stats)
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/web/node-status/<int:node_id>')
    def ajax_node_status(node_id):
        """AJAX endpoint for node status updates"""
        try:
            status = status_monitor.get_node_status(node_id)
            return jsonify(status)
        except Exception as e:
            logger.error(f"Error getting node status: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/web/deployment-progress/<deployment_id>')
    def ajax_deployment_progress(deployment_id):
        """AJAX endpoint for deployment progress"""
        try:
            progress = get_deployment_progress(db, deployment_id)
            return jsonify(progress)
        except Exception as e:
            logger.error(f"Error getting deployment progress: {e}")
            return jsonify({'error': str(e)}), 500
        
def add_database_viewer_routes(app, db):
    """Add database viewer routes to the Flask application"""

    def add_database_viewer_routes(app, db):
        """Add database viewer routes to the Flask application"""
    
    @app.route('/database')
    def database_viewer():
        """Database viewer main page"""
        try:
            # Get list of available tables
            tables = get_database_tables(db)
            
            # Get selected table from query params
            selected_table = request.args.get('table')
            
            context = {
                'tables': tables,
                'current_table': selected_table,
                'last_updated': None,
                'row_count': 0,
                'table_data': None,
                'current_table_display': None,
                'error': None
            }
            
            # Load initial table data if table is selected
            if selected_table:
                try:
                    table_data = get_table_data(db, selected_table)
                    context.update({
                        'table_data': table_data,
                        'current_table_display': get_table_display_name(selected_table),
                        'row_count': len(table_data['rows']) if table_data else 0,
                        'last_updated': datetime.now().strftime('%H:%M:%S')
                    })
                except Exception as e:
                    context['error'] = str(e)
                    logger.error(f"Error loading initial table data for {selected_table}: {e}")
            
            return render_template('database_viewer.html', **context)
            
        except Exception as e:
            logger.error(f"Error loading database viewer: {e}")
            return render_template('database_viewer.html', 
                                 tables=[], 
                                 error=f"Error loading database viewer: {str(e)}")

    @app.route('/api/web/database-table')
    def api_get_table_data():
        """API endpoint to get table data"""
        table_name = request.args.get('table')
        
        if not table_name:
            return jsonify({'error': 'Table name is required'}), 400
        
        try:
            table_data = get_table_data(db, table_name)
            if table_data:
                return jsonify({
                    'table_name': table_name,
                    'table_display_name': get_table_display_name(table_name),
                    'columns': table_data['columns'],
                    'rows': table_data['rows'],
                    'row_count': len(table_data['rows']),
                    'last_updated': datetime.now().isoformat()
                })
            else:
                return jsonify({'error': f'Table {table_name} not found'}), 404
                
        except Exception as e:
            logger.error(f"Error getting table data for {table_name}: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/web/database-schema')
    def api_get_table_schema():
        """API endpoint to get table schema"""
        table_name = request.args.get('table')
        
        if not table_name:
            return jsonify({'error': 'Table name is required'}), 400
        
        try:
            schema = get_table_schema(db, table_name)
            if schema:
                return jsonify({
                    'table_name': table_name,
                    'columns': schema
                })
            else:
                return jsonify({'error': f'Schema for table {table_name} not found'}), 404
                
        except Exception as e:
            logger.error(f"Error getting table schema for {table_name}: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/web/database-export')
    def api_export_table():
        """API endpoint to export table data as CSV"""
        table_name = request.args.get('table')
        export_format = request.args.get('format', 'csv')
        
        if not table_name:
            return jsonify({'error': 'Table name is required'}), 400
        
        if export_format != 'csv':
            return jsonify({'error': 'Only CSV format is supported'}), 400
        
        try:
            table_data = get_table_data(db, table_name)
            if not table_data:
                return jsonify({'error': f'Table {table_name} not found'}), 404
            
            # Create CSV content
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write headers
            writer.writerow(table_data['columns'])
            
            # Write data rows
            for row in table_data['rows']:
                # Convert None values to empty strings for CSV
                csv_row = ['' if cell is None else str(cell) for cell in row]
                writer.writerow(csv_row)
            
            # Create response
            csv_content = output.getvalue()
            output.close()
            
            filename = f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            response = Response(
                csv_content,
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename={filename}'
                }
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error exporting table {table_name}: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/web/database-tables')
    def api_get_database_tables():
        """API endpoint to get list of available tables"""
        try:
            tables = get_database_tables(db)
            return jsonify({'tables': tables})
        except Exception as e:
            logger.error(f"Error getting database tables: {e}")
            return jsonify({'error': str(e)}), 500

def register_additional_routes(app, db, node_provisioner, status_monitor):
    """Register additional routes for server profile integration"""
    
    @app.route('/api/web/profile-storage-config')
    def api_profile_storage_config():
        """Get storage configuration for a server profile"""
        try:
            profile = request.args.get('profile')
            template = request.args.get('template', 'nutanix_default')
            
            if not profile:
                return jsonify({'error': 'Profile parameter required'}), 400
            
            server_profiles = ServerProfileConfig()
            
            if not server_profiles.validate_profile(profile):
                return jsonify({'error': f'Unknown server profile: {profile}'}), 400
            
            storage_config = server_profiles.get_storage_config(profile, template)
            return jsonify(storage_config)
            
        except Exception as e:
            logger.error(f"Error getting profile storage config: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/web/profile-details')
    def api_profile_details():
        """Get detailed information about a server profile"""
        try:
            profile = request.args.get('profile')
            
            if not profile:
                return jsonify({'error': 'Profile parameter required'}), 400
            
            server_profiles = ServerProfileConfig()
            profile_summary = server_profiles.get_profile_summary(profile)
            
            if not profile_summary:
                return jsonify({'error': f'Unknown server profile: {profile}'}), 404
            
            return jsonify(profile_summary)
            
        except Exception as e:
            logger.error(f"Error getting profile details: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/web/server-profiles')
    def api_server_profiles():
        """Get list of all available server profiles"""
        try:
            server_profiles = ServerProfileConfig()
            profiles = server_profiles.get_available_profiles()
            return jsonify({'profiles': profiles})
            
        except Exception as e:
            logger.error(f"Error getting server profiles: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/web/storage-templates')
    def api_storage_templates():
        """Get available storage templates"""
        try:
            server_profiles = ServerProfileConfig()
            templates = []
            
            for template_name, template_config in server_profiles.STORAGE_TEMPLATES.items():
                templates.append({
                    'name': template_name,
                    'description': template_config['description'],
                    'exclude_drives': template_config['exclude_drives'],
                    'raid_config': template_config['raid_config']
                })
            
            return jsonify({'templates': templates})
            
        except Exception as e:
            logger.error(f"Error getting storage templates: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/web/validate-node-config', methods=['POST'])
    def api_validate_node_config():
        """Validate node configuration before provisioning"""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            
            # Validate required fields
            required_fields = ['node_name', 'server_profile', 'cluster_operation']
            missing_fields = [field for field in required_fields if not data.get(field)]
            
            if missing_fields:
                return jsonify({
                    'valid': False,
                    'error': f'Missing required fields: {", ".join(missing_fields)}'
                }), 400
            
            # Validate server profile
            server_profiles = ServerProfileConfig()
            if not server_profiles.validate_profile(data['server_profile']):
                return jsonify({
                    'valid': False,
                    'error': f'Unknown server profile: {data["server_profile"]}'
                }), 400
            
            # Check if node name already exists
            existing_node = db.get_node_by_name(data['node_name'])
            if existing_node and existing_node['deployment_status'] not in ['cleanup_completed', 'failed']:
                return jsonify({
                    'valid': False,
                    'error': f'Node name "{data["node_name"]}" already exists with status: {existing_node["deployment_status"]}'
                }), 400
            
            # Generate configuration preview
            storage_template = data.get('storage_template', 'nutanix_default')
            storage_config = server_profiles.get_storage_config(data['server_profile'], storage_template)
            profile_summary = server_profiles.get_profile_summary(data['server_profile'])
            
            return jsonify({
                'valid': True,
                'preview': {
                    'node_name': data['node_name'],
                    'server_profile': data['server_profile'],
                    'cluster_role': data.get('cluster_role') or server_profiles.get_recommended_cluster_role(data['server_profile']),
                    'cluster_operation': data['cluster_operation'],
                    'storage_config': storage_config,
                    'profile_summary': profile_summary,
                    'estimated_deployment_time': '15-20 minutes'
                }
            })
            
        except Exception as e:
            logger.error(f"Error validating node config: {e}")
            return jsonify({'error': str(e)}), 500

# Helper functions for dashboard
def get_dashboard_stats(db):
    """Get dashboard statistics"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                # Active nodes
                cursor.execute("SELECT COUNT(*) FROM nodes WHERE deployment_status = 'running'")
                active_nodes = cursor.fetchone()[0]
                
                # Total clusters
                cursor.execute("SELECT COUNT(*) FROM clusters")
                total_clusters = cursor.fetchone()[0]
                
                # Total deployments
                cursor.execute("SELECT COUNT(*) FROM nodes")
                total_deployments = cursor.fetchone()[0]
                
                # Success rate
                cursor.execute("SELECT COUNT(*) FROM nodes WHERE deployment_status = 'running'")
                successful = cursor.fetchone()[0]
                success_rate = (successful / total_deployments * 100) if total_deployments > 0 else 0
        
        return {
            'active_nodes': active_nodes,
            'total_clusters': total_clusters,
            'total_deployments': total_deployments,
            'success_rate': f"{success_rate:.1f}%"
        }
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        return {
            'active_nodes': 0,
            'total_clusters': 0,
            'total_deployments': 0,
            'success_rate': '0%'
        }

def get_recent_deployments(db, limit=5):
    """Get recent deployments"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, node_name, deployment_status, cluster_name, created_at, progress_percentage
                    FROM nodes
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                
                deployments = []
                for row in cursor.fetchall():
                    deployments.append({
                        'id': row[0],
                        'node_name': row[1],
                        'status': row[2],
                        'cluster': row[3] or 'Not assigned',
                        'created_at': row[4],
                        'progress': row[5] or 0
                    })
        
        return deployments
    except Exception as e:
        logger.error(f"Error getting recent deployments: {e}")
        return []

def get_all_nodes(db):
    """Get all nodes"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, node_name, management_ip, cluster_role, cluster_name,
                           server_profile, deployment_status, created_at
                    FROM nodes
                    ORDER BY created_at DESC
                """)
                
                nodes = []
                for row in cursor.fetchall():
                    nodes.append({
                        'id': row[0],
                        'node_name': row[1],
                        'ip_address': row[2] or 'Pending',
                        'cluster_role': row[3],
                        'cluster_name': row[4] or 'Not assigned',
                        'server_profile': row[5],
                        'status': row[6],
                        'created_at': row[7]
                    })
        
        return nodes
    except Exception as e:
        logger.error(f"Error getting all nodes: {e}")
        return []

def get_deployment_history(db):
    """Get deployment history"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT dh.id, n.node_name, dh.phase, dh.status, dh.timestamp,
                           dh.node_id
                    FROM deployment_history dh
                    JOIN nodes n ON dh.node_id = n.id
                    ORDER BY dh.timestamp DESC
                """)
                
                deployments = []
                for row in cursor.fetchall():
                    deployments.append({
                        'id': row[0],
                        'node_name': row[1],
                        'phase': row[2],
                        'status': row[3],
                        'timestamp': row[4],
                        'node_id': row[5]
                    })
        
        return deployments
    except Exception as e:
        logger.error(f"Error getting deployment history: {e}")
        return []

def get_system_health():
    """Get system health information"""
    return {
        'pxe_server': {'status': 'running', 'response_time': '45ms'},
        'database': {'status': 'running', 'response_time': '12ms'},
        'ibm_cloud_api': {'status': 'connected', 'response_time': '156ms'},
        'disk_usage': '2.1 GB',
        'avg_deploy_time': '15 min'
    }

def get_node_by_id(db, node_id):
    """Get node by ID"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, node_name, management_ip, cluster_role, cluster_name,
                           server_profile, deployment_status, created_at,
                           progress_percentage, current_phase
                    FROM nodes
                    WHERE id = %s
                """, (node_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'node_name': row[1],
                        'ip_address': row[2],
                        'cluster_role': row[3],
                        'cluster_name': row[4],
                        'server_profile': row[5],
                        'status': row[6],
                        'created_at': row[7],
                        'progress': row[8] or 0,
                'current_phase': row[9]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting node by ID: {e}")
        return None

def get_node_deployment_history(db, node_id):
    """Get deployment history for a specific node"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT phase, status, timestamp
                    FROM deployment_history
                    WHERE node_id = %s
                    ORDER BY timestamp DESC
                """, (node_id,))
                
                history = []
                for row in cursor.fetchall():
                    history.append({
                        'phase': row[0],
                        'status': row[1],
                        'timestamp': row[2]
                    })
        
        return history
    except Exception as e:
        logger.error(f"Error getting node deployment history: {e}")
        return []

def get_deployment_logs(db, deployment_id):
    """Get deployment logs"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT logs, timestamp, phase
                    FROM deployment_history
                    WHERE id = %s
                """, (deployment_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'logs': row[0] or 'No logs available',
                        'timestamp': row[1],
                        'phase': row[2]
            }
        return {'logs': 'Deployment not found', 'timestamp': None, 'phase': None}
    except Exception as e:
        logger.error(f"Error getting deployment logs: {e}")
        return {'logs': f'Error loading logs: {str(e)}', 'timestamp': None, 'phase': None}

def get_deployment_by_id(db, deployment_id):
    """Get deployment by ID"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT dh.id, n.node_name, dh.phase, dh.status
                    FROM deployment_history dh
                    JOIN nodes n ON dh.node_id = n.id
                    WHERE dh.id = %s
                """, (deployment_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'node_name': row[1],
                        'phase': row[2],
                'status': row[3]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting deployment by ID: {e}")
        return None

def get_deployment_progress(db, deployment_id):
    """Get deployment progress"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT n.progress_percentage, n.current_phase, n.deployment_status
                    FROM deployment_history dh
                    JOIN nodes n ON dh.node_id = n.id
                    WHERE dh.id = %s
                """, (deployment_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'progress': row[0] or 0,
                'current_phase': row[1] or 'Starting',
                'status': row[2]
            }
        return {'progress': 0, 'current_phase': 'Unknown', 'status': 'unknown'}
    except Exception as e:
        logger.error(f"Error getting deployment progress: {e}")
        return {'progress': 0, 'current_phase': 'Error', 'status': 'error'}
    
# Helper functions for database viewer
def get_database_tables(db):
    """Get list of available database tables with metadata"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Get tables from information_schema
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                """)
                
                table_names = [row[0] for row in cur.fetchall()]
                
                tables = []
                for table_name in table_names:
                    try:
                        # Get row count for each table
                        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                        row_count = cur.fetchone()[0]
                        
                        tables.append({
                            'name': table_name,
                            'display_name': get_table_display_name(table_name),
                            'row_count': row_count
                        })
                    except Exception as e:
                        logger.warning(f"Could not get row count for table {table_name}: {e}")
                        tables.append({
                            'name': table_name,
                            'display_name': get_table_display_name(table_name),
                            'row_count': 0
                        })
                
                return tables
                
    except Exception as e:
        logger.error(f"Error getting database tables: {e}")
        return []

def get_table_data(db, table_name):
    """Get data from a specific table"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Validate table name to prevent SQL injection
                if not is_valid_table_name(db, table_name):
                    raise ValueError(f"Table {table_name} does not exist")
                
                # Get column names
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s 
                    AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, (table_name,))
                
                columns = [row[0] for row in cur.fetchall()]
                
                if not columns:
                    return None
                
                # Get table data with limit to prevent overwhelming the browser
                limit = request.args.get('limit', 1000, type=int)
                offset = request.args.get('offset', 0, type=int)
                
                cur.execute(f"""
                    SELECT * FROM {table_name} 
                    ORDER BY 1 
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                
                rows = []
                for row in cur.fetchall():
                    # Convert row to list and handle special types
                    converted_row = []
                    for cell in row:
                        if isinstance(cell, datetime):
                            converted_row.append(cell.isoformat())
                        elif isinstance(cell, dict):
                            converted_row.append(json.dumps(cell))
                        else:
                            converted_row.append(cell)
                    rows.append(converted_row)
                
                return {
                    'columns': columns,
                    'rows': rows
                }
                
    except Exception as e:
        logger.error(f"Error getting table data for {table_name}: {e}")
        raise

def get_table_schema(db, table_name):
    """Get schema information for a specific table"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Validate table name
                if not is_valid_table_name(db, table_name):
                    raise ValueError(f"Table {table_name} does not exist")
                
                cur.execute("""
                    SELECT 
                        column_name,
                        data_type,
                        is_nullable,
                        column_default,
                        character_maximum_length,
                        numeric_precision,
                        numeric_scale
                    FROM information_schema.columns 
                    WHERE table_name = %s 
                    AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, (table_name,))
                
                schema_info = []
                for row in cur.fetchall():
                    column_info = {
                        'name': row[0],
                        'type': format_column_type(row[1], row[4], row[5], row[6]),
                        'nullable': row[2] == 'YES',
                        'default': row[3] if row[3] is not None else ''
                    }
                    schema_info.append(column_info)
                
                return schema_info
                
    except Exception as e:
        logger.error(f"Error getting table schema for {table_name}: {e}")
        raise

def is_valid_table_name(db, table_name):
    """Validate that table name exists in the database"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = %s 
                    AND table_schema = 'public'
                    AND table_type = 'BASE TABLE'
                """, (table_name,))
                
                return cur.fetchone() is not None
                
    except Exception as e:
        logger.error(f"Error validating table name {table_name}: {e}")
        return False

def get_table_display_name(table_name):
    """Convert table name to display-friendly format"""
    display_names = {
        'nodes': 'Cluster Nodes',
        'clusters': 'Clusters',
        'deployment_history': 'Deployment History',
        'ip_reservations': 'IP Reservations',
        'dns_records': 'DNS Records',
        'vnic_info': 'Virtual Network Interfaces'
    }
    
    return display_names.get(table_name, table_name.replace('_', ' ').title())

def format_column_type(data_type, max_length, precision, scale):
    """Format column type with length/precision information"""
    if data_type == 'character varying' and max_length:
        return f"VARCHAR({max_length})"
    elif data_type == 'character' and max_length:
        return f"CHAR({max_length})"
    elif data_type == 'numeric' and precision and scale:
        return f"NUMERIC({precision},{scale})"
    elif data_type == 'numeric' and precision:
        return f"NUMERIC({precision})"
    else:
        return data_type.upper()
    
# Helper functions for the web interface
def get_available_server_profiles():
    """Get available server profiles for the web interface"""
    try:
        server_profiles = ServerProfileConfig()
        return server_profiles.get_available_profiles()
    except Exception as e:
        logger.error(f"Error getting server profiles: {e}")
        return []

def get_storage_templates():
    """Get available storage templates"""
    try:
        server_profiles = ServerProfileConfig()
        templates = []
        
        for template_name, template_config in server_profiles.STORAGE_TEMPLATES.items():
            templates.append({
                'name': template_name,
                'display_name': template_name.replace('_', ' ').title(),
                'description': template_config['description']
            })
        
        return templates
    except Exception as e:
        logger.error(f"Error getting storage templates: {e}")
        return [
            {
                'name': 'nutanix_default',
                'display_name': 'Default Configuration',
                'description': 'Use all NVMe drives for maximum storage capacity'
            }
        ]

def get_profile_details(server_profile):
    """Get detailed information about a server profile"""
    try:
        server_profiles = ServerProfileConfig()
        return server_profiles.get_profile_summary(server_profile)
    except Exception as e:
        logger.error(f"Error getting profile details for {server_profile}: {e}")
        return None
def get_all_clusters(db):
    """Get all clusters"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, cluster_name, cluster_ip, cluster_dns, node_count, status, created_at, updated_at
                    FROM clusters 
                    ORDER BY created_at DESC
                """)
                
                clusters = []
                for row in cur.fetchall():
                    clusters.append({
                        'id': row[0],
                        'cluster_name': row[1],
                        'cluster_ip': str(row[2]) if row[2] else None,
                        'cluster_dns': row[3],
                        'node_count': row[4],
                        'status': row[5],
                        'created_at': row[6],
                        'updated_at': row[7]
                    })
                
                return clusters
    except Exception as e:
        logger.error(f"Error getting clusters: {e}")
        return []

def get_available_nodes(db):
    """Get nodes that are not yet assigned to a cluster"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, node_name, server_profile, deployment_status
                    FROM nodes 
                    WHERE cluster_name IS NULL OR cluster_name = ''
                    ORDER BY created_at DESC
                """)
                
                nodes = []
                for row in cur.fetchall():
                    nodes.append({
                        'id': row[0],
                        'node_name': row[1],
                        'server_profile': row[2],
                        'deployment_status': row[3]
                    })
                
                return nodes
    except Exception as e:
        logger.error(f"Error getting available nodes: {e}")
        return []

def get_cluster_by_id(db, cluster_id):
    """Get cluster by ID"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, cluster_name, cluster_ip, cluster_dns, created_by_node, node_count, status, created_at, updated_at
                    FROM clusters 
                    WHERE id = %s
                """, (cluster_id,))
                
                row = cur.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'cluster_name': row[1],
                        'cluster_ip': str(row[2]) if row[2] else None,
                        'cluster_dns': row[3],
                        'created_by_node': row[4],
                        'node_count': row[5],
                        'status': row[6],
                        'created_at': row[7],
                        'updated_at': row[8]
                    }
                return None
    except Exception as e:
        logger.error(f"Error getting cluster {cluster_id}: {e}")
        return None

def get_nodes_by_cluster(db, cluster_id):
    """Get nodes in a specific cluster"""
    try:
        # First get the cluster name
        cluster = get_cluster_by_id(db, cluster_id)
        if not cluster:
            return []
        
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, node_name, server_profile, management_ip, deployment_status
                    FROM nodes 
                    WHERE cluster_name = %s
                    ORDER BY created_at DESC
                """, (cluster['cluster_name'],))
                
                nodes = []
                for row in cur.fetchall():
                    nodes.append({
                        'id': row[0],
                        'node_name': row[1],
                        'server_profile': row[2],
                        'management_ip': str(row[3]) if row[3] else None,
                        'deployment_status': row[4]
                    })
                
                return nodes
    except Exception as e:
        logger.error(f"Error getting nodes for cluster {cluster_id}: {e}")
        return []