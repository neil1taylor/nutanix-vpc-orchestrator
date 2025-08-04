"""
Database models and operations for Nutanix PXE/Config Server
"""
import psycopg2
import psycopg2.extras
import json
from datetime import datetime
from config import Config
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.connection_string = Config.DATABASE_URL
        self.init_database()
    
    def get_connection(self):
        """Get database connection"""
        return psycopg2.connect(self.connection_string)
    
    def init_database(self):
        """Initialize database tables"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Create tables
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS nodes (
                            id SERIAL PRIMARY KEY,
                            node_name VARCHAR(255) UNIQUE NOT NULL,
                            server_profile VARCHAR(100),
                            cluster_role VARCHAR(50),
                            deployment_status VARCHAR(50) DEFAULT 'pending',
                            bare_metal_id VARCHAR(255),
                            management_vnic_id VARCHAR(255),
                            management_ip INET,
                            workload_vnic_id VARCHAR(255),
                            workload_ip INET,
                            workload_vnics JSONB,
                            nutanix_config JSONB,
                            progress_percentage INTEGER DEFAULT 0,
                            current_phase VARCHAR(100),
                            cluster_name VARCHAR(100),
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW()
                        );
                    """)
                    
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS clusters (
                            id SERIAL PRIMARY KEY,
                            cluster_name VARCHAR(255) UNIQUE NOT NULL,
                            cluster_ip INET,
                            cluster_dns VARCHAR(255),
                            created_by_node INTEGER REFERENCES nodes(id),
                            node_count INTEGER DEFAULT 0,
                            status VARCHAR(50) DEFAULT 'creating',
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW()
                        );
                    """)
                    
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS deployment_history (
                            id SERIAL PRIMARY KEY,
                            node_id INTEGER REFERENCES nodes(id),
                            phase VARCHAR(100),
                            status VARCHAR(50),
                            message TEXT,
                            duration INTEGER DEFAULT 0,
                            timestamp TIMESTAMP DEFAULT NOW()
                        );
                    """)
                    
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS ip_reservations (
                            id SERIAL PRIMARY KEY,
                            node_name VARCHAR(255),
                            ip_address INET,
                            ip_type VARCHAR(50),
                            reservation_id VARCHAR(255),
                            subnet_id VARCHAR(255),
                            created_at TIMESTAMP DEFAULT NOW()
                        );
                    """)
                    
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS dns_records (
                            id SERIAL PRIMARY KEY,
                            node_name VARCHAR(255),
                            record_name VARCHAR(255),
                            record_type VARCHAR(10),
                            rdata VARCHAR(255),
                            record_id VARCHAR(255),
                            created_at TIMESTAMP DEFAULT NOW()
                        );
                    """)
                    
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS vnic_info (
                            id SERIAL PRIMARY KEY,
                            node_name VARCHAR(255),
                            vnic_name VARCHAR(255),
                            vnic_id VARCHAR(255),
                            vnic_type VARCHAR(50),
                            created_at TIMESTAMP DEFAULT NOW()
                        );
                    """)

                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(
                            deployment_status
                        );
                    """)

                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_nodes_created ON nodes(
                            created_at
                        );
                    """)

                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_deployment_history_node ON deployment_history(
                            node_id
                        );
                    """)
                    
                    conn.commit()
                    logger.info("Database initialized successfully")
                    
                    # Add missing columns to existing tables if needed
                    try:
                        # Add workload_vnics column to nodes table if it doesn't exist
                        cur.execute("""
                            ALTER TABLE nodes
                            ADD COLUMN IF NOT EXISTS workload_vnics JSONB
                        """)
                        
                        # Add duration column to deployment_history table if it doesn't exist
                        cur.execute("""
                            ALTER TABLE deployment_history
                            ADD COLUMN IF NOT EXISTS duration INTEGER DEFAULT 0
                        """)
                        
                        conn.commit()
                        logger.info("Database schema updated successfully")
                    except Exception as e:
                        logger.error(f"Failed to update database schema: {str(e)}")
                        conn.rollback()
        except Exception as e:
            logger.error(f"Database initialization failed: {str(e)}")
            raise
    
    def insert_node(self, node_config):
        """Insert new node configuration"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO nodes (
                            node_name, server_profile, cluster_role,
                            deployment_status, management_vnic_id, management_ip,
                            workload_vnic_id, workload_ip, workload_vnics, nutanix_config
                        ) VALUES (
                            %(node_name)s, %(server_profile)s, %(cluster_role)s,
                            %(deployment_status)s, %(management_vnic_id)s, %(management_ip)s,
                            %(workload_vnic_id)s, %(workload_ip)s, %(workload_vnics)s, %(nutanix_config)s
                        ) RETURNING id;
                    """, {
                        'node_name': node_config['node_name'],
                        'server_profile': node_config['server_profile'],
                        'cluster_role': node_config['cluster_role'],
                        'deployment_status': node_config['deployment_status'],
                        'management_vnic_id': node_config['management_vnic']['vnic_id'],
                        'management_ip': node_config['management_vnic']['ip'],
                        'workload_vnic_id': node_config['workload_vnic']['vnic_id'],
                        'workload_ip': node_config['workload_vnic']['ip'],
                        'workload_vnics': json.dumps(node_config.get('workload_vnics', {})),
                        'nutanix_config': json.dumps(node_config['nutanix_config'])
                    })
                    
                    node_id = cur.fetchone()[0]
                    conn.commit()
                    logger.info(f"Node {node_config['node_name']} inserted with ID {node_id}")
                    return node_id
        except Exception as e:
            logger.error(f"Failed to insert node: {str(e)}")
            raise
    
    def get_node(self, node_id):
        """Get node by ID"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT * FROM nodes WHERE id = %s", (node_id,))
                    node = cur.fetchone()
                    if node:
                        # Check if nutanix_config is already a dict (JSONB field) or needs to be parsed
                        if isinstance(node['nutanix_config'], str):
                            node['nutanix_config'] = json.loads(node['nutanix_config'])
                        # If it's already a dict, no need to parse it
                    return dict(node) if node else None
        except Exception as e:
            logger.error(f"Failed to get node {node_id}: {str(e)}")
            raise
    
    def get_node_by_management_ip(self, ip_address):
        """Get node by management IP"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT * FROM nodes WHERE management_ip = %s", (ip_address,))
                    node = cur.fetchone()
                    if node:
                        # Check if nutanix_config is already a dict (JSONB field) or needs to be parsed
                        if isinstance(node['nutanix_config'], str):
                            node['nutanix_config'] = json.loads(node['nutanix_config'])
                        # If it's already a dict, no need to parse it
                    return dict(node) if node else None
        except Exception as e:
            logger.error(f"Failed to get node by IP {ip_address}: {str(e)}")
            raise
    
    def delete_node(self, node_id):
        """Delete a node from the database"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Delete related records first (foreign key constraints)
                    cur.execute("DELETE FROM deployment_history WHERE node_id = %s", (node_id,))
                    cur.execute("DELETE FROM ip_reservations WHERE node_name = (SELECT node_name FROM nodes WHERE id = %s)", (node_id,))
                    cur.execute("DELETE FROM dns_records WHERE node_name = (SELECT node_name FROM nodes WHERE id = %s)", (node_id,))
                    cur.execute("DELETE FROM vnic_info WHERE node_name = (SELECT node_name FROM nodes WHERE id = %s)", (node_id,))
                    
                    # Delete the node itself
                    cur.execute("DELETE FROM nodes WHERE id = %s", (node_id,))
                    
                    conn.commit()
                    logger.info(f"Node {node_id} deleted from database")
        except Exception as e:
            logger.error(f"Failed to delete node {node_id}: {str(e)}")
            raise
    
    def get_node_by_name(self, node_name):
        """Get node by name"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, node_name, bare_metal_id, management_ip, workload_ip,
                               management_vnic_id, workload_vnic_id, workload_vnics, deployment_status, nutanix_config
                        FROM nodes WHERE node_name = %s
                    """, (node_name,))
                    
                    row = cur.fetchone()
                    if row:
                        # Check if nutanix_config is already a dict (JSONB field) or needs to be parsed
                        if isinstance(row.get('nutanix_config'), str):
                            row['nutanix_config'] = json.loads(row['nutanix_config'])
                        # If it's already a dict, no need to parse it
                        return dict(row)
                    return None
        except Exception as e:
            logger.error(f"Error getting node by name {node_name}: {str(e)}")
            raise
    
    def update_node_status(self, node_id, status):
        """Update node deployment status"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE nodes 
                        SET deployment_status = %s, updated_at = NOW() 
                        WHERE id = %s
                    """, (status, node_id))
                    conn.commit()
                    logger.info(f"Node {node_id} status updated to {status}")
        except Exception as e:
            logger.error(f"Failed to update node status: {str(e)}")
            raise
    
    def update_node_deployment_info(self, node_id, bare_metal_id, status):
        """Update node with bare metal deployment info"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE nodes 
                        SET bare_metal_id = %s, deployment_status = %s, updated_at = NOW()
                        WHERE id = %s
                    """, (bare_metal_id, status, node_id))
                    conn.commit()
                    logger.info(f"Node {node_id} deployment info updated")
        except Exception as e:
            logger.error(f"Failed to update deployment info: {str(e)}")
            raise
    
    def log_deployment_event(self, node_id, phase, status, message):
        """Log deployment event"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO deployment_history (node_id, phase, status, message)
                        VALUES (%s, %s, %s, %s)
                    """, (node_id, phase, status, message))
                    conn.commit()
        except Exception as e:
            logger.error(f"Failed to log deployment event: {str(e)}")
    
    def get_deployment_history(self, node_id):
        """Get deployment history for a node"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM deployment_history 
                        WHERE node_id = %s 
                        ORDER BY timestamp ASC
                    """, (node_id,))
                    return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get deployment history: {str(e)}")
            return []
    
    def get_latest_deployment_status(self, node_id):
        """Get latest deployment status for a node"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM deployment_history 
                        WHERE node_id = %s 
                        ORDER BY timestamp DESC 
                        LIMIT 1
                    """, (node_id,))
                    result = cur.fetchone()
                    return dict(result) if result else None
        except Exception as e:
            logger.error(f"Failed to get latest status: {str(e)}")
            return None
    
    def store_ip_reservations(self, node_name, ip_allocation):
        """Store IP reservations for a node"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    for ip_type, ip_info in ip_allocation.items():
                        if ip_info:  # Some IPs might be None (like cluster_ip for non-first nodes)
                            cur.execute("""
                                INSERT INTO ip_reservations 
                                (node_name, ip_address, ip_type, reservation_id, subnet_id)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (
                                node_name,
                                ip_info['ip_address'],
                                ip_type,
                                ip_info['reservation_id'],
                                ip_info.get('subnet_id', '')
                            ))
                    conn.commit()
                    logger.info(f"IP reservations stored for {node_name}")
        except Exception as e:
            logger.error(f"Failed to store IP reservations: {str(e)}")
            raise
    
    def store_dns_records(self, node_name, dns_records):
        """Store DNS records for a node"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    for record in dns_records:
                        cur.execute("""
                            INSERT INTO dns_records 
                            (node_name, record_name, record_type, rdata, record_id)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            node_name,
                            record['name'],
                            record['type'],
                            record['rdata'],
                            record['id']
                        ))
                    conn.commit()
                    logger.info(f"DNS records stored for {node_name}")
        except Exception as e:
            logger.error(f"Failed to store DNS records: {str(e)}")
            raise
    
    def store_vnic_info(self, node_name, vnics):
        """Store vNIC information for a node"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    for vnic_type, vnic_info in vnics.items():
                        # Handle both individual VNI dictionaries and lists of VNI dictionaries
                        if isinstance(vnic_info, list):
                            # Handle list of VNIs
                            for i, vni in enumerate(vnic_info):
                                if vni and isinstance(vni, dict):
                                    cur.execute("""
                                        INSERT INTO vnic_info
                                        (node_name, vnic_name, vnic_id, vnic_type)
                                        VALUES (%s, %s, %s, %s)
                                    """, (
                                        node_name,
                                        vni.get('name', f'{vnic_type}_{i}'),
                                        vni.get('id', ''),
                                        f'{vnic_type}_{i}'
                                    ))
                        elif vnic_info and isinstance(vnic_info, dict):
                            # Handle individual VNI dictionary
                            cur.execute("""
                                INSERT INTO vnic_info
                                (node_name, vnic_name, vnic_id, vnic_type)
                                VALUES (%s, %s, %s, %s)
                            """, (
                                node_name,
                                vnic_info.get('name', vnic_type),
                                vnic_info.get('id', ''),
                                vnic_type
                            ))
                    conn.commit()
                    logger.info(f"vNIC info stored for {node_name}")
        except Exception as e:
            logger.error(f"Failed to store vNIC info: {str(e)}")
            raise
    
    def register_cluster(self, cluster_config):
        """Register a new cluster"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO clusters 
                        (cluster_name, cluster_ip, cluster_dns, created_by_node, node_count, status)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        cluster_config['cluster_name'],
                        cluster_config['cluster_ip'],
                        cluster_config['cluster_dns'],
                        cluster_config['created_by_node'],
                        cluster_config['node_count'],
                        cluster_config['status']
                    ))
                    cluster_id = cur.fetchone()[0]
                    conn.commit()
                    logger.info(f"Cluster {cluster_config['cluster_name']} registered with ID {cluster_id}")
                    return cluster_id
        except Exception as e:
            logger.error(f"Failed to register cluster: {str(e)}")
            raise
    
    def update_node_with_cluster_info(self, node_id, cluster_id, cluster_config):
        """Update node with cluster information"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE nodes
                        SET cluster_name = %s, deployment_status = %s, updated_at = NOW()
                        WHERE id = %s
                    """, (
                        cluster_config['cluster_name'],
                        'cluster_assigned',
                        node_id
                    ))
                    conn.commit()
                    logger.info(f"Node {node_id} updated with cluster {cluster_config['cluster_name']}")
        except Exception as e:
            logger.error(f"Failed to update node {node_id} with cluster info: {str(e)}")
            raise
    
    def get_cluster_by_ip(self, cluster_ip):
        """Get cluster by IP address"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT * FROM clusters WHERE cluster_ip = %s", (cluster_ip,))
                    result = cur.fetchone()
                    return dict(result) if result else None
        except Exception as e:
            logger.error(f"Failed to get cluster by IP: {str(e)}")
            return None
    
    def get_nodes_with_status(self, status):
        """Get all nodes with a specific status"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT * FROM nodes WHERE deployment_status = %s", (status,))
                    return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get nodes with status {status}: {str(e)}")
            return []
    
    def is_first_node(self):
        """Check if this is the first node (no existing deployed nodes)"""
        try:
            deployed_nodes = self.get_nodes_with_status('deployed')
            return len(deployed_nodes) == 0
        except Exception as e:
            logger.error(f"Failed to check if first node: {str(e)}")
            return True  # Assume first node on error
    
    def get_cluster_info(self):
        """Get existing cluster information"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT * FROM clusters WHERE status = 'active' LIMIT 1")
                    result = cur.fetchone()
                    return dict(result) if result else None
        except Exception as e:
            logger.error(f"Failed to get cluster info: {str(e)}")
            return None
    
    def get_cluster_by_id(self, cluster_id):
        """Get cluster by ID"""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT * FROM clusters WHERE id = %s", (cluster_id,))
                    result = cur.fetchone()
                    return dict(result) if result else None
        except Exception as e:
            logger.error(f"Failed to get cluster {cluster_id}: {str(e)}")
            return None