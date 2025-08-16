# Workflow Logging and Status

The system has comprehensive logging capabilities that track the deployment progress through multiple phases and stages.

## Logging Endpoints

You can check the status through several endpoints:

- API endpoint: `http://localhost:8080/api/status/nodes/10.240.0.10`
- Web UI: Access the monitoring page at `https://localhost/node/10.240.0.10`
- Database: The `deployment_history` table contains columns that tracks progress for each node

## Node Status Tracking

The system tracks the node deployment phase, these events are all logged in the `deployment_history` table:

### Events

- `node_ips_reserved`: IP addresses have been reserved for the node on the management subnet
- `dns_resources_registered`: IP addresses have been registered in DNS
- `vnis_deployed`: Virtual Network Interfaces (VNIs) have been deployed successfully and are available
- `server_requested`: Server deployment has been successfully requested and accepted by IBM Cloud
- `pending`: Initial status before Server deployment starts - polled via the VPC SDK
- `provisioning`: Hardware is reserved, OS installed, network configured - polled via the VPC SDK
- `ipxe_boot`: Server has contacted the PXE server for its iPXE boot script
- `config_download`: Server has contacted the PXE server for it's configuration
- `rebooting`: The `vpc_ce_installation.py` script run on the bare metal server has sent an API call to say the server is rebooting
- `deployed`: The server is listening on TCP port 22
- `ready`: Server deployment completed successfully and is ready to be included in a cluster - polled from the IBM Cloud API

The following status tags are used when a server deployment fails for any reason:

- `failed`: Server deployment failed - polled from the IBM Cloud API
- `cleaned`: Server deployment has been cleaned up

When using the IBM Cloud VPC SDK the lifecycle of the bare metal server should show:

- `pending: `You request a new bare metal server via API or UI.
- `provisioning`: Hardware is reserved, OS installed, network configured.
- `provisioned`: You now have access via SSH (Linux) or RDP (Windows).
- `starting`: Boot back up.
- `stopping` /`restarting` / `rescue`: Shut down temporarily.
- `running`: Server is available
- `deprovisioning`: You delete the server.
- `deprovisioned`: Fully removed from your account.

Also:

- `failed`: Provisioning or some part of the process failed (hardware/networking/etc).
- `unknown`: May appear if the server is in an inconsistent or transitional state.

## Database 

The system logs deployment events in the `deployment_history` table, which tracks: