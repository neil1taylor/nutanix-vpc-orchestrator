# Cleanup Service Documentation

The Cleanup Service provides comprehensive resource cleanup for failed or completed Nutanix deployments on IBM Cloud VPC. It handles the cleanup of bare metal servers, virtual network interfaces, DNS records, IP reservations, and database records.

## Overview

The cleanup system consists of several components:

- **CleanupService** (`cleanup_service.py`) - Core cleanup logic
- **API Endpoints** - REST API for cleanup operations
- **Helper Script** (`scripts/cleanup-helper.sh`) - Command-line interface
- **Integration** - Built into NodeProvisioner for automatic cleanup

## How Resource Tracking Works

### Database-Driven Resource Management

The cleanup system uses **database tracking** rather than maintaining lists of IDs in memory. This approach provides persistence, reliability, and the ability to clean up resources even after server restarts or crashes.

### 1. During Provisioning - Resource ID Storage

When a node is provisioned, **each resource creation step stores tracking information in the database**:

```python
# IP Reservations
ip_allocation = self.ibm_cloud.create_subnet_reserved_ip(...)
self.db.store_ip_reservations(node_config['node_name'], ip_allocation)

# DNS Records
dns_records = self.ibm_cloud.create_dns_record(...)
self.db.store_dns_records(node_config['node_name'], dns_records)

# Virtual Network Interfaces
vnis = self.ibm_cloud.create_virtual_network_interface(...)
self.db.store_vni_info(node_config['node_name'], vnis)

# Bare Metal Server ID stored in main nodes table
self.db.update_node_deployment_info(node_id, bare_metal_id, status)
```

### 2. Database Tables for Resource Tracking

The system creates specific database tables to track all created resources:

```sql
-- IP reservations tracking
CREATE TABLE ip_reservations (
    id SERIAL PRIMARY KEY,
    node_name VARCHAR(255),
    ip_address INET,
    ip_type VARCHAR(50),           -- 'management', 'ahv', 'cvm', 'workload', 'cluster'
    reservation_id VARCHAR(255),   -- IBM Cloud reservation ID for deletion
    subnet_id VARCHAR(255),        -- Which subnet it belongs to
    created_at TIMESTAMP DEFAULT NOW()
);

-- DNS records tracking  
CREATE TABLE dns_records (
    id SERIAL PRIMARY KEY,
    node_name VARCHAR(255),
    record_name VARCHAR(255),      -- 'node01-mgmt', 'node01-ahv', etc.
    record_type VARCHAR(10),       -- 'A', 'CNAME', etc.
    rdata VARCHAR(255),           -- IP address or target
    record_id VARCHAR(255),       -- IBM Cloud DNS record ID for deletion
    created_at TIMESTAMP DEFAULT NOW()
);

-- VNI tracking
CREATE TABLE vnic_info (
    id SERIAL PRIMARY KEY,
    node_name VARCHAR(255),
    vnic_name VARCHAR(255),       -- 'node01-mgmt-vni', 'node01-workload-vni'
    vnic_id VARCHAR(255),         -- IBM Cloud VNI ID for deletion
    vnic_type VARCHAR(50),        -- 'management_vni', 'workload_vni'
    created_at TIMESTAMP DEFAULT NOW()
);

-- Main nodes table also stores key resource IDs
CREATE TABLE nodes (
    id SERIAL PRIMARY KEY,
    node_name VARCHAR(255),
    bare_metal_id VARCHAR(255),   -- IBM Cloud bare metal server ID
    management_vnic_id VARCHAR(255),
    workload_vnic_id VARCHAR(255),
    -- ... other fields
);
```

### 3. During Cleanup - Database Retrieval and Deletion

When cleanup is triggered, the system **queries the database** to find all resources and their IBM Cloud IDs:

```python
def cleanup_failed_provisioning(self, node_name: str):
    # 1. Get main node info with bare metal server ID
    node = self.get_node_by_name(node_name)
    
    # 2. Query database for all related resources
    vni_info = self.get_vni_info_by_node(node_name)
    dns_records = self.get_dns_records_by_node(node_name) 
    ip_reservations = self.get_ip_reservations_by_node(node_name)
    
    # 3. Clean up each resource using stored IBM Cloud IDs
    for vni in vni_info:
        self.ibm_cloud.delete_virtual_network_interface(vni['vnic_id'])
    
    for record in dns_records:
        self.ibm_cloud.delete_dns_record(record['record_id'])
    
    for reservation in ip_reservations:
        subnet_id = self.determine_subnet_from_type(reservation['ip_type'])
        self.ibm_cloud.delete_subnet_reserved_ip(subnet_id, reservation['reservation_id'])
    
    # 4. Delete bare metal server (automatically cleans up attached VNIs)
    if node.get('bare_metal_id'):
        self.ibm_cloud.delete_bare_metal_server(node['bare_metal_id'])
```

