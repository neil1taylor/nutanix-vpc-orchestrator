# IBM Cloud Node Provisioning Operations Guide

## Overview

This documentation describes the operations of two Python scripts that work together to provision Nutanix nodes on IBM Cloud VPC infrastructure using trusted profile authentication. The system automates the complex process of creating bare metal servers with proper networking and DNS configuration.

## System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Node Provisioner│───▶│ IBM Cloud Client │───▶│ IBM Cloud APIs  │
│                 │    │                  │    │ (VPC & DNS)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Configuration   │    │ Trusted Profile  │    │ Provisioned     │
│ Database        │    │ Authentication   │    │ Resources       │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## File 1: `ibm_cloud_client.py`

### Purpose
This file serves as an abstraction layer between the application and IBM Cloud APIs. It handles authentication via trusted profiles and provides simplified methods for managing VPC and DNS resources.

### Key Components

#### Authentication Setup
```python
self.vpc_authenticator = VPCInstanceAuthenticator()
self.vpc_service = VpcV1(authenticator=self.vpc_authenticator)
```

**What this does:**
- Uses IBM Cloud's trusted profile authentication (no API keys needed)
- The `VPCInstanceAuthenticator` automatically retrieves tokens from the instance metadata service
- Tokens are automatically refreshed when they expire

#### VPC Operations

##### 1. IP Address Reservation
```python
def create_subnet_reserved_ip(self, subnet_id, address, name):
```
**Purpose:** Reserves a specific IP address in a subnet to prevent it from being assigned to other resources.

**Process:**
1. Creates a reservation request with the desired IP address
2. Calls IBM Cloud VPC API to reserve the IP
3. Returns reservation details including the reservation ID

**Use Case:** Ensuring Nutanix nodes get predictable IP addresses for management and clustering.

##### 2. Virtual Network Interface (VNI) Management
```python
def create_virtual_network_interface(self, subnet_id, name, primary_ip_id, security_group_ids):
```
**Purpose:** Creates a modern network interface that can be attached to bare metal servers.

**What VNIs provide:**
- Independent lifecycle from compute resources
- Support for multiple IP addresses
- Advanced security group management
- Can be moved between servers for high availability

**Process:**
1. Defines VNI configuration with subnet, IP, and security groups
2. Creates the VNI via IBM Cloud API
3. Returns VNI details for use in server creation

##### 3. Bare Metal Server Provisioning
```python
def create_bare_metal_server(self, name, profile, image_id, primary_vni_id, additional_vnis, user_data):
```
**Purpose:** Creates a physical server with specified configuration and network attachments.

**Key Concepts:**
- **Profile:** Defines server specifications (CPU, memory, storage)
- **Image:** Custom iPXE boot image for Nutanix installation
- **Network Attachments:** Connect VNIs to the server
- **User Data:** Cloud-init configuration passed to the server

#### DNS Operations

##### DNS Record Management
```python
def create_dns_record(self, record_type, name, rdata, ttl=300):
```
**Purpose:** Creates DNS records in IBM Cloud DNS Services for hostname resolution.

**Process:**
1. Formats the DNS record according to IBM Cloud API requirements
2. Creates the record in the specified DNS zone
3. Returns record details for tracking and cleanup

**Why This Matters:** Nutanix nodes need consistent DNS names for cluster communication and management access.

## File 2: `node_provisioner.py`

### Purpose
This is the main orchestration engine that coordinates the entire node provisioning process. It implements a multi-step workflow with error handling and rollback capabilities.

### Provisioning Workflow

#### Step 1: IP Address Reservation
```python
def reserve_node_ips(self, node_config):
```

**What it does:**
1. **Analyzes subnet capacity:** Gets current subnet information and existing reservations
2. **Calculates available IPs:** Uses IP range configuration to find free addresses
3. **Reserves multiple IPs per node:**
   - Management interface IP (for server management)
   - AHV IP (hypervisor access)
   - CVM IP (Controller VM access)
   - Workload IP (data network)
   - Cluster IP (only for first node - cluster management)

**IP Range Strategy:**
```python
# Example IP ranges from config
IP_RANGES = {
    'management': (10, 50),    # .10 to .50 in subnet
    'ahv': (51, 100),          # .51 to .100 in subnet
    'cvm': (101, 150),         # .101 to .150 in subnet
    'workload': (10, 200),     # Different subnet
    'cluster': (200, 210)      # Cluster VIPs
}
```

**Error Handling:** If any IP reservation fails, all successful reservations are cleaned up automatically.

#### Step 2: DNS Registration
```python
def register_node_dns(self, ip_allocation, node_config):
```

**DNS Record Creation:**
- `node01-mgmt.domain.com` → Management IP
- `node01-ahv.domain.com` → Hypervisor IP  
- `node01-cvm.domain.com` → Controller VM IP
- `node01-workload.domain.com` → Workload IP
- `cluster01.domain.com` → Cluster IP (first node only)

**Why Multiple DNS Names:**
Nutanix architecture requires different components to communicate via specific interfaces, each needing its own DNS name for proper cluster operation.

#### Step 3: Virtual Network Interface Creation
```python
def create_node_vnis(self, ip_allocation, node_config):
```

