# Nutanix on IBM Cloud VPC Bare Metal Networking Configuration Guide

## Overview

This guide explains how to configure networking for Nutanix clusters deployed on IBM Cloud VPC bare metal servers. The architecture uses dual PCI NICs with VLAN interfaces to separate management and workload traffic while providing connectivity to multiple VPC subnets.

## Network Architecture

### Physical Network Layout with Built-in Redundancy

```
┌───────────────────────────────────────────────────────────┐
│                    IBM Cloud VPC                          │
├───────────────────────────────────────────────────────────┤
│  Management Subnet         │    Workload Subnets          │
│  10.240.0.0/24             │    10.241.0.0/24             │
│                            │    10.242.0.0/24             │
│                            │    10.243.0.0/24             │
└───────────────────────────────────────────────────────────┘
                    │                      │
            ┌───────┴──────┐       ┌───────┴──────┐
            │  TOR Switch  │       │  TOR Switch  │
            │      A       │       │      B       │
            └──────┬───────┘       └──────┬───────┘
                   │                      │
┌───────────────────────────────────────────────────────────┐
│              Bare Metal Server                            │
├───────────────────────────────────────────────────────────┤
│  PCI NIC 0 (eth0)         │    PCI NIC 1 (eth1)           │
│  Management Traffic       │    Workload Traffic           │
│  - Hypervisor Mgmt        │    - VM Networks              │
│  - CVM Management         │    - VLAN Interfaces          │
│  ┌─────────────────┐      │      - eth1.100 (VLAN 100)    │
│  │ Redundant Ports │      │      - eth1.200 (VLAN 200)    │
│  │ to TOR A & B    │      │      - eth1.300 (VLAN 300)    │
│  └─────────────────┘      │    ┌─────────────────┐        │
│                           │    │ Redundant Ports │        │
│                           │    │ to TOR A & B    │        │
│                           │    └─────────────────┘        │
└───────────────────────────────────────────────────────────┘
```

### Network Redundancy and Fault Tolerance

**Built-in Hardware Redundancy**: Each PCI network interface is redundant by design. The uplinks (PCI network interfaces) are redundant and you don't need to manage uplink redundancy because redundancy is automatic.

**Key Redundancy Features**:
- **Dual Physical Uplinks**: Each PCI NIC is backed by two redundant physical ports connected to separate Top-of-Rack (TOR) switches
- **Automatic Failover**: IBM Cloud manages the aggregation and failover between the redundant links transparently
- **No Single Point of Failure**: Network connectivity is maintained even if one physical port or TOR switch fails
- **VLAN Interface Redundancy**: VLAN interfaces inherit the same redundancy as their parent PCI interface

### Network Interface Mapping

| Component | Interface | Purpose | Subnet | Redundancy |
|-----------|-----------|---------|--------|------------|
| AHV/ESXi Host | eth0 | Hypervisor Management | Management Subnet | Dual uplinks to TOR A+B |
| Nutanix CVM | eth0 | CVM Management | Management Subnet | Dual uplinks to TOR A+B |
| VM Networks | eth1 | Primary Workload | Workload Subnet 1 | Dual uplinks to TOR A+B |
| VM Networks | eth1.100 | VLAN Workload | Workload Subnet 2 | Inherits eth1 redundancy |
| VM Networks | eth1.200 | VLAN Workload | Workload Subnet 3 | Inherits eth1 redundancy |
| VM Networks | eth1.300 | VLAN Workload | Workload Subnet 4 | Inherits eth1 redundancy |

## IBM Cloud VPC Configuration

### 1. Create VPC and Subnets

```bash
# Create VPC
ibmcloud is vpc-create nutanix-vpc --resource-group-name default

# Create Management Subnet
ibmcloud is subnet-create mgmt-subnet nutanix-vpc \
  --ipv4-address-count 256 \
  --ipv4-cidr-block 10.240.0.0/24 \
  --zone us-south-1

# Create Workload Subnets
ibmcloud is subnet-create workload-subnet-1 nutanix-vpc \
  --ipv4-address-count 256 \
  --ipv4-cidr-block 10.241.0.0/24 \
  --zone us-south-1

ibmcloud is subnet-create workload-subnet-2 nutanix-vpc \
  --ipv4-address-count 256 \
  --ipv4-cidr-block 10.242.0.0/24 \
  --zone us-south-1

ibmcloud is subnet-create workload-subnet-3 nutanix-vpc \
  --ipv4-address-count 256 \
  --ipv4-cidr-block 10.243.0.0/24 \
  --zone us-south-1
```