### 4. Resource Tracking Flow

**Provisioning Phase:**
```
1. Create IP Reservation → Get reservation_id → Store in ip_reservations table
2. Create DNS Record → Get record_id → Store in dns_records table  
3. Create VNI → Get vnic_id → Store in vnic_info table
4. Create Bare Metal → Get server_id → Store in nodes.bare_metal_id
5. If ANY step fails → Automatic cleanup of previous steps using stored IDs
```

**Cleanup Phase:**
```
1. Query: "SELECT * FROM ip_reservations WHERE node_name = ?"
2. Query: "SELECT * FROM dns_records WHERE node_name = ?"
3. Query: "SELECT * FROM vnic_info WHERE node_name = ?"
4. Query: "SELECT bare_metal_id FROM nodes WHERE node_name = ?"
5. Use retrieved IDs to call IBM Cloud delete APIs
6. Update database: Mark node as 'cleanup_completed'
```

### 5. Partial Cleanup Handling

The system handles **partial failures during provisioning** by cleaning up already-created resources:

```python
def reserve_node_ips(self, node_config):
    ip_allocation = {}
    try:
        # Reserve management IP
        ip_allocation['management'] = self.ibm_cloud.create_subnet_reserved_ip(...)
        
        # Reserve AHV IP  
        ip_allocation['ahv'] = self.ibm_cloud.create_subnet_reserved_ip(...)
        
        # If this fails, we need to clean up the previous ones
        ip_allocation['cvm'] = self.ibm_cloud.create_subnet_reserved_ip(...)
        
    except Exception as e:
        # Clean up any successful reservations before re-raising
        self._cleanup_partial_ip_allocation(ip_allocation)
        raise Exception(f"IP reservation failed: {str(e)}")

def _cleanup_partial_ip_allocation(self, ip_allocation):
    """Clean up partially allocated IPs when reservation fails"""
    for ip_type, ip_info in ip_allocation.items():
        if ip_info:  # Only clean up successful allocations
            try:
                subnet_id = self.determine_subnet(ip_type)
                self.ibm_cloud.delete_subnet_reserved_ip(subnet_id, ip_info['reservation_id'])
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup IP: {str(cleanup_error)}")
```

### 6. Advantages of Database Tracking

✅ **Persistent**: Survives server restarts and failures  
✅ **Reliable**: Database transactions ensure consistency  
✅ **Queryable**: Can find resources by node, deployment, age, etc.  
✅ **Auditable**: Complete history of what was created and cleaned up  
✅ **Recoverable**: Can clean up resources even if original process failed  
✅ **Scalable**: No memory limitations for tracking large numbers of resources  

### 7. Database Query Examples

Here's how the cleanup service retrieves resource IDs for deletion:

```python
def get_vni_info_by_node(self, node_name: str) -> List[Dict]:
    """Get VNI information for a node"""
    with self.db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT vnic_name, vnic_id, vnic_type
                FROM vnic_info WHERE node_name = %s
            """, (node_name,))
            
            return [
                {
                    'vnic_name': row[0],
                    'vnic_id': row[1],      # IBM Cloud VNI ID for deletion
                    'vnic_type': row[2]
                }
                for row in cur.fetchall()
            ]

def get_dns_records_by_node(self, node_name: str) -> List[Dict]:
    """Get DNS records for a node"""
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
                    'record_id': row[3]    # IBM Cloud DNS record ID for deletion
                }
                for row in cur.fetchall()
            ]
```

## Key Features

- **Comprehensive Resource Cleanup**: Handles all IBM Cloud VPC resources
- **Automatic Error Recovery**: Triggered automatically on provisioning failures
- **Manual Cleanup Options**: API and CLI for manual operations
- **Batch Operations**: Clean up multiple nodes or deployments at once
- **Validation**: Verify cleanup completion
- **Script Generation**: Create cleanup scripts for manual execution
- **Orphaned Resource Cleanup**: Clean up resources from old failed deployments

## Quick Start

### Using the Helper Script

The easiest way to perform cleanup operations is using the helper script:

```bash
# Make the script executable
chmod +x /opt/nutanix-pxe/scripts/cleanup-helper.sh

# Show overall cleanup status
./scripts/cleanup-helper.sh status

# Clean up a specific node
./scripts/cleanup-helper.sh cleanup-node 1

# Clean up a deployment
./scripts/cleanup-helper.sh cleanup-deployment nutanix-poc-bm-node-01

# Validate cleanup completion
./scripts/cleanup-helper.sh validate 1

# Interactive menu
./scripts/cleanup-helper.sh interactive
```

### Using the API

Direct API calls for integration with other systems:

