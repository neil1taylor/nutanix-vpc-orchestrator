# Nutanix VPC Orchestrator Scripts

This directory contains utility scripts for managing the Nutanix VPC Orchestrator.

## Reinitialize Server Script

The `reinitialize_server.py` script allows you to stop a bare metal server and reinitialize it with a specific IP address. This is useful when you need to reconfigure a server without provisioning a new one.

### Prerequisites

- The server must be registered in the database
- The IBM Cloud VPC SDK must be properly configured
- The server must be accessible via the VPC

### Usage

```bash
./reinitialize_server.py <hostname> [--timeout <minutes>]
```

#### Arguments

- `hostname`: The hostname of the server to reinitialize (required)
- `--timeout`: Timeout in minutes for the server to stop (default: 30)

#### Example

```bash
# Reinitialize a server with the default timeout
./reinitialize_server.py nutanix-node-1

# Reinitialize a server with a custom timeout of 15 minutes
./reinitialize_server.py nutanix-node-1 --timeout 15
```

### Process

The script performs the following steps:

1. Retrieves server details from the database using the provided hostname
2. Stops the bare metal server using the VPC SDK
3. Waits for the server to reach the stopped state (with timeout)
4. Reinitializes the server with an iPXE boot configuration URL:
   `http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/boot/config?mgmt_ip=${net0/ip}`
   
   The `${net0/ip}` variable is expanded by the iPXE client on the bare metal server to the actual IP address.

### Error Handling

The script includes error handling for various scenarios:

- Server not found in the database
- Failed to stop the server
- Timeout waiting for the server to stop
- Failed to reinitialize the server

If any of these errors occur, the script will exit with a non-zero status code and display an error message.

## Other Scripts

- `populate_bare_metal_server.py`: Populates the database with bare metal server details for reinitialization
- `check_vpc_methods.py`: Checks available methods in the VPC SDK
- `list_nodes.py`: Lists all nodes in the database
- `reset_database.py`: Resets the database to its initial state