### 2. Create Security Groups

```bash
# Management Security Group
ibmcloud is security-group-create mgmt-sg nutanix-vpc \
  --rules '[
    {
      "direction": "inbound",
      "protocol": "tcp",
      "port_min": 22,
      "port_max": 22,
      "remote": {"cidr_block": "0.0.0.0/0"}
    },
    {
      "direction": "inbound",
      "protocol": "tcp",
      "port_min": 9440,
      "port_max": 9440,
      "remote": {"cidr_block": "10.240.0.0/24"}
    },
    {
      "direction": "inbound",
      "protocol": "tcp",
      "port_min": 2009,
      "port_max": 2009,
      "remote": {"cidr_block": "10.240.0.0/24"}
    }
  ]'

# Workload Security Group
ibmcloud is security-group-create workload-sg nutanix-vpc \
  --rules '[
    {
      "direction": "inbound",
      "protocol": "all",
      "remote": {"cidr_block": "10.241.0.0/16"}
    },
    {
      "direction": "outbound",
      "protocol": "all",
      "remote": {"cidr_block": "0.0.0.0/0"}
    }
  ]'
```

### 3. Provision Bare Metal Server

```bash
# Create bare metal server with dual NICs
ibmcloud is bare-metal-server-create \
  --name nutanix-node-1 \
  --zone us-south-1 \
  --profile bx2d-metal-96x384 \
  --image r006-ed3f775f-ad7e-4e37-ae62-7199b4988b00 \
  --primary-network-interface '[
    {
      "name": "mgmt-nic",
      "subnet": {"id": "MGMT_SUBNET_ID"},
      "security_groups": [{"id": "MGMT_SG_ID"}],
      "allow_ip_spoofing": true
    }
  ]' \
  --network-interfaces '[
    {
      "name": "workload-nic",
      "subnet": {"id": "WORKLOAD_SUBNET_1_ID"},
      "security_groups": [{"id": "WORKLOAD_SG_ID"}],
      "allow_ip_spoofing": true,
      "vlan": 100
    }
  ]'
```

### 4. Add VLAN Interfaces to Workload NIC

```bash
# Add VLAN interface for subnet 2
ibmcloud is bare-metal-server-network-interface-create nutanix-node-1 \
  --interface-type vlan \
  --vlan 200 \
  --name workload-vlan-200 \
  --subnet workload-subnet-2 \
  --security-groups workload-sg \
  --allow-ip-spoofing true

# Add VLAN interface for subnet 3
ibmcloud is bare-metal-server-network-interface-create nutanix-node-1 \
  --interface-type vlan \
  --vlan 300 \
  --name workload-vlan-300 \
  --subnet workload-subnet-3 \
  --security-groups workload-sg \
  --allow-ip-spoofing true
```

## Operating System Network Configuration

### AHV/ESXi Host Configuration

#### CentOS/RHEL (AHV) Network Configuration

```bash
# /etc/sysconfig/network-scripts/ifcfg-eth0 (Management)
cat > /etc/sysconfig/network-scripts/ifcfg-eth0 << EOF
DEVICE=eth0
BOOTPROTO=static
IPADDR=10.240.0.10
NETMASK=255.255.255.0
GATEWAY=10.240.0.1
DNS1=161.26.0.10
DNS2=161.26.0.11
ONBOOT=yes
EOF

# /etc/sysconfig/network-scripts/ifcfg-eth1 (Workload Primary)
cat > /etc/sysconfig/network-scripts/ifcfg-eth1 << EOF
DEVICE=eth1
BOOTPROTO=static
IPADDR=10.241.0.10
NETMASK=255.255.255.0
ONBOOT=yes
EOF

# Create VLAN interfaces
# /etc/sysconfig/network-scripts/ifcfg-eth1.200
cat > /etc/sysconfig/network-scripts/ifcfg-eth1.200 << EOF
DEVICE=eth1.200
BOOTPROTO=static
IPADDR=10.242.0.10
NETMASK=255.255.255.0
VLAN=yes
ONBOOT=yes
EOF

# /etc/sysconfig/network-scripts/ifcfg-eth1.300
cat > /etc/sysconfig/network-scripts/ifcfg-eth1.300 << EOF
DEVICE=eth1.300
BOOTPROTO=static
IPADDR=10.243.0.10
NETMASK=255.255.255.0
VLAN=yes
ONBOOT=yes
EOF

# Restart networking
systemctl restart NetworkManager
```

