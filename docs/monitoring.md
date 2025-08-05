# Monitoring & Status Workflow

The system has comprehensive monitoring capabilities that track the deployment progress through multiple phases:

1. **Initial Status**: After the bare metal server is created in IBM Cloud VPC, the status shows "monitoring_start" which means the system is waiting for the server to boot and contact the PXE server.

2. **Monitoring Endpoints**: You can check the status through several endpoints:
   - API endpoint: `http://localhost:8080/api/status/nodes/1`
   - Web UI: Access the monitoring page at `http://localhost:8080/monitoring`
   - Database: The `nodes` table contains a `deployment_status` column that tracks progress

3. **Status Tracking**: The system tracks various deployment phases:
   - `server_requested`: Deployment of the servers has been requested and accepted by IBM Cloud
   - `pending`: Status from polling the IBM Cloud status. The server is not yet ready
   - `starting`: Status from polling the IBM Cloud status. The server is booting
   - `running`: Status from polling the IBM Cloud status. The server is running
   - `ipxe_boot`: Server has contacted the PXE server
   - `config_requested`: Server has requested its configuration
   - `foundation_boot`: Foundation environment is starting
   - `health_validation`: System health checks
   - `running`: Deployment completed successfully

4. **Database Monitoring**: The system logs deployment events in the `deployment_history` table, which tracks:
   - Phase transitions
   - Status changes
   - Progress messages
   - Error conditions

**Current Status Explanation:**
The "pending" status you see in the IBM Cloud Portal is expected during the initial boot process. The server needs to:
1. Boot the iPXE firmware
2. Download and execute the boot script from our PXE server
3. Load the Foundation kernel and initrd
4. Boot into the Foundation environment
5. Download configuration from our PXE server
6. Begin the Nutanix installation process

This entire process can take 30-60 minutes depending on network conditions and the complexity of the configuration.

**Verification:**
The fix has been successfully verified with the bare metal server created and monitoring started:
```
2025-08-04 15:12:07,135 - ibm_cloud_client - INFO - 127.0.0.1 - Created bare metal server nutanix-poc-bm-node-01
```

The monitoring system is now tracking the deployment progress, and you can check the status using the monitoring endpoints mentioned above.