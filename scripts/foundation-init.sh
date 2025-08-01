#!/bin/bash
# Foundation initialization script for Nutanix CE
set -euo pipefail

NODE_ID=$(cat /proc/cmdline | grep -o 'node_id=[^ ]*' | cut -d= -f2 || echo "unknown")
OPERATION=$(cat /proc/cmdline | grep -o 'operation=[^ ]*' | cut -d= -f2 || echo "create_cluster")
CONFIG_SERVER=$(cat /proc/cmdline | grep -o 'config_server=[^ ]*' | cut -d= -f2 || echo "localhost")

echo "Foundation initialization - Node: $NODE_ID, Operation: $OPERATION"

# Download and apply configuration
if curl -f -o /tmp/server-config.json "http://${CONFIG_SERVER}:8080/server-config/$(hostname -I | awk '{print $1}')" 2>/dev/null; then
    echo "Configuration downloaded successfully"
else
    echo "Warning: Could not download configuration"
fi

# Report status
curl -X POST "http://${CONFIG_SERVER}:8080/api/v1/phase-update" \
    -H "Content-Type: application/json" \
    -d "{\"server_ip\":\"$(hostname -I | awk '{print $1}')\",\"phase\":\"foundation_start\",\"status\":\"success\"}" \
    2>/dev/null || echo "Warning: Could not report status"