#### VMware ESXi Configuration

```bash
# Configure management vmkernel interface
esxcli network vswitch standard add --vswitch-name vSwitch0
esxcli network vswitch standard portgroup add --portgroup-name "Management Network" --vswitch-name vSwitch0
esxcli network vswitch standard uplink add --uplink-name vmnic0 --vswitch-name vSwitch0

# Configure workload vSwitch
esxcli network vswitch standard add --vswitch-name vSwitch1
esxcli network vswitch standard uplink add --uplink-name vmnic1 --vswitch-name vSwitch1

# Create VLAN port groups
esxcli network vswitch standard portgroup add --portgroup-name "VLAN-100" --vswitch-name vSwitch1
esxcli network vswitch standard portgroup set --portgroup-name "VLAN-100" --vlan-id 100

esxcli network vswitch standard portgroup add --portgroup-name "VLAN-200" --vswitch-name vSwitch1
esxcli network vswitch standard portgroup set --portgroup-name "VLAN-200" --vlan-id 200

esxcli network vswitch standard portgroup add --portgroup-name "VLAN-300" --vswitch-name vSwitch1
esxcli network vswitch standard portgroup set --portgroup-name "VLAN-300" --vlan-id 300
```

## Nutanix Configuration

### CVM Network Configuration

```bash
# Configure CVM networking (executed on each CVM)
# Management interface (eth0)
sudo /home/nutanix/cluster/bin/manage_ovs --bridge_name br0 --interfaces eth0

# Set static IP for CVM management
allssh "sudo /home/nutanix/cluster/bin/acli net.update_dhcp_scope network=External cidr=10.240.0.0/24 gateway=10.240.0.1"

# Configure workload bridge (eth1)
sudo /home/nutanix/cluster/bin/manage_ovs --bridge_name br1 --interfaces eth1
```

### Prism Element Network Configuration

```bash
# Create network configurations in Prism Element
# Management Network
curl -X POST "https://cluster-vip:9440/PrismGateway/services/rest/v2.0/networks" \
  -H "Content-Type: application/json" \
  -u admin:password \
  -d '{
    "name": "Management",
    "vlan_id": 0,
    "network_address": "10.240.0.0",
    "network_mask": "255.255.255.0",
    "default_gateway": "10.240.0.1",
    "pool_list": [
      {
        "range": "10.240.0.100 10.240.0.200"
      }
    ]
  }'

# Workload Networks
curl -X POST "https://cluster-vip:9440/PrismGateway/services/rest/v2.0/networks" \
  -H "Content-Type: application/json" \
  -u admin:password \
  -d '{
    "name": "Workload-VLAN-100",
    "vlan_id": 100,
    "network_address": "10.241.0.0",
    "network_mask": "255.255.255.0",
    "default_gateway": "10.241.0.1",
    "pool_list": [
      {
        "range": "10.241.0.100 10.241.0.200"
      }
    ]
  }'

curl -X POST "https://cluster-vip:9440/PrismGateway/services/rest/v2.0/networks" \
  -H "Content-Type: application/json" \
  -u admin:password \
  -d '{
    "name": "Workload-VLAN-200",
    "vlan_id": 200,
    "network_address": "10.242.0.0",
    "network_mask": "255.255.255.0",
    "default_gateway": "10.242.0.1",
    "pool_list": [
      {
        "range": "10.242.0.100 10.242.0.200"
      }
    ]
  }'
```

## Advanced Configuration

### Terraform Configuration Example

