# Nutanix VPC Orchestrator API Documentation

This document outlines the available API endpoints for the Nutanix VPC Orchestrator, their functionalities, and example `curl` commands for usage.

## Boot Server Endpoints

These endpoints are used for iPXE boot configuration and serving boot files.

### `/boot/config` (GET)

**Description:** Handles iPXE boot configuration requests. Returns a boot script tailored to the requesting client.

**Example `curl` command:**
```bash
curl http://localhost:8080/boot/config?mgmt_ip=10.240.0.10
```

### `/boot/server/<server_ip>` (GET)

**Description:** Retrieves detailed server configuration for a given server IP address. This is used by the provisioning process to configure newly provisioned nodes.

**Example `curl` command:**
```bash
curl http://localhost:8080/boot/server/10.240.0.10
```

### `/boot/images/<filename>` (GET)

**Description:** Serves boot images such as kernel, initrd, and ISO files required for node provisioning.

**Example `curl` command:**
```bash
curl http://localhost:8080/boot/images/kernel -o kernel
curl http://localhost:8080/boot/images/initrd-vpc.img -o initrd-vpc.img

curl -I http://localhost:8080/boot/images/kernel
curl -I http://localhost:8080/boot/images/initrd-vpc.img
```

### `/boot/scripts/<script_name>` (GET)

**Description:** Serves boot scripts and configuration files used during the node provisioning and setup process.

**Example `curl` command:**
```bash
curl http://localhost:8080/boot/scripts/foundation-init.sh -o foundation-init.sh
```

## Configuration API Endpoints

These endpoints are used for managing nodes, clusters, and related configurations.

### `/api/config/nodes` (POST)

**Description:** Provisions a new Nutanix node. Requires a JSON payload with `node_config` and optionally `cluster_config` and `network_config`.

**Example `curl` command:**
```bash
curl -X POST http://localhost:8080/api/config/nodes \
-H "Content-Type: application/json" \
-d '{
  "node_config": {
    "node_name": "node-01",
    "server_profile": "default_profile",
    "cluster_role": "worker",
    "storage_template": "nutanix_default"
  },
  "network_config": {
    "management_subnet": "auto",
    "workload_subnets": ["subnet-1", "subnet-2"]
  },
  "cluster_config": {
    "cluster_type": "multi_node"
  }
}'
```

### `/api/config/clusters` (POST)

**Description:** Creates a new Nutanix cluster from deployed nodes. Requires a JSON payload with `cluster_config` including a list of node IDs.

**Example `curl` command:**
```bash
curl -X POST http://localhost:8080/api/config/clusters \
-H "Content-Type: application/json" \
-d '{
  "cluster_config": {
    "cluster_name": "my-cluster",
    "cluster_type": "multi_node",
    "nodes": [1, 2, 3]
  }
}'
```

### `/api/config/clusters/<int:cluster_id>` (GET)

**Description:** Retrieves information about a specific cluster.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/config/clusters/1
```

### `/api/config/clusters` (GET)

**Description:** Lists all configured clusters.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/config/clusters
```

### `/api/config/clusters/<int:cluster_id>` (DELETE)

**Description:** Deletes information for a specific cluster.

**Example `curl` command:**
```bash
curl -X DELETE http://localhost:8080/api/config/clusters/1
```

### `/api/config/nodes/<int:node_id>` (GET)

**Description:** Retrieves information about a specific node.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/config/nodes/1
```

### `/api/config/nodes` (GET)

**Description:** Lists all nodes managed by the orchestrator.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/config/nodes
```

## Status Monitoring Endpoints

These endpoints are used for monitoring the status of nodes and deployments.

### `/api/status/nodes/<int:node_id>` (GET)

**Description:** Gets the deployment status for a specific node.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/status/nodes/1
```

### `/api/status/deployment/<server_ip>` (GET)

**Description:** Gets deployment status by server IP address (legacy endpoint).

**Example `curl` command:**
```bash
curl http://localhost:8080/api/status/deployment/10.240.0.10
```

### `/api/status/phase` (POST)

**Description:** Receives phase updates from deploying servers. Used by nodes during the deployment process to report their current stage.

**Example `curl` command:**
```bash
curl -X POST http://localhost:8080/api/status/phase \
-H "Content-Type: application/json" \
-d '{
  "server_ip": "<server-ip-address>",
  "phase": "installing_os",
  "status": "in_progress"
}'
```

### `/api/status/history/<int:node_id>` (GET)

**Description:** Gets the deployment history for a specific node.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/status/history/1
```

### `/api/status/summary` (GET)

**Description:** Gets an overall summary of all deployments.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/status/summary
```

### `/api/status` (POST)

**Description:** Updates the installation status. This endpoint is likely called by nodes to report their overall installation progress.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/status
```

## Database API Endpoints

These endpoints provide access to the system's database for viewing and exporting data.

### `/api/web/database-table` (GET)

**Description:** Retrieves data from a specific database table.

**Example `curl` command:**
```bash
curl "http://localhost:8080/api/web/database-table?table=nodes"
```

### `/api/web/database-schema` (GET)

**Description:** Retrieves schema information for a specific database table.

**Example `curl` command:**
```bash
curl "http://localhost:8080/api/web/database-schema?table=nodes"
```

### `/api/web/database-export` (GET)

**Description:** Exports table data as a CSV file.

**Example `curl` command:**
```bash
curl "http://localhost:8080/api/web/database-export?table=nodes" -o nodes.csv
```

### `/api/web/database-tables` (GET)

**Description:** Retrieves a list of all available database tables.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/web/database-tables
```

## Server Profile and Storage Endpoints

These endpoints provide information about server profiles and storage templates.

### `/api/web/profile-storage-config` (GET)

**Description:** Gets the storage configuration for a given server profile and storage template.

**Example `curl` command:**
```bash
curl "http://localhost:8080/api/web/profile-storage-config?profile=default_profile&template=nutanix_default"
```

### `/api/web/profile-details` (GET)

**Description:** Gets detailed information about a specific server profile.

**Example `curl` command:**
```bash
curl "http://localhost:8080/api/web/profile-details?profile=default_profile"
```

### `/api/web/server-profiles` (GET)

**Description:** Gets a list of all available server profiles.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/web/server-profiles
```

### `/api/web/storage-templates` (GET)

**Description:** Gets a list of available storage templates.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/web/storage-templates
```

### `/api/web/validate-node-config` (POST)

**Description:** Validates node configuration before provisioning. Expects a JSON payload with the node configuration.

**Example `curl` command:**
```bash
curl -X POST http://localhost:8080/api/web/validate-node-config \
-H "Content-Type: application/json" \
-d '{
  "node_config": {
    "node_name": "node-02",
    "server_profile": "high_memory_profile"
  }
}'
```

## DNS Management Endpoints

These endpoints are for managing DNS records within the orchestrator.

### `/api/dns/records` (POST)

**Description:** Creates a new DNS record. Requires a JSON payload with the record details.

**Example `curl` command:**
```bash
curl -X POST http://localhost:8080/api/dns/records \
-H "Content-Type: application/json" \
-d '{
  "record_name": "my-server",
  "record_type": "A",
  "value": "192.168.1.100"
}'
```

### `/api/dns/records/<record_name>` (DELETE)

**Description:** Deletes a specific DNS record.

**Example `curl` command:**
```bash
curl -X DELETE http://localhost:8080/api/dns/records/my-server
```

### `/api/dns/records` (GET)

**Description:** Lists all DNS records.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/dns/records
```

### `/api/dns/records/<record_name>` (GET)

**Description:** Gets a specific DNS record.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/dns/records/my-server
```

## Cleanup Endpoints

These endpoints are used for cleaning up resources.

### `/api/cleanup/node/<int:node_id>` (POST)

**Description:** Cleans up resources associated with a specific node.

**Example `curl` command:**
```bash
curl -X POST http://localhost:8080/api/cleanup/node/1
```

### `/api/cleanup/deployment/<deployment_id>` (POST)

**Description:** Cleans up all resources for a given deployment.

**Example `curl` command:**
```bash
curl -X POST http://localhost:8080/api/cleanup/deployment/<deployment-id>
```

### `/api/cleanup/script/<deployment_id>` (GET)

**Description:** Generates a cleanup script for manual execution for a specific deployment.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/cleanup/script/<deployment-id> -o cleanup_script.sh
```

### `/api/cleanup/status` (GET)

**Description:** Gets the overall cleanup status.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/cleanup/status
```

### `/api/cleanup/validate/<int:node_id>` (GET)

**Description:** Validates the cleanup completion for a specific node.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/cleanup/validate/1
```

### `/api/cleanup/orphaned` (POST)

**Description:** Cleans up orphaned resources that may have resulted from failed deployments.

**Example `curl` command:**
```bash
curl -X POST http://localhost:8080/api/cleanup/orphaned
```

### `/api/cleanup/batch` (POST)

**Description:** Performs batch cleanup operations. Expects a JSON payload specifying the cleanup targets.

**Example `curl` command:**
```bash
curl -X POST http://localhost:8080/api/cleanup/batch \
-H "Content-Type: application/json" \
-d '{
  "cleanup_targets": [
    {"type": "node", "id": 1},
    {"type": "deployment", "id": "deployment-abc"}
  ]
}'
```

## Health and Info Endpoints

### `/health` (GET)

**Description:** Health check endpoint. Returns a simple status indicating if the orchestrator is running.

**Example `curl` command:**
```bash
curl http://localhost:8080/health
```

### `/api/info` (GET)

**Description:** Retrieves general server information about the orchestrator.

**Example `curl` command:**
```bash
curl http://localhost:8080/api/info