### **Implementation in PXE Boot Process**

1. **Boot Images**: Foundation images are extracted during setup:
   ```bash
   # In setup.sh
   cp /mnt/boot/kernel /var/www/pxe/images/vmlinuz-foundation
   cp /mnt/boot/initrd /var/www/pxe/images/initrd-foundation.img
   ```

2. **iPXE Script Generation**: In `boot_service.py`:
   ```python
   def generate_ipxe_script_url(self, server_id):
       """Return URL for server-specific iPXE script (for IBM Cloud user_data)"""
       return f"http://{self.pxe_server_ip}/boot/ipxe/{server_id}"
   
   def generate_server_ipxe_script(self, server_id, mgmt_ip):
       """Generate iPXE script for specific server"""
       return f"""#!ipxe
   echo Starting Nutanix Foundation for server {server_id}...
   
   :retry_dhcp
   dhcp || goto retry_dhcp
   sleep 2
   
   set base-url http://{self.pxe_server_ip}/pxe
   
   kernel ${{base-url}}/images/vmlinuz-foundation console=tty0 console=ttyS0,115200
   initrd ${{base-url}}/images/initrd-foundation.img
   
   imgargs vmlinuz-foundation node_id={server_id} mgmt_ip={mgmt_ip}
   
   boot || goto error
   
   :error
   echo Boot failed, retrying...
   sleep 10
   goto retry_dhcp
   """
   
   def create_ibm_cloud_server(self, server_config):
       """Create IBM Cloud VPC bare metal server with iPXE user_data"""
       
       # Generate iPXE script URL for user_data
       ipxe_url = self.generate_ipxe_script_url(server_config['server_id'])
       
       server_response = vpc_client.create_bare_metal_server(
           bare_metal_server_prototype={
               'name': server_config['server_name'],
               'profile': {'name': 'bx2-metal-96x384'},
               'zone': {'name': server_config['zone_name']},
               'vpc': {'id': server_config['vpc_id']},
               'primary_network_interface': {
                   'name': 'eth0',
                   'subnet': {'id': server_config['subnet_id']}
               },
               'user_data': ipxe_url  # URL method - IBM Cloud fetches iPXE script
           }
       )
       
       return server_response
   ```

3. **Configuration Delivery**: Foundation receives configuration via REST API:
   ```python
   def get_server_config(self, server_ip):
       return {
           'server_info': server_info,
           'cluster_config': foundation_config['cluster_config'],
           'node_config': foundation_config['node_config'], 
           'storage_config': storage_config,
           'network_config': network_config
       }
   ```

## Security Considerations

### Network Security
- **HTTPS Configuration**: Use HTTPS for sensitive configuration endpoints
- **Network Isolation**: Ensure PXE server is on trusted network segment
- **Firewall Rules**: Restrict access to PXE server ports (80/443, 69 for TFTP if used)
- **API Authentication**: Implement authentication for configuration endpoints

### Access Control
- **File Permissions**: Proper permissions on PXE server files (644 for files, 755 for directories)
- **Network ACLs**: Restrict which systems can access PXE resources
- **Audit Logging**: Log all boot attempts and configuration downloads
- **IP Validation**: Validate requesting IP addresses against known servers

### Configuration Security
- **Encrypted Passwords**: Use secure password hashing for any stored credentials
- **Certificate Validation**: Validate downloaded files with checksums where possible
- **Configuration Validation**: Validate configuration parameters before applying
- **Secure Defaults**: Use secure default configurations

## Troubleshooting Common Issues

### Boot Failures
1. **Network Issues**: 
   - Check DHCP server configuration and IP allocation
   - Verify routing between servers and PXE server
   - Check firewall rules for HTTP/HTTPS traffic

2. **Missing Files**: 
   - Verify vmlinuz-foundation and initrd-foundation.img exist
   - Check file permissions (should be readable by web server)
   - Validate file integrity with checksums

3. **iPXE Script Issues**:
   - Check iPXE script syntax
   - Verify base-url variable is correctly set
   - Test iPXE script manually if possible

### Foundation Failures
1. **Configuration Issues**: 
   - Validate JSON configuration syntax
   - Check that all required fields are present
   - Verify IP addresses don't conflict

