#!/bin/bash
# Post-installation script for Nutanix CE
# Transfers SSH public key to Nutanix node and CVM for automation access
# Also handles single node cluster creation for Nutanix CE
set -euo pipefail

# Get parameters from command line or environment
NODE_ID=${1:-$(cat /proc/cmdline | grep -o 'node_id=[^ ]*' | cut -d= -f2 || echo "unknown")}
CONFIG_SERVER=${2:-$(cat /proc/cmdline | grep -o 'config_server=[^ ]*' | cut -d= -f2 || echo "localhost")}
OPERATION=${3:-$(cat /proc/cmdline | grep -o 'operation=[^ ]*' | cut -d= -f2 || echo "create_cluster")}

echo "Post-installation script started - Node: $NODE_ID, Operation: $OPERATION"

# Function to transfer SSH key to a target host
transfer_ssh_key() {
    local target_host=$1
    local target_name=$2
    
    echo "Transferring SSH key to $target_name ($target_host)"
    
    # Wait for SSH to be available
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if nc -z $target_host 22 2>/dev/null; then
            echo "SSH is available on $target_name"
            break
        fi
        
        echo "Waiting for SSH on $target_name (attempt $attempt/$max_attempts)"
        sleep 10
        attempt=$((attempt + 1))
    done
    
    if [ $attempt -gt $max_attempts ]; then
        echo "ERROR: SSH not available on $target_name after $max_attempts attempts"
        return 1
    fi
    
    # Get the orchestrator's SSH public key
    if [ ! -f "/home/nutanix/.ssh/id_rsa.pub" ]; then
        echo "ERROR: SSH public key not found at /home/nutanix/.ssh/id_rsa.pub"
        return 1
    fi
    
    local public_key=$(cat /home/nutanix/.ssh/id_rsa.pub)
    
    # Transfer the key using SSH with default password
    echo "Transferring key to $target_name..."
    
    # Try to add the key to authorized_keys using default password
    echo "nutanix/4u" | sshpass ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        nutanix@$target_host \
        "mkdir -p ~/.ssh && echo '$public_key' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh" \
        2>/dev/null || {
            echo "WARNING: Could not transfer key to $target_name via SSH"
            echo "This may be expected if SSH access is not yet configured"
            return 1
        }
    
    echo "SSH key successfully transferred to $target_name"
    return 0
}

# Function to create single node cluster
create_single_node_cluster() {
    local cvm_ip=$1
    local redundancy_factor=$2
    local dns_servers=$3
    
    echo "Creating single node cluster with CVM IP: $cvm_ip"
    
    # Wait for CVM to be ready
    local max_attempts=60
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        # Try to SSH to CVM with default credentials
        if echo "nutanix/4u" | sshpass ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            nutanix@$cvm_ip \
            "echo 'CVM is ready'" 2>/dev/null; then
            echo "CVM is ready for cluster creation"
            break
        fi
        
        echo "Waiting for CVM to be ready (attempt $attempt/$max_attempts)"
        sleep 30
        attempt=$((attempt + 1))
    done
    
    if [ $attempt -gt $max_attempts ]; then
        echo "ERROR: CVM not ready after $max_attempts attempts"
        return 1
    fi
    
    # Create the cluster
    echo "Creating cluster with redundancy factor $redundancy_factor..."
    
    local cluster_cmd="cluster -s $cvm_ip --redundancy_factor=$redundancy_factor --dns_servers $dns_servers create"
    
    if echo "nutanix/4u" | sshpass ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        nutanix@$cvm_ip \
        "$cluster_cmd" 2>&1; then
        echo "Single node cluster created successfully"
        return 0
    else
        echo "ERROR: Failed to create single node cluster"
        return 1
    fi
}

# Get node configuration from orchestrator
echo "Fetching node configuration from orchestrator..."
CONFIG_URL="http://${CONFIG_SERVER}:8080/boot/server/$(hostname -I | awk '{print $1}')"

if curl -f -o /tmp/node-config.json "$CONFIG_URL" 2>/dev/null; then
    echo "Node configuration downloaded successfully"
    
    # Extract CVM and AHV IPs from configuration
    CVM_IP=$(jq -r '.node_config.cvm_ip' /tmp/node-config.json 2>/dev/null || echo "")
    AHV_IP=$(jq -r '.node_config.hypervisor_ip' /tmp/node-config.json 2>/dev/null || echo "")
    
    # Extract cluster configuration
    CLUSTER_OPERATION=$(jq -r '.cluster_operation' /tmp/node-config.json 2>/dev/null || echo "")
    CLUSTER_TYPE=$(jq -r '.cluster_type' /tmp/node-config.json 2>/dev/null || echo "multi_node")
    REDUNDANCY_FACTOR=$(jq -r '.cluster_config.redundancy_factor' /tmp/node-config.json 2>/dev/null || echo "1")
    DNS_SERVERS=$(jq -r '.cluster_config.name_servers[0]' /tmp/node-config.json 2>/dev/null || echo "8.8.8.8")
    
    # Transfer SSH keys
    if [ -n "$CVM_IP" ] && [ "$CVM_IP" != "null" ]; then
        echo "CVM IP: $CVM_IP"
        transfer_ssh_key "$CVM_IP" "CVM"
    else
        echo "WARNING: Could not extract CVM IP from configuration"
    fi
    
    if [ -n "$AHV_IP" ] && [ "$AHV_IP" != "null" ]; then
        echo "AHV IP: $AHV_IP"
        # Note: AHV is the hypervisor, SSH access may be limited
        # We'll still try to transfer the key for potential future use
        transfer_ssh_key "$AHV_IP" "AHV"
    else
        echo "WARNING: Could not extract AHV IP from configuration"
    fi
    
    # Handle cluster creation based on cluster type
    if [ "$OPERATION" = "create_cluster" ] && [ "$CLUSTER_OPERATION" = "create_new" ]; then
        if [ "$CLUSTER_TYPE" = "single_node" ]; then
            echo "This is a single node cluster - cluster creation will be handled by cluster manager API"
            echo "Use POST /api/config/clusters to create the cluster after node deployment"
        else
            echo "This is a multi-node cluster - cluster creation will be handled by Foundation"
        fi
    elif [ "$OPERATION" = "add_node" ]; then
        echo "This is a node addition operation - cluster creation will be handled by Foundation"
    else
        echo "Skipping cluster creation for operation: $OPERATION"
    fi
            
            if [ -n "$CVM_IP" ] && [ "$CVM_IP" != "null" ]; then
                # Create single node cluster
                if create_single_node_cluster "$CVM_IP" "$REDUNDANCY_FACTOR" "$DNS_SERVERS"; then
                    echo "Single node cluster creation completed successfully"
                else
                    echo "ERROR: Failed to create single node cluster"
                fi
            else
                echo "ERROR: Cannot create cluster without CVM IP"
            fi
        else
            echo "This is a multi-node cluster operation - cluster creation will be handled by Foundation"
        fi
    elif [ "$OPERATION" = "add_node" ]; then
        echo "This is a node addition operation - cluster creation will be handled by Foundation"
    else
        echo "Skipping cluster creation for operation: $OPERATION"
    fi
else
    echo "WARNING: Could not download node configuration from orchestrator"
    echo "Skipping SSH key transfer to CVM and AHV"
fi

# Report status to orchestrator
echo "Reporting post-install status to orchestrator..."
curl -X POST "http://${CONFIG_SERVER}:8080/api/status/phase" \
    -H "Content-Type: application/json" \
    -d "{\"server_ip\":\"$(hostname -I | awk '{print $1}')\",\"phase\":\"post_install\",\"status\":\"success\",\"message\":\"Post-install completed\"}" \
    2>/dev/null || echo "WARNING: Could not report status to orchestrator"

echo "Post-installation script completed"