**VNI Architecture:**
- **Management VNI:** Connected to management subnet with security groups for SSH, HTTPS, cluster ports
- **Workload VNI:** Connected to workload subnet for VM traffic and storage replication

**Benefits of VNIs:**
- Can survive server failures and be attached to replacement servers
- Support advanced networking features like secondary IPs
- Provide network-level isolation and security

#### Step 4: Database Configuration
```python
def update_config_database(self, node_data, ip_allocation, vnis):
```

**Information Stored:**
- Node metadata (name, position, role)
- Network configuration (IPs, VNI IDs, DNS names)
- Nutanix-specific configuration
- Deployment tracking information

**Purpose:** Provides persistent storage for configuration data needed during deployment and ongoing operations.

#### Step 5: Bare Metal Server Deployment
```python
def deploy_bare_metal_server(self, node_id, vnis, node_data):
```

**Deployment Process:**
1. **Custom Image Selection:** Uses a pre-built iPXE boot image configured for Nutanix
2. **Network Attachment:** Connects the VNIs created in previous steps
3. **User Data Generation:** Creates cloud-init configuration with node-specific information
4. **Server Creation:** Provisions the bare metal server with all configurations

**User Data Contents:**
```json
{
    "node_id": "unique_node_identifier",
    "pxe_server": "pxe-server.domain.com",
    "config_endpoint": "http://pxe-server.domain.com:8081/server-config"
}
```

#### Step 6: Monitoring Initialization
```python
def start_deployment_monitoring(self, node_id):
```

**Monitoring Setup:**
- Initializes deployment status tracking
- Prepares for health checks and progress monitoring
- Sets up endpoints for status queries

### Error Handling and Cleanup

#### Rollback Strategy
Each provisioning step includes cleanup logic:

```python
try:
    # Provisioning step
    result = self.create_resource()
except Exception as e:
    # Cleanup any partial success
    self.cleanup_resources()
    raise
```

**Cleanup Hierarchy:**
1. DNS records (fastest to clean up)
2. VNIs (network interfaces)
3. IP reservations
4. Database entries

#### Failure Scenarios Handled:
- **Network timeouts:** Automatic retry with exponential backoff
- **Resource quota exceeded:** Clear error messages with guidance
- **Partial failures:** Complete rollback to prevent resource leaks
- **Authentication issues:** Detailed logging for troubleshooting

### Nutanix-Specific Considerations

#### Why Multiple IP Addresses?
Nutanix nodes require separate network interfaces for:
- **Management:** Administrative access, monitoring, configuration
- **Hypervisor (AHV):** Virtual machine management and migration
- **Controller VM (CVM):** Storage services and data replication
- **Workload:** VM data traffic and user workloads

#### iPXE Boot Process
1. **Server Powers On:** Bare metal server starts with custom iPXE image
2. **Network Configuration:** Server gets IP address via DHCP or static config
3. **PXE Boot:** Contacts PXE server to download Nutanix installation image
4. **Automated Install:** Nutanix software installs using pre-configured parameters

#### Cluster Formation
- **First Node:** Gets cluster IP and initializes cluster database
- **Additional Nodes:** Join existing cluster using cluster IP
- **Discovery:** Nodes find each other via DNS resolution

## Configuration Requirements

### Environment Setup
```python
# Required configuration items
class Config:
    IBM_CLOUD_REGION = "us-south"
    VPC_ID = "vpc-12345678"
    MANAGEMENT_SUBNET_ID = "subnet-mgmt-12345"
    WORKLOAD_SUBNET_ID = "subnet-work-12345"
    DNS_INSTANCE_ID = "dns-instance-12345"
    DNS_ZONE_ID = "dns-zone-12345"
    DNS_ZONE_NAME = "nutanix.internal"
```

### Security Groups
Must be configured to allow:
- SSH (port 22) for management access
- HTTPS (port 443) for web interfaces
- Nutanix cluster ports (2009, 2030, 2036, etc.)
- Storage replication ports

### Trusted Profile Permissions
The trusted profile must have:
- VPC Infrastructure Services: Editor + Manager roles
- DNS Services: Editor + Manager roles  
- Resource Group: Viewer role

## Operational Workflows

### Successful Provisioning Flow
```
Request → IP Reservation → DNS Registration → VNI Creation → 
Database Update → Server Deployment → Monitoring → Complete
```

### Error Recovery Flow
```
Error Detected → Identify Failure Point → Cleanup Created Resources →
Log Error Details → Return Error to Caller
```

### Monitoring and Status
- **Real-time Status:** Query database for current deployment state
- **Progress Tracking:** Monitor each provisioning step
- **Error Logging:** Detailed logs for troubleshooting failures
- **Resource Tracking:** Maintain inventory of created resources

## Best Practices

### Resource Naming
- Use consistent naming conventions: `{node-name}-{component}-{type}`
- Include environment identifiers for multi-environment deployments
- Make names descriptive for easier troubleshooting

### Error Handling
- Always clean up partial successes
- Log detailed error information
- Provide actionable error messages
- Implement retry logic for transient failures

### Security
- Use trusted profiles instead of API keys
- Apply principle of least privilege
- Regularly rotate any manual credentials
- Monitor access patterns and unusual activity

This system provides a robust, automated way to provision Nutanix nodes on IBM Cloud while handling the complexity of modern cloud networking and maintaining proper error recovery capabilities.