Here are the exact curl commands for Phase 1 steps 1 and 2:

## Step 1: Provision First Node (Create New Cluster)

```bash
curl -X POST http://localhost:8080/api/config/nodes \
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
      "workload_subnet": "auto",
      "cluster_operation": "create_new"
    }
  }'
```

**Expected Response:**
```json
{
  "message": "Node provisioning initiated successfully",
  "node_id": 1,
  "deployment_id": "bare-metal-server-id",
  "estimated_completion": "2025-08-01T14:30:00",
  "monitoring_endpoint": "/api/status/nodes/1"
}
```

## Step 2: Monitor Deployment Progress

Using the `node_id` from step 1 response (in this example, `1`):

```bash
curl http://localhost:8080/api/status/nodes/1
```

**Expected Response:**
```json
{
  "server_ip": "10.240.0.10",
  "server_name": "nutanix-poc-bm-node-01",
  "node_id": 1,
  "deployment_id": "bare-metal-server-id",
  "current_phase": "provisioning",
  "phase_status": "in_progress",
  "progress_percent": 15,
  "elapsed_time_seconds": 180,
  "estimated_remaining_seconds": 2700,
  "timed_out": false,
  "last_update": "2025-08-01T12:15:30",
  "message": "Creating bare metal server"
}
```

## Monitoring Loop

To continuously monitor until completion:

```bash
# Simple monitoring loop
while true; do
  response=$(curl -s http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/status/nodes/1)
  echo "$(date): $response"
  
  # Check if deployment is complete
  if echo "$response" | grep -q '"phase_status":"completed"'; then
    echo "Deployment completed successfully!"
    break
  elif echo "$response" | grep -q '"phase_status":"failed"'; then
    echo "Deployment failed!"
    break
  fi
  
  sleep 30  # Wait 30 seconds before checking again
done
```

## Alternative: Using jq for Better Output

If you have `jq` installed for better JSON parsing:

```bash
# Get deployment status with formatted output
curl -s http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/status/nodes/1 | \
  jq '{
    node_name: .server_name,
    phase: .current_phase,
    status: .phase_status,
    progress: .progress_percent,
    message: .message,
    elapsed_time: .elapsed_time_seconds
  }'
```

## For Subsequent Nodes

Once your first node is deployed, add additional nodes with:

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

The key differences for additional nodes:
- Different `node_name`
- Use `"cluster_operation": "join_existing"` instead of `"create_new"`
- Storage config is optional for additional nodes