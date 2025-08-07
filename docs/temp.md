# Nutanix CE Configuration JSON Structure

After analyzing the `ParamList` class in `docs/temp.py`, I can determine what a JSON configuration file for Nutanix Community Edition (CE) would look like.

## Key Configuration Parameters

```json
{
  "hyp_type": "kvm",
  "model": "NX-3060-G7",
  "node_position": "A",
  "block_id": "BLOCK-123",
  "node_serial": "SERIAL-456",
  "cluster_id": 1,
  "node_name": "BLOCK-123-A",
  "cluster_name": "CE-Cluster",
  
  "hyp_install_type": "clean",
  "svm_install_type": "clean",
  
  "ce_hyp_boot_disk": "/dev/sda",
  "ce_cvm_boot_disks": ["/dev/sdb"],
  "ce_cvm_data_disks": ["/dev/sdc", "/dev/sdd"],
  "ce_disks": ["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"],
  
  "host_ip": "192.168.1.100",
  "host_subnet_mask": "255.255.255.0",
  "default_gw": "192.168.1.1",
  
  "svm_ip": "192.168.1.101",
  "svm_subnet_mask": "255.255.255.0",
  "svm_default_gw": "192.168.1.1",
  
  "dns_ip": "8.8.8.8",
  "per_node_ntp_servers": "pool.ntp.org,time.google.com",
  
  "svm_gb_ram": 16,
  "svm_num_vcpus": 4,
  
  "create_1node_cluster": true,
  "ce_eula_accepted": true,
  "ce_eula_viewed": true,
}
```

## Critical Configuration Requirements

1. **Basic Node Information**:
   - `hyp_type`: Hypervisor type (typically "kvm" for CE)
   - `model`, `node_position`, `block_id`, `node_serial`: Required identifiers
   - `cluster_id`: Must be a positive integer

2. **CE-Specific Parameters**:
   - `ce_hyp_boot_disk`, `ce_cvm_boot_disks`, `ce_cvm_data_disks`: Disk configurations
   - `ce_eula_accepted` and `ce_eula_viewed`: Must be true
   - `create_1node_cluster`: For single-node deployments

3. **Network Configuration**:
   - Host networking (`host_ip`, `host_subnet_mask`, `default_gw`): All three must be provided together
   - CVM networking (`svm_ip`, `svm_subnet_mask`, `svm_default_gw`): All three must be provided together
   - IPs cannot be in the 192.168.5.x network (reserved)

4. **Resource Allocation**:
   - `svm_gb_ram`: RAM for CVM (in GB)
   - `svm_num_vcpus`: vCPUs for CVM

The configuration is validated through the `ce_validate()` method which enforces these requirements.