2. **Hardware Issues**: 
   - Confirm specified storage drives exist (`/dev/nvme2n1`, etc.)
   - Verify network interfaces are available
   - Check hardware compatibility with Nutanix CE

3. **Network Timeouts**: 
   - Increase timeout values for slow networks
   - Check network connectivity between nodes
   - Verify DNS resolution if using hostnames

### Storage Configuration Issues
1. **Drive Detection**: 
   - Verify drive naming convention matches system
   - Check that drives are not already in use
   - Validate drive sizes meet minimum requirements

2. **Partition Failures**:
   - Ensure drives are not mounted or in use
   - Check for existing partition tables
   - Verify sufficient free space


## Cluster Formation Process

### **Individual Node Deployment**
Foundation on each node:
1. **Prepares the hardware** (storage, network, drivers)
2. **Installs Nutanix software** (AOS, AHV, CVM)
3. **Configures node-level settings** (IP addresses, storage pools)
4. **Brings node to "ready" state** (CVM running, services ready)
5. **Waits for cluster formation command**

### **Cluster Creation Orchestration**
Your orchestration system:
1. **Waits for minimum nodes** (typically 3 for production)
2. **Validates all nodes are ready** (health checks, connectivity)
3. **Initiates cluster creation** via Nutanix REST APIs or Foundation APIs
4. **Monitors cluster formation** across all participating nodes
5. **Validates cluster health** once formation is complete

### **Why This Two-Phase Approach**
- **Hardware vs Cluster Separation**: Foundation focuses on hardware/software setup
- **Minimum Node Requirements**: Clusters need multiple nodes before formation
- **Orchestration Control**: Your system controls when cluster formation begins
- **Error Handling**: Can retry cluster formation without re-imaging nodes
- **Flexibility**: Supports different cluster topologies and timing

## Cluster Creation API Implementation

### **How Cluster Creation Works**
Once Foundation has prepared the nodes, each node runs a Controller VM (CVM) with REST APIs available. You can connect to **any** of the ready nodes to initiate cluster creation for all nodes. There are two options:

- Option 1 - use Foundation REST API. Not used in this implementation.
- Option 2 - use Prism REST API. Used in this implementation.

### **Option 1: Foundation REST API**
Connect to any ready node's CVM to create the cluster, example code is shown below:

```python
import requests
import time

def create_nutanix_cluster(self, nodes):
    """Create cluster using Foundation API on any ready node"""
    
    # Connect to the first ready node's CVM (port 8000)
    foundation_url = f"https://{nodes[0]['cvm_ip']}:8000"
    
    cluster_config = {
        "cluster_name": "my-nutanix-cluster",
        "cluster_external_ip": "10.240.0.200",
        "dns_servers": ["8.8.8.8"],
        "ntp_servers": ["pool.ntp.org"],
        "nodes": [
            {
                "node_uuid": node["node_uuid"],
                "hypervisor_ip": node["ahv_ip"],
                "cvm_ip": node["cvm_ip"],
                "node_position": "A"
            }
            for node in nodes
        ]
    }
    
    # Call Foundation cluster creation API
    response = requests.post(
        f"{foundation_url}/foundation/clusters",
        json=cluster_config,
        verify=False,  # Self-signed certs on fresh installations
        auth=('admin', 'nutanix/4u'),  # Default Foundation credentials
        timeout=30
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Cluster creation failed: {response.text}")
```

### **Option 2: Nutanix Prism REST API**
Use the standard Nutanix management API:

```python
def create_cluster_prism_api(self, nodes):
    """Create cluster using Nutanix Prism v2 REST API"""
    
    # Connect to any CVM (port 9440)
    prism_url = f"https://{nodes[0]['cvm_ip']}:9440"
    
    cluster_config = {
        "name": "my-nutanix-cluster",
        "external_ip": "10.240.0.200",
        "redundancy_factor": 2,
        "cluster_functions": ["AOS"],
        "timezone": "UTC"
    }
    
    response = requests.post(
        f"{prism_url}/PrismGateway/services/rest/v2.0/clusters",
        json=cluster_config,
        auth=('admin', 'admin'),  # Default Prism credentials
        verify=False,
        timeout=30
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Cluster creation failed: {response.text}")
```