```bash
# Clean up a node
curl -X POST http://localhost:8080/api/cleanup/node/1

# Clean up a deployment
curl -X POST http://localhost:8080/api/cleanup/deployment/deployment-123

# Get cleanup status
curl http://localhost:8080/api/cleanup/status

# Generate cleanup script
curl http://localhost:8080/api/cleanup/script/deployment-123 > cleanup.sh
```

## Detailed Usage

### 1. Automatic Cleanup (Recommended)

The system automatically triggers cleanup when provisioning fails:

```python
# This happens automatically in NodeProvisioner
try:
    result = node_provisioner.provision_node(node_config)
except Exception as e:
    # Cleanup is automatically triggered
    logger.error(f"Provisioning failed, cleanup initiated: {str(e)}")
```

### 2. Manual Node Cleanup

Clean up resources for a specific node:

```bash
# Using helper script
./cleanup-helper.sh cleanup-node 1

# Using API
curl -X POST http://localhost:8080/api/cleanup/node/1 | jq '.'
```

**Response Example:**
```json
{
  "message": "Cleanup completed successfully for node 1",
  "node_name": "nutanix-poc-bm-node-01",
  "summary": {
    "total_operations": 12,
    "successful_operations": 11,
    "success_rate": "91.7%"
  },
  "details": [
    {
      "resource_type": "bare_metal_server",
      "operations": [
        {
          "type": "bare_metal_server_deletion",
          "success": true,
          "message": "Deleted bare metal server server-123"
        }
      ]
    }
  ]
}
```

### 3. Deployment Cleanup

Clean up all resources for an entire deployment:

```bash
# Using helper script
./cleanup-helper.sh cleanup-deployment deployment-123

# Using API
curl -X POST http://localhost:8080/api/cleanup/deployment/deployment-123
```

### 4. Cleanup Status and Monitoring

Check cleanup status:

```bash
# Overall status
./cleanup-helper.sh status

# Specific node status
./cleanup-helper.sh status-node nutanix-poc-bm-node-01

# Specific deployment status
./cleanup-helper.sh status-deployment deployment-123
```

**Status Response Example:**
```json
{
  "overall_status": {
    "deployed": 2,
    "failed": 1,
    "cleanup_completed": 3
  },
  "cleanup_needed": 1,
  "cleanup_completed": 3
}
```

### 5. Cleanup Validation

Verify that cleanup was completed successfully:

```bash
# Using helper script
./cleanup-helper.sh validate 1

# Using API
curl http://localhost:8080/api/cleanup/validate/1
```

**Validation Response Example:**
```json
{
  "node_name": "nutanix-poc-bm-node-01",
  "cleanup_complete": true,
  "validation_results": [
    {
      "check": "bare_metal_server",
      "status": "PASS",
      "message": "Bare metal server not found (successfully deleted)"
    },
    {
      "check": "dns_records",
      "status": "PASS", 
      "message": "All DNS records successfully deleted"
    },
    {
      "check": "ip_reservations",
      "status": "PASS",
      "message": "All IP reservations successfully deleted"
    }
  ]
}
```

### 6. Orphaned Resource Cleanup

Clean up resources from old failed deployments:

```bash
# Clean up resources older than 24 hours (default)
./cleanup-helper.sh cleanup-orphaned

# Clean up resources older than 48 hours
./cleanup-helper.sh cleanup-orphaned 48

# Using API
curl -X POST http://localhost:8080/api/cleanup/orphaned \
  -H "Content-Type: application/json" \
  -d '{"max_age_hours": 48}'
```

### 7. Batch Operations

Perform cleanup operations on multiple resources:

```bash
# Batch cleanup multiple nodes
./cleanup-helper.sh batch-nodes node1,node2,node3

# Batch validate multiple nodes
./cleanup-helper.sh batch-validate node1,node2,node3

# Using API
curl -X POST http://localhost:8080/api/cleanup/batch \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "cleanup_nodes",
    "targets": ["node1", "node2", "node3"]
  }'
```

### 8. Manual Cleanup Scripts

Generate cleanup scripts for manual execution:

```bash
# Generate script
./cleanup-helper.sh script deployment-123

# Execute generated script
chmod +x cleanup-deployment-123.sh
./cleanup-deployment-123.sh
```

**Generated Script Example:**
```bash
#!/bin/bash
# Cleanup script for deployment deployment-123
# Generated on 2025-08-02T10:30:00

# Delete bare metal server
if ibmcloud is bare-metal-server server-123 >/dev/null 2>&1; then
    ibmcloud is bare-metal-server-delete server-123 --force
    echo "✓ Deleted bare metal server server-123"
fi

# Delete DNS records
DNS_RECORDS=$(ibmcloud dns resource-records --instance $DNS_INSTANCE_ID --zone $DNS_ZONE_ID --output json | jq -r '.[] | select(.name | contains("node1")) | .id')
for record_id in $DNS_RECORDS; do
    ibmcloud dns resource-record-delete $DNS_INSTANCE_ID $DNS_ZONE_ID $record_id --force
    echo "✓ Deleted DNS record $record_id"
done
```