```hcl
# variables.tf
variable "vpc_name" {
  description = "Name of the VPC"
  type        = string
  default     = "nutanix-vpc"
}

variable "resource_group" {
  description = "Resource group"
  type        = string
  default     = "default"
}

# main.tf
terraform {
  required_providers {
    ibm = {
      source  = "IBM-Cloud/ibm"
      version = "~> 1.45.0"
    }
  }
}

provider "ibm" {
  region = "us-south"
}

# Create VPC
resource "ibm_is_vpc" "nutanix_vpc" {
  name           = var.vpc_name
  resource_group = data.ibm_resource_group.rg.id
  tags           = ["nutanix", "hci"]
}

# Create subnets
resource "ibm_is_subnet" "management" {
  name            = "${var.vpc_name}-mgmt"
  vpc             = ibm_is_vpc.nutanix_vpc.id
  zone            = "us-south-1"
  ipv4_cidr_block = "10.240.0.0/24"
  resource_group  = data.ibm_resource_group.rg.id
}

resource "ibm_is_subnet" "workload" {
  count           = 3
  name            = "${var.vpc_name}-workload-${count.index + 1}"
  vpc             = ibm_is_vpc.nutanix_vpc.id
  zone            = "us-south-1"
  ipv4_cidr_block = "10.24${count.index + 1}.0.0/24"
  resource_group  = data.ibm_resource_group.rg.id
}

# Security Groups
resource "ibm_is_security_group" "management" {
  name           = "${var.vpc_name}-mgmt-sg"
  vpc            = ibm_is_vpc.nutanix_vpc.id
  resource_group = data.ibm_resource_group.rg.id
}

resource "ibm_is_security_group_rule" "mgmt_ssh" {
  group     = ibm_is_security_group.management.id
  direction = "inbound"
  tcp {
    port_min = 22
    port_max = 22
  }
}

resource "ibm_is_security_group_rule" "mgmt_prism" {
  group     = ibm_is_security_group.management.id
  direction = "inbound"
  tcp {
    port_min = 9440
    port_max = 9440
  }
  remote = ibm_is_security_group.management.id
}

# Bare Metal Servers
resource "ibm_is_bare_metal_server" "nutanix_nodes" {
  count   = 3
  profile = "bx2d-metal-96x384"
  name    = "nutanix-node-${count.index + 1}"
  image   = data.ibm_is_image.centos.id
  zone    = "us-south-1"

  primary_network_interface {
    name            = "mgmt-nic"
    subnet          = ibm_is_subnet.management.id
    security_groups = [ibm_is_security_group.management.id]
    allow_ip_spoofing = true
  }

  network_interfaces {
    name            = "workload-nic"
    subnet          = ibm_is_subnet.workload[0].id
    security_groups = [ibm_is_security_group.workload.id]
    allow_ip_spoofing = true
  }

  user_data = base64encode(templatefile("${path.module}/cloud-init.yml", {
    mgmt_ip = "10.240.0.${count.index + 10}"
    work_ip = "10.241.0.${count.index + 10}"
  }))

  resource_group = data.ibm_resource_group.rg.id
  
  tags = ["nutanix", "node-${count.index + 1}"]
}

# Add VLAN interfaces
resource "ibm_is_bare_metal_server_network_interface" "vlan_interfaces" {
  count               = 6  # 3 nodes × 2 additional VLANs
  bare_metal_server   = ibm_is_bare_metal_server.nutanix_nodes[count.index % 3].id
  interface_type      = "vlan"
  name                = "vlan-${200 + (count.index / 3) * 100}"
  vlan                = 200 + (count.index / 3) * 100
  subnet              = ibm_is_subnet.workload[1 + (count.index / 3)].id
  security_groups     = [ibm_is_security_group.workload.id]
  allow_ip_spoofing   = true
}
```

### Ansible Playbook for Network Configuration

