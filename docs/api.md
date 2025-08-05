# Nutanix PXE/Config Server API Documentation

This document provides comprehensive documentation for the Nutanix PXE/Config Server API endpoints, their purposes, and the proper execution order for automated Nutanix CE provisioning on IBM Cloud VPC.

## API Overview

The server provides five main service categories:
- **Boot Services** (`/boot/*`) - iPXE boot handling and file serving
- **Configuration API** (`/api/config/*`) - Node provisioning and management
- **Status Monitoring** (`/api/status/*`) - Deployment progress tracking
- **DNS Management** (`/api/dns/*`) - DNS record management
- **Cleanup Services** (`/api/cleanup/*`) - Resource cleanup

## 1. Boot Services (`/boot/*`)

These endpoints handle the iPXE boot process and serve boot-related files.

### 1.1 Boot Configuration
**Endpoint:** `GET /boot/ipxe`
**Purpose:** Handle iPXE boot configuration requests from provisioned servers
**Usage:** Called automatically by iPXE during server boot

**Parameters:**
- `mgmt_ip` - Management IP address of the booting server

**Returns:** iPXE boot script in plain text format

**Example:**
```bash
curl "http://localhost:8080/boot/ipxe?mgmt_ip=10.240.0.10"
```

### 1.2 Boot Images
**Endpoint:** `GET /boot/images/<filename>`
**Purpose:** Serve boot images (kernel, initrd, ISO files)
**Allowed Files:**
- `vmlinuz-foundation` - Foundation kernel
- `initrd-foundation.img` - Foundation initial ramdisk
- `nutanix-ce-installer.iso` - Nutanix CE installer ISO

**Example:**
```bash
curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/images/vmlinuz-foundation"
```

### 1.3 Boot Scripts
**Endpoint:** `GET /boot/scripts/<script_name>`
**Purpose:** Serve boot scripts and configuration files
**Allowed Scripts:**
- `foundation-init.sh` - Foundation initialization script
- `network-config.sh` - Network configuration script
- `post-install.sh` - Post-installation script

## 2. Configuration API (`/api/config/*`)

These endpoints handle node provisioning and configuration management.

### 2.1 Provision Node
**Endpoint:** `POST /api/config/nodes`
**Purpose:** Provision a new Nutanix node
**Usage:** Primary endpoint for creating new cluster nodes

**Request Body:**
```json
{
  "node_config": {
    "node_name": "nutanix-poc-bm-node-01",
    "server_profile": "bx2d-metal-48x192",
    "cluster_role": "compute",
    "storage_config": {
      "data_drives": ["nvme2n1", "nvme3n1", "nvme4n1", "nvme5n1"]
    }
  },
  "network_config": {
    "management_subnet": "auto",
    "workload_subnets": ["auto"],
    "cluster_operation": "create_new"
  },
  "cluster_config": {
    "cluster_type": "single_node"
  }
}
```

**Additional Parameters:**
- `cluster_config.cluster_type` (optional): Specify cluster type
  - `"multi_node"` (default): Standard multi-node cluster (3+ nodes)
  - `"single_node"`: Single node cluster requiring manual creation
- `network_config.workload_subnets` (optional): Specify workload subnets
  - Array of subnet IDs or "auto" for automatic selection
  - Default: `["auto"]` (single workload subnet)
  - Multiple subnets can be specified for multi-homed configurations

**Response:**
```json
{
  "message": "Node provisioning initiated successfully",
  "node_id": 1,
  "deployment_id": "bare-metal-server-id",
  "estimated_completion": "2025-08-01T14:30:00",
  "monitoring_endpoint": "/api/status/nodes/1"
}
```

**Examples:**

Create First Node (Multi-Node Cluster - Default):
```bash
curl -X POST http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/nodes \
  -H "Content-Type: application/json" \
  -d '{
    "node_config": {
      "node_name": "nutanix-poc-bm-node-01",
      "server_profile": "bx2d-metal-48x192",
      "cluster_role": "compute",
      "storage_config": {
        "data_drives": ["nvme2n1", "nvme3n1", "nvme4n1", "nvme5n1"]
      }
    },
    "network_config": {
      "management_subnet": "auto",
      "workload_subnets": ["auto"],
      "cluster_operation": "create_new"
    }
  }'
```