## API Reference

### Cleanup Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/cleanup/node/<id>` | POST | Clean up specific node |
| `/api/cleanup/deployment/<id>` | POST | Clean up deployment |
| `/api/cleanup/status` | GET | Get cleanup status |
| `/api/cleanup/validate/<id>` | GET | Validate cleanup |
| `/api/cleanup/script/<id>` | GET | Generate cleanup script |
| `/api/cleanup/orphaned` | POST | Clean up orphaned resources |
| `/api/cleanup/batch` | POST | Batch cleanup operations |

### Status Codes

- **200**: Success
- **207**: Multi-Status (partial success)
- **404**: Resource not found
- **500**: Internal server error

## Integration with NodeProvisioner

The cleanup service is automatically integrated with the NodeProvisioner:

```python
class NodeProvisioner:
    def __init__(self):
        # Cleanup service is automatically imported
        from cleanup_service import CleanupService
        self.cleanup_service = CleanupService()
    
    def provision_node(self, node_request):
        try:
            # Provisioning logic...
            pass
        except Exception as e:
            # Automatic cleanup on failure
            cleanup_result = self.cleanup_service.cleanup_failed_provisioning(node_name)
            logger.info(f"Cleanup result: {cleanup_result}")
            raise
```

## Configuration

The cleanup service uses the same configuration as the main application:

```python
# Required configuration in Config class
IBM_CLOUD_REGION = "us-south"
VPC_ID = "vpc-12345"
DNS_INSTANCE_ID = "instance-12345"
DNS_ZONE_ID = "zone-12345"
MANAGEMENT_SUBNET_ID = "subnet-mgmt-12345"
WORKLOAD_SUBNET_ID = "subnet-workload-12345"
```

## Error Handling

The cleanup service includes comprehensive error handling:

1. **Partial Cleanup**: If some operations fail, successful operations are reported
2. **Retry Logic**: Automatic retries for transient failures
3. **Validation**: Post-cleanup validation to ensure completion
4. **Logging**: Detailed logging of all operations
5. **Fallback**: Manual cleanup script generation if automated cleanup fails

## Monitoring and Logging

All cleanup operations are logged with details:

```bash
# View cleanup logs
journalctl -u nutanix-pxe | grep -i cleanup

# View specific cleanup events
tail -f /var/log/nutanix-pxe/pxe-server.log | grep -i cleanup
```

## Troubleshooting

### Common Issues

1. **Cleanup Fails with 403 Errors**
   - Check IBM Cloud IAM permissions
   - Verify trusted profile authentication

2. **Resources Not Found**
   - Resources may have been manually deleted
   - Check IBM Cloud console for actual resource state

3. **Database Connection Errors**
   - Verify PostgreSQL is running
   - Check database connection string

4. **Network Timeouts**
   - Increase timeout values in configuration
   - Check network connectivity to IBM Cloud APIs

### Manual Verification

If automatic validation fails, manually verify cleanup:

```bash
# Check bare metal servers
ibmcloud is bare-metal-servers

# Check virtual network interfaces
ibmcloud is virtual-network-interfaces

# Check DNS records
ibmcloud dns resource-records --instance $DNS_INSTANCE_ID --zone $DNS_ZONE_ID

# Check IP reservations
ibmcloud is subnet-reserved-ips $SUBNET_ID
```

### Recovery Procedures

1. **Re-run Cleanup**
   ```bash
   ./cleanup-helper.sh cleanup-node 1
   ```

2. **Generate Manual Script**
   ```bash
   ./cleanup-helper.sh script deployment-123
   chmod +x cleanup-deployment-123.sh
   ./cleanup-deployment-123.sh
   ```

3. **Contact Support**
   - If cleanup continues to fail, manual intervention may be required
   - Use the validation endpoint to identify remaining resources

## Best Practices

1. **Always Validate**: Run validation after cleanup operations
2. **Monitor Logs**: Check logs for any errors or warnings
3. **Test Cleanup**: Test cleanup procedures in development environment
4. **Regular Maintenance**: Periodically run orphaned resource cleanup
5. **Manual Verification**: Verify critical resources in IBM Cloud console

## Security Considerations

- Cleanup operations require appropriate IBM Cloud IAM permissions
- Scripts contain sensitive configuration information
- Database access is required for cleanup operations
- Network access to IBM Cloud APIs is required

This cleanup system provides comprehensive resource management for Nutanix deployments, ensuring that failed provisioning attempts don't leave orphaned resources in your IBM Cloud VPC environment.