```yaml
# nutanix-network-setup.yml
---
- name: Configure Nutanix Cluster Networking
  hosts: nutanix_nodes
  become: yes
  vars:
    mgmt_subnet: "10.240.0.0/24"
    mgmt_gateway: "10.240.0.1"
    workload_subnets:
      - { vlan: 100, cidr: "10.241.0.0/24", gateway: "10.241.0.1" }
      - { vlan: 200, cidr: "10.242.0.0/24", gateway: "10.242.0.1" }
      - { vlan: 300, cidr: "10.243.0.0/24", gateway: "10.243.0.1" }

  tasks:
    - name: Configure management interface
      copy:
        content: |
          DEVICE=eth0
          BOOTPROTO=static
          IPADDR={{ ansible_host }}
          NETMASK=255.255.255.0
          GATEWAY={{ mgmt_gateway }}
          DNS1=161.26.0.10
          DNS2=161.26.0.11
          ONBOOT=yes
        dest: /etc/sysconfig/network-scripts/ifcfg-eth0
      notify: restart_network

    - name: Configure workload interface
      copy:
        content: |
          DEVICE=eth1
          BOOTPROTO=static
          IPADDR={{ workload_ip }}
          NETMASK=255.255.255.0
          ONBOOT=yes
        dest: /etc/sysconfig/network-scripts/ifcfg-eth1
      notify: restart_network

    - name: Configure VLAN interfaces
      copy:
        content: |
          DEVICE=eth1.{{ item.vlan }}
          BOOTPROTO=static
          IPADDR={{ item.ip }}
          NETMASK=255.255.255.0
          VLAN=yes
          ONBOOT=yes
        dest: /etc/sysconfig/network-scripts/ifcfg-eth1.{{ item.vlan }}
      loop:
        - { vlan: 200, ip: "{{ vlan_200_ip }}" }
        - { vlan: 300, ip: "{{ vlan_300_ip }}" }
      notify: restart_network

    - name: Load 8021q module
      modprobe:
        name: 8021q
        state: present

    - name: Add 8021q to modules
      lineinfile:
        path: /etc/modules-load.d/8021q.conf
        line: 8021q
        create: yes

  handlers:
    - name: restart_network
      systemd:
        name: NetworkManager
        state: restarted
```

## Troubleshooting

### Common Network Issues

#### 1. VLAN Interface Not Coming Up

```bash
# Check if VLAN module is loaded
lsmod | grep 8021q

# Load VLAN module if missing
modprobe 8021q

# Check interface status
ip link show
ip addr show

# Manually create VLAN interface for testing
ip link add link eth1 name eth1.200 type vlan id 200
ip addr add 10.242.0.10/24 dev eth1.200
ip link set eth1.200 up
```

#### 2. Connectivity Issues Between Subnets

```bash
# Check routing table
ip route show

# Check security group rules
ibmcloud is security-group-rules SECURITY_GROUP_ID

# Test connectivity
ping 10.241.0.1  # Test gateway connectivity
traceroute 10.242.0.1  # Trace route to other subnet
```

#### 3. CVM Network Connectivity

```bash
# Check OVS bridges
sudo ovs-vsctl show

# Check CVM network status
allssh "ifconfig"

# Restart CVM networking
allssh "sudo systemctl restart openvswitch"
```

### Monitoring and Validation

```bash
# Validate IBM Cloud VPC configuration
ibmcloud is bare-metal-server nutanix-node-1 --output json

# Check all network interfaces
ibmcloud is bare-metal-server-network-interfaces nutanix-node-1

# Validate VLAN configuration
ibmcloud is bare-metal-server-network-interface nutanix-node-1 workload-vlan-200

# Monitor network traffic
sudo tcpdump -i eth1.200 -n

# Check Nutanix cluster status
ncli cluster get-params
```

## Best Practices

1. **IP Spoofing**: Always enable `allow_ip_spoofing` on workload interfaces to support VM networking
2. **Security Groups**: Use separate security groups for management and workload traffic
3. **VLAN IDs**: Use consistent VLAN IDs across all nodes in the cluster
4. **Redundancy**: All network interfaces are automatically redundant in IBM Cloud VPC
5. **Documentation**: Keep network diagrams and IP allocation spreadsheets updated
6. **Monitoring**: Implement network monitoring for all subnets and interfaces

## Summary

This configuration provides a robust networking foundation for Nutanix clusters on IBM Cloud VPC, with proper traffic separation between management and workload networks, support for multiple workload subnets through VLAN interfaces, and full integration with IBM Cloud VPC security and routing features.