### **Monitor Cluster Creation Progress**
```python
def wait_for_cluster_creation(self, cluster_ip, timeout_minutes=30):
    """Monitor cluster creation progress"""
    
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    
    while (time.time() - start_time) < timeout_seconds:
        try:
            response = requests.get(
                f"https://{cluster_ip}:9440/PrismGateway/services/rest/v2.0/cluster",
                auth=('admin', 'admin'),
                verify=False,
                timeout=10
            )
            
            if response.status_code == 200:
                cluster_status = response.json()
                if cluster_status.get('cluster_status') == 'UP':
                    print("Cluster creation completed successfully!")
                    return True
                else:
                    print(f"Cluster status: {cluster_status.get('cluster_status')}")
                    
        except requests.RequestException as e:
            print(f"Connection attempt failed: {e}")
            
        print("Waiting for cluster formation...")
        time.sleep(30)
    
    raise Exception(f"Cluster creation timed out after {timeout_minutes} minutes")
```

### **Complete Orchestration Flow**
```python
def deploy_nutanix_cluster(self, cluster_config):
    """Complete cluster deployment orchestration"""
    
    print("Starting Nutanix cluster deployment...")
    
    # Phase 1: Deploy individual nodes via Foundation (PXE boot process)
    nodes = []
    for node_config in cluster_config['nodes']:
        print(f"Deploying node: {node_config['server_name']}")
        
        # Create IBM Cloud server with PXE boot (triggers Foundation)
        server = self.create_ibm_cloud_server(node_config)
        nodes.append(server)
    
    print(f"Waiting for {len(nodes)} nodes to complete Foundation deployment...")
    
    # Phase 2: Wait for all Foundation deployments to complete
    ready_nodes = self.wait_for_nodes_ready(nodes)
    print(f"All {len(ready_nodes)} nodes are ready for cluster formation")
    
    # Phase 3: Create cluster using any ready node
    print("Initiating cluster creation...")
    cluster = self.create_nutanix_cluster(ready_nodes)
    
    # Phase 4: Wait for cluster to be fully operational
    print("Monitoring cluster formation progress...")
    self.wait_for_cluster_creation(cluster['cluster_external_ip'])
    
    print("Nutanix cluster deployment completed successfully!")
    return cluster

def wait_for_nodes_ready(self, nodes, timeout_minutes=60):
    """Wait for all nodes to complete Foundation deployment"""
    
    ready_nodes = []
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    
    while len(ready_nodes) < len(nodes) and (time.time() - start_time) < timeout_seconds:
        for node in nodes:
            if node in ready_nodes:
                continue
                
            try:
                # Check if CVM is responding
                response = requests.get(
                    f"https://{node['cvm_ip']}:9440/PrismGateway/services/rest/v1/cluster",
                    auth=('admin', 'admin'),
                    verify=False,
                    timeout=5
                )
                
                if response.status_code == 200:
                    print(f"Node {node['server_name']} is ready")
                    ready_nodes.append(node)
                    
            except requests.RequestException:
                # Node not ready yet
                pass
        
        if len(ready_nodes) < len(nodes):
            print(f"Waiting for {len(nodes) - len(ready_nodes)} more nodes...")
            time.sleep(30)
    
    if len(ready_nodes) < len(nodes):
        raise Exception(f"Timeout waiting for nodes to be ready. Only {len(ready_nodes)}/{len(nodes)} ready")
    
    return ready_nodes
```

### **Key API Details**

| API Type | Port | Default Credentials | Purpose |
|----------|------|-------------------|---------|
| **Foundation API** | 8000 | admin / nutanix/4u | Node preparation and cluster creation |
| **Prism API** | 9440 | admin / admin | Standard Nutanix management |
| **Prism Element** | 9440 | admin / admin | Cluster management post-creation |

### **Important Notes**

1. **Any Node Access**: You can connect to any prepared node's CVM to initiate cluster creation
2. **Self-Signed Certificates**: Fresh Nutanix installations use self-signed certs, so disable SSL verification
3. **Default Credentials**: Change default passwords immediately after cluster creation
4. **Timeout Handling**: Cluster creation can take 10-30 minutes depending on hardware and network
5. **Error Recovery**: If cluster creation fails, you can retry without re-imaging nodes
6. **Network Connectivity**: Ensure all CVMs can communicate with each other on the management network# Understanding PXE Boot Components for Nutanix CE

This document explains how the various components w