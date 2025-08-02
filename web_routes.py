"""
Web UI routes for Nutanix VPC Orchestrator
Adds web interface to the existing API-based Flask application
"""

from flask import render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime
import json
import logging

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

    @app.route('/provision', methods=['GET', 'POST'])
    def web_provision_node():
        """Node provisioning form"""
        if request.method == 'POST':
            try:
                # Get form data
                node_config = {
                    'node_config': {
                        'node_name': request.form.get('node_name'),
                        'server_profile': request.form.get('server_profile'),
                        'cluster_role': request.form.get('cluster_role'),
                        'storage_config': {
                            'data_drives': request.form.getlist('data_drives')
                        }
                    },
                    'network_config': {
                        'management_subnet': request.form.get('management_subnet'),
                        'workload_subnet': request.form.get('workload_subnet', 'auto'),
                        'cluster_operation': request.form.get('cluster_operation')
                    }
                }
                
                # Validate required fields
                if not all([
                    node_config['node_config']['node_name'],
                    node_config['node_config']['server_profile'],
                    node_config['network_config']['cluster_operation']
                ]):
                    flash('Please fill in all required fields', 'error')
                    return render_template('provision_form.html')
                
                # Submit to existing API endpoint via internal call
                try:
                    result = node_provisioner.provision_node(node_config)
                    flash(f'Node {node_config["node_config"]["node_name"]} provisioning started successfully!', 'success')
                    return redirect(url_for('deployments'))
                except Exception as e:
                    logger.error(f"Error provisioning node: {e}")
                    flash(f'Error provisioning node: {str(e)}', 'error')
                
                if result.get('success'):
                    flash(f'Node {node_config["node_config"]["node_name"]} provisioning started successfully!', 'success')
                    return redirect(url_for('deployments'))
                else:
                    flash(f'Error provisioning node: {result.get("error", "Unknown error")}', 'error')
                    
            except Exception as e:
                logger.error(f"Error provisioning node: {e}")
                flash(f'Error provisioning node: {str(e)}', 'error')
        
        return render_template('provision_form.html')

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

def get_dashboard_stats(db):
    """Get dashboard statistics"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                # Active nodes
                cursor.execute("SELECT COUNT(*) FROM nodes WHERE deployment_status = 'running'")
                active_nodes = cursor.fetchone()[0]
                
                # Total clusters
                cursor.execute("SELECT COUNT(DISTINCT cluster_name) FROM nodes WHERE cluster_name IS NOT NULL")
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
                    SELECT id, node_name, ip_address, cluster_role, cluster_name,
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
                           dh.duration, dh.node_id
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
                        'duration': row[5],
                        'node_id': row[6]
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
                    SELECT id, node_name, ip_address, cluster_role, cluster_name,
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
                    SELECT phase, status, timestamp, duration, logs
                    FROM deployment_history
                    WHERE node_id = %s
                    ORDER BY timestamp DESC
                """, (node_id,))
                
                history = []
                for row in cursor.fetchall():
                    history.append({
                        'phase': row[0],
                        'status': row[1],
                        'timestamp': row[2],
                        'duration': row[3],
                        'logs': row[4]
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