Create First Node (Single Node Cluster):
```bash
curl -X POST http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/nodes \
  -H "Content-Type: application/json" \
  -d '{
    "node_config": {
      "node_name": "nutanix-poc-bm-node-01",
      "server_profile": "bx2d-metal-48x192",
      "cluster_role": "compute",
      "storage_config": {
        "data_drives": ["nvme2n1", "nvme3n1", "nvme4n1", "nvme5n1"]
      }
    },
    "network_config": {
      "management_subnet": "auto",
      "workload_subnets": ["auto"],
      "cluster_operation": "create_new"
    },
    "cluster_config": {
      "cluster_type": "single_node"
    }
  }'
```

Add Node to Existing Cluster:
```bash
curl -X POST http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/nodes \
  -H "Content-Type: application/json" \
  -d '{
    "node_config": {
      "node_name": "nutanix-poc-bm-node-02",
      "server_profile": "bx2d-metal-48x192",
      "cluster_role": "compute"
    },
    "network_config": {
      "cluster_operation": "join_existing"
    }
  }'
```

### 2.2 Get Node Information
**Endpoint:** `GET /api/config/nodes/<node_id>`
**Purpose:** Retrieve detailed information about a specific node

**Example:**
```bash
curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/nodes/1"
```

### 2.3 List All Nodes
**Endpoint:** `GET /api/config/nodes`
**Purpose:** List all provisioned nodes

**Example:**
```bash
curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/nodes"
```

## 3. Status Monitoring (`/api/status/*`)

These endpoints provide deployment progress tracking and monitoring.

### 3.1 Node Status

## 4. Cluster Management API (`/api/config/clusters`)

These endpoints handle cluster creation and configuration after node deployment.

### 4.1 Create Cluster
**Endpoint:** `POST /api/config/clusters`
**Purpose:** Create a new Nutanix cluster from deployed nodes
**Usage:** Create either single node or multi-node clusters after nodes are deployed

**Request Body:**
```json
{
  "cluster_config": {
    "cluster_operation": "create_new",
    "cluster_name": "my-cluster",
    "cluster_type": "single_node",
    "nodes": ["nutanix-poc-bm-node-01"]
  }
}
```

**Response:**
```json
{
  "message": "Cluster creation initiated successfully",
  "cluster_id": 1,
  "cluster_name": "my-cluster",
  "cluster_ip": "10.240.0.200",
  "status": "creating",
  "message": "Single node cluster registered. Use cluster manager to create the cluster."
}
```

**Examples:**

Create Single Node Cluster:
```bash
curl -X POST http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/clusters \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_config": {
      "cluster_operation": "create_new",
      "cluster_name": "single-node-cluster",
      "cluster_type": "single_node",
      "nodes": ["nutanix-poc-bm-node-01"]
    }
  }'
```

Create Multi-Node Cluster:
```bash
curl -X POST http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/clusters \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_config": {
      "cluster_operation": "create_new",
      "cluster_name": "multi-node-cluster",
      "cluster_type": "multi_node",
      "nodes": ["nutanix-poc-bm-node-01", "nutanix-poc-bm-node-02", "nutanix-poc-bm-node-03"]
    }
  }'
```

### 4.2 Get Cluster Information
**Endpoint:** `GET /api/config/clusters/<cluster_id>`
**Purpose:** Retrieve detailed information about a specific cluster

**Example:**
```bash
curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/clusters/1"
```

### 4.3 List All Clusters
**Endpoint:** `GET /api/config/clusters`
**Purpose:** List all provisioned clusters

**Example:**
```bash
curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/clusters"
```

### 4.4 Delete Cluster Information
**Endpoint:** `DELETE /api/config/clusters/<cluster_id>`
**Purpose:** Delete cluster information from database (does not delete actual cluster)

**Example:**
```bash
curl -X DELETE "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/config/clusters/1"
```
**Endpoint:** `GET /api/status/nodes/<node_id>`
**Purpose:** Get deployment status for a specific node
**Usage:** Monitor deployment progress by node ID

**Response:**
```json
{
  "server_ip": "10.240.0.10",
  "server_name": "nutanix-poc-bm-node-01",
  "node_id": 1,
  "deployment_id": "bare-metal-server-id",
  "current_phase": "installation",
  "phase_status": "in_progress",
  "progress_percent": 65,
  "elapsed_time_seconds": 900,
  "estimated_remaining_seconds": 600,
  "timed_out": false,
  "last_update": "2025-08-01T12:15:30",
  "message": "Installing Nutanix CE software"
}
```

**Example:**
```bash
curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/status/nodes/1"
```

### 3.2 Deployment Status by IP
**Endpoint:** `GET /api/status/deployment/<server_ip>`
**Purpose:** Get deployment status by server IP (legacy endpoint)

**Example:**
```bash
curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/status/deployment/10.240.0.10"
```

### 3.3 Phase Update
**Endpoint:** `POST /api/status/phase`
**Purpose:** Receive phase updates from deploying servers
**Usage:** Called by deploying servers to report progress

**Request Body:**
```json
{
  "server_ip": "10.240.0.10",
  "phase": "installation",
  "status": "success",
  "message": "Nutanix CE installation completed"
}
```

### 3.4 Deployment History
**Endpoint:** `GET /api/status/history/<node_id>`
**Purpose:** Get complete deployment history for a node

**Example:**
```bash
curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/status/history/1"
```

### 3.5 Deployment Summary
**Endpoint:** `GET /api/status/summary`
**Purpose:** Get overall deployment summary across all nodes

**Example:**
```bash
curl "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/status/summary"
```

## 4. DNS Management (`/api/dns/*`)

These endpoints manage DNS record creation and deletion.

### 4.1 Create DNS Record
**Endpoint:** `POST /api/dns/records`
**Purpose:** Create a DNS record

**Request Body:**
```json
{
  "record_type": "A",
  "name": "node01-mgmt",
  "rdata": "10.240.0.10"
}
```

### 4.2 Delete DNS Record
**Endpoint:** `DELETE /api/dns/records/<record_name>`
**Purpose:** Delete a DNS record

## 5. Cleanup Services (`/api/cleanup/*`)

These endpoints handle resource cleanup for failed or completed deployments.

### 5.1 Node Cleanup
**Endpoint:** `POST /api/cleanup/node/<node_id>`
**Purpose:** Clean up all resources for a specific node

### 5.2 Deployment Cleanup
**Endpoint:** `POST /api/cleanup/deployment/<deployment_id>`
**Purpose:** Clean up all resources for an entire deployment

### 5.3 Generate Cleanup Script
**Endpoint:** `GET /api/cleanup/script/<deployment_id>`
**Purpose:** Generate shell script for manual cleanup

## 6. Health and Information

### 6.1 Health Check
**Endpoint:** `GET /health`
**Purpose:** Basic health check endpoint
**Usage:** Monitoring and load balancer health checks

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-08-01T12:00:00",
  "version": "1.0.0"
}
```

### 6.2 Server Information
**Endpoint:** `GET /api/info`
**Purpose:** Get PXE server information and available endpoints

## Deployment Flow and API Call Order

### Phase 1: Initial Provisioning (Human/API Initiated)

1. **Provision First Node (Create Cluster)**
   ```bash
   POST /api/config/nodes
   # Creates cluster, reserves IPs, creates VNIs, deploys bare metal
   ```

2. **Monitor Deployment Progress**
   ```bash
   GET /api/status/nodes/{node_id}
   # Poll this endpoint to track deployment progress
   ```

### Phase 2: Automated Boot Process (Server Initiated)

3. **iPXE Boot Request** (Server calls automatically)
   ```bash
   GET /boot/config?mgmt_ip=X.X.X.X&mgmt_mac=XX:XX:XX:XX:XX:XX
   # Server requests iPXE boot script
   ```

4. **Download Boot Images** (iPXE calls automatically)
   ```bash
   GET /boot/images/vmlinuz-foundation
   GET /boot/images/initrd-foundation.img
   # iPXE downloads kernel and initrd
   ```

5. **Get Server Configuration** (Boot scripts call automatically)
   ```bash
   GET /boot/server/{server_ip}
   # Foundation requests detailed configuration
   ```

6. **Download Boot Scripts** (Foundation calls automatically)
   ```bash
   GET /boot/scripts/foundation-init.sh
   GET /boot/scripts/network-config.sh
   GET /boot/scripts/post-install.sh
   # Foundation downloads configuration scripts
   ```

### Phase 3: Progress Reporting (Server Reports Back)

7. **Phase Updates** (Server reports automatically)
   ```bash
   POST /api/status/phase
   # Server reports progress through deployment phases
   ```

### Phase 4: Additional Nodes (Repeat for Each Node)

8. **Provision Additional Nodes**
   ```bash
   POST /api/config/nodes
   # Use "join_existing" cluster_operation
   ```

9. **Repeat Boot Process** (Steps 3-7 for each new node)

### Phase 5: Monitoring and Management

10. **Check Overall Status**
    ```bash
    GET /api/status/summary
    # Get cluster-wide deployment status
    ```

11. **View Deployment History**
    ```bash
    GET /api/status/history/{node_id}
    # Get detailed deployment timeline
    ```

## Deployment Phases

The system tracks these deployment phases:

1. **ipxe_boot** - Server boots from iPXE
2. **config_download** - Configuration files downloaded
3. **foundation_start** - Foundation environment started
4. **storage_discovery** - Storage devices detected
5. **image_download** - Nutanix CE images downloaded
6. **installation** - Nutanix CE installation
7. **cluster_formation** - Cluster creation/joining
8. **dns_registration** - DNS records updated
9. **health_validation** - Final health checks

## Typical Usage Patterns

### Single Node Cluster
```bash
# 1. Create cluster with first node
curl -X POST .../api/config/nodes -d '{"node_config":{"cluster_operation":"create_new"},...}'

# 2. Monitor progress
curl .../api/status/nodes/1

# 3. Check when complete
curl .../api/status/summary
```

### Multi-Node Cluster
```bash
# 1. Create first node (as above)
# 2. Add second node
curl -X POST .../api/config/nodes -d '{"node_config":{"cluster_operation":"join_existing"},...}'

# 3. Monitor both nodes
curl .../api/status/nodes/1
curl .../api/status/nodes/2

# 4. Check cluster status
curl .../api/status/summary
```

### Cleanup Failed Deployment
```bash
# 1. Generate cleanup script
curl .../api/cleanup/script/deployment-id > cleanup.sh

# 2. Or trigger automated cleanup
curl -X POST .../api/cleanup/node/1
```

## Error Handling

All endpoints return standard HTTP status codes:
- **200** - Success
- **202** - Accepted (for async operations)
- **400** - Bad Request (missing/invalid parameters)
- **404** - Not Found (resource doesn't exist)
- **500** - Internal Server Error

Error responses include JSON with error details:
```json
{
  "error": "Description of the error",
  "timestamp": "2025-08-01T12:00:00"
}
```

## Security Considerations

- All endpoints should be accessed over HTTPS in production
- The server uses IBM Cloud Trusted Profile authentication
- File serving endpoints have security restrictions on allowed files
- Sensitive configuration data is stored in environment variables

## Rate Limiting and Timeouts

The system includes configurable timeouts for each deployment phase:
- **iPXE Boot**: 300 seconds
- **Config Download**: 120 seconds
- **Foundation Start**: 180 seconds
- **Storage Discovery**: 300 seconds
- **Image Download**: 900 seconds
- **Installation**: 1200 seconds
- **Cluster Formation**: 600 seconds
- **DNS Registration**: 120 seconds
- **Health Validation**: 300 seconds

## Web Interface Routes

The system also provides a web interface for manual management:
- `/` - Dashboard
- `/nodes` - Node management
- `/deployments` - Deployment history
- `/monitoring` - System monitoring
- `/provision` - Node provisioning form

## Integration Examples

### Terraform Integration
```hcl
resource "local_file" "provision_node" {
  content = jsonencode({
    node_config = {
      node_name = "nutanix-node-${count.index + 1}"
      server_profile = "bx2d-metal-48x192"
      cluster_operation = count.index == 0 ? "create_new" : "join_existing"
    }
  })
  
  provisioner "local-exec" {
    command = "curl -X POST ${var.pxe_server}/api/config/nodes -d @${self.filename}"
  }
}
```

### Python Script Integration
```python
import requests
import time

def provision_cluster(nodes):
    pxe_server = "http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080"
    
    for i, node_config in enumerate(nodes):
        # Set cluster operation
        node_config["network_config"]["cluster_operation"] = (
            "create_new" if i == 0 else "join_existing"
        )
        
        # Provision node
        response = requests.post(f"{pxe_server}/api/config/nodes", json=node_config)
        node_data = response.json()
        
        # Monitor deployment
        while True:
            status_response = requests.get(f"{pxe_server}/api/status/nodes/{node_data['node_id']}")
            status = status_response.json()
            
            if status["phase_status"] in ["completed", "failed"]:
                break
                
            time.sleep(30)  # Wait 30 seconds before checking again
```

This API structure provides complete automation for Nutanix CE cluster provisioning while maintaining flexibility for various deployment scenarios and comprehensive monitoring throughout the process.