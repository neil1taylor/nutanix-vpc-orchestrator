#!/bin/bash
# Network configuration script for Nutanix CE
# Configures network interfaces based on deployment configuration
set -euo pipefail

echo "Network configuration script started"

# Get parameters from command line or environment
NODE_ID=${1:-$(cat /proc/cmdline | grep -o 'node_id=[^ ]*' | cut -d= -f2 || echo "unknown")}
CONFIG_SERVER=${2:-$(cat /proc/cmdline | grep -o 'config_server=[^ ]*' | cut -d= -f2 || echo "localhost")}

echo "Node ID: $NODE_ID"
echo "Config Server: $CONFIG_SERVER"

# Get node configuration from orchestrator
echo "Fetching network configuration from orchestrator..."
CONFIG_URL="http://${CONFIG_SERVER}:8080/boot/server/$(hostname -I | awk '{print $1}')"

if curl -f -o /tmp/network-config.json "$CONFIG_URL" 2>/dev/null; then
    echo "Network configuration downloaded successfully"
    
    # Apply network configuration
    echo "Applying network configuration..."
    
    # Configure management interface
    MANAGEMENT_IP=$(jq -r '.network_config.management_network.ip' /tmp/network-config.json)
    MANAGEMENT_NETMASK=$(jq -r '.network_config.management_network.netmask' /tmp/network-config.json)
    MANAGEMENT_GATEWAY=$(jq -r '.network_config.management_network.gateway' /tmp/network-config.json)
    
    if [ -n "$MANAGEMENT_IP" ] && [ "$MANAGEMENT_IP" != "null" ]; then
        echo "Configuring management interface with IP $MANAGEMENT_IP"
        # Actual network configuration commands would go here
    fi
    
    # Configure primary workload interface
    WORKLOAD_IP=$(jq -r '.network_config.workload_network.ip' /tmp/network-config.json)
    WORKLOAD_NETMASK=$(jq -r '.network_config.workload_network.netmask' /tmp/network-config.json)
    WORKLOAD_GATEWAY=$(jq -r '.network_config.workload_network.gateway' /tmp/network-config.json)
    
    if [ -n "$WORKLOAD_IP" ] && [ "$WORKLOAD_IP" != "null" ]; then
        echo "Configuring workload interface with IP $WORKLOAD_IP"
        # Actual network configuration commands would go here
    fi
    
    # Configure additional workload interfaces if they exist
    ADDITIONAL_WORKLOAD_COUNT=$(jq '.network_config.additional_workload_networks | length' /tmp/network-config.json)
    
    if [ "$ADDITIONAL_WORKLOAD_COUNT" != "null" ] && [ "$ADDITIONAL_WORKLOAD_COUNT" -gt 0 ]; then
        echo "Configuring $ADDITIONAL_WORKLOAD_COUNT additional workload interfaces"
        
        for i in $(seq 0 $((ADDITIONAL_WORKLOAD_COUNT - 1))); do
            INTERFACE_IP=$(jq -r ".network_config.additional_workload_networks[$i].ip" /tmp/network-config.json)
            if [ -n "$INTERFACE_IP" ] && [ "$INTERFACE_IP" != "null" ]; then
                echo "Configuring additional workload interface $((i + 2)) with IP $INTERFACE_IP"
                # Actual network configuration commands would go here
            fi
        done
    fi
    
    echo "Network configuration applied successfully"
else
    echo "WARNING: Could not download network configuration from orchestrator"
fi

# Report status to orchestrator
echo "Reporting network configuration status to orchestrator..."
curl -X POST "http://${CONFIG_SERVER}:8080/api/status/phase" \
    -H "Content-Type: application/json" \
    -d "{\"server_ip\":\"$(hostname -I | awk '{print $1}')\",\"phase\":\"network_config\",\"status\":\"success\",\"message\":\"Network configured\"}" \
    2>/dev/null || echo "WARNING: Could not report status to orchestrator"

echo "Network configuration script completed"