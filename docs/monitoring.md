# Monitoring & Status Workflow

The system has comprehensive monitoring capabilities that track the deployment progress through multiple phases:

## 1. Initial Status
After the bare metal server is created in IBM Cloud VPC, the status shows "monitoring_start" which means the system is waiting for the server to boot and contact the PXE server.

## 2. Monitoring Endpoints
You can check the status through several endpoints:
- API endpoint: `http://localhost:8080/api/status/nodes/1`
- Web UI: Access the monitoring page at `http://localhost:8080/monitoring`
- Database: The `nodes` table contains a `deployment_status` column that tracks progress

## 3. Status Tracking
The system tracks various deployment phases:

### Provisioning Phases
- `pending`: Initial status before deployment starts
- `monitoring_start`: Deployment monitoring has been initialized
- `server_requested`: Deployment of the servers has been requested and accepted by IBM Cloud
- `ipxe_boot`: Server has contacted the PXE server
- `config_download`: Server is downloading its configuration
- `foundation_start`: Foundation environment is starting
- `storage_discovery`: Storage devices are being discovered
- `image_download`: Installation images are being downloaded
- `installation`: Nutanix software is being installed
- `cluster_formation`: Cluster is being formed (for multi-node deployments)
- `dns_registration`: DNS records are being registered
- `health_validation`: System health checks
- `deployed`: Deployment completed successfully
- `failed`: Deployment failed

### Failure States
- `failed`: Deployment has failed and requires cleanup
- `cleanup_completed`: Cleanup after failed deployment has been completed

## 4. Database Monitoring
The system logs deployment events in the `deployment_history` table, which tracks:
- Phase transitions
- Status changes
- Progress messages
- Error conditions

## 5. Deployment Phase Details

### monitoring_start
This phase is initiated when the node provisioner starts monitoring for a newly created bare metal server. The system is waiting for the server to boot and contact the PXE server.

### ipxe_boot
When the bare metal server boots, it contacts the PXE server to download its boot configuration. This phase is logged when the boot service receives an iPXE boot request.

### config_download
The server downloads its detailed configuration from the orchestrator. This includes network settings, cluster configuration, and other deployment parameters.

### foundation_start
The Foundation environment is starting. This is logged by the foundation-init.sh script when it begins execution on the deployed server.

### storage_discovery
The system is discovering storage devices on the node. This is part of the Foundation process.

### image_download
Installation images are being downloaded to the node. This can take some time depending on network conditions.

### installation
The Nutanix software is being installed on the node. This includes the hypervisor and CVM components.

### cluster_formation
For multi-node deployments, the cluster is being formed. This phase is logged when the first node successfully creates the cluster.

### dns_registration
DNS records are being registered for the deployed node and cluster.

### health_validation
System health checks are being performed to ensure the deployment is successful.

### deployed
Deployment has completed successfully and the node is ready for use.

### failed
Deployment has failed. This status is set when any phase reports a failure.

## 6. API Endpoints

### Get Node Status
```
GET /api/status/nodes/{node_id}
```
Returns detailed status information for a specific node.

### Get Deployment Status by IP
```
GET /api/status/deployment/{server_ip}
```
Returns deployment status for a server identified by its IP address.

### Update Deployment Phase
```
POST /api/status/phase
```
Used by deployed servers to report their current phase and status.

### Get Deployment History
```
GET /api/status/history/{node_id}
```
Returns the complete deployment history for a node.

### Get Deployment Summary
```
GET /api/status/summary
```
Returns an overall summary of all deployments.

## 7. Monitoring Scripts
The deployment process uses several scripts that report status back to the orchestrator:

- `foundation-init.sh`: Reports `foundation_start` phase
- `network-config.sh`: Reports `network_config` phase
- `post-install.sh`: Reports `post_install` phase

Each script uses curl to POST status updates to the `/api/status/phase` endpoint.

## 8. Current Status Explanation
The "pending" status you see in the IBM Cloud Portal is expected during the initial boot process. The server needs to:
1. Boot the iPXE firmware
2. Download and execute the boot script from our PXE server
3. Load the Foundation kernel and initrd
4. Boot into the Foundation environment
5. Download configuration from our PXE server
6. Begin the Nutanix installation process

This entire process can take 30-60 minutes depending on network conditions and the complexity of the configuration.

## 9. Verification
The fix has been successfully verified with the bare metal server created and monitoring started:
```
2025-08-04 15:12:07,135 - ibm_cloud_client - INFO - 127.0.0.1 - Created bare metal server nutanix-poc-bm-node-01
```

The monitoring system is now tracking the deployment progress, and you can check the status using the monitoring endpoints mentioned above.