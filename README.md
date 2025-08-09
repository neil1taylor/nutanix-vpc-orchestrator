# Nutanix PXE/Config Server Deployment Guide

This repository contains the complete Python application for the Nutanix PXE/Config Server that provides automated provisioning of Nutanix CE nodes on IBM Cloud VPC bare metal servers.

## Repository Structure

```
nutanix-pxe-server/
├── requirements.txt         # Python dependencies
├── config.py                # Configuration settings
├── database.py              # Database models and operations
├── ibm_cloud_client.py      # IBM Cloud API client
├── node_provisioner.py      # Node provisioning service
├── boot_service.py          # iPXE boot service
├── status_monitor.py        # Deployment status monitoring
├── app.py                   # Main Flask application
├── setup.sh                 # Installation script
├── gunicorn.conf.py         # Gunicorn configuration
└── README-Deployment.md     # This file
```

## Deployment Overview

The deployment follows a two-phase approach:

1. **Phase 1**: Infrastructure deployment creates VPC, subnets, and PXE/Config Server VSI - Located in TBD
2. **Phase 2**: On-demand node provisioning via API calls to the PXE/Config Server - Contained in this GitHub repository.

## Phase 1: Infrastructure Deployment

### Prerequisites

- IBM Cloud CLI installed and configured
- IBM Cloud VPC service enabled
- IBM Cloud DNS service instance created
- Appropriate IAM permissions for VPC and DNS management
- GitHub repository with this code deployed

### Cloud-Init Configuration

The cloud-init used in the pase 1 script will automatically:

1. **Clone Repository**: Downloads all application files from thisGitHub
2. **Install Dependencies**: Sets up Python environment and PostgreSQL
3. **Configure Services**: Creates systemd services and Nginx configuration
4. **Initialize Database**: Creates database schema and tables
5. **Start Services**: Enables and starts all required services
6. **Health Validation**: Verifies deployment success

## Phase 2: Node Provisioning API

### API Endpoints

Once the PXE/Config Server is deployed, it exposes the following endpoints:

- **Node Provisioning**: `POST /api/nodes`
- **Node Status**: `GET /api/nodes/{id}/status`
- **Boot Configuration**: `GET /boot-config` (for iPXE)
- **Server Configuration**: `GET /server-config/{ip}` (for Foundation)
- **Health Check**: `GET /health`

### Provision First Node (Create Cluster)



### Provision Additional Node (Join Cluster)



### Monitor Deployment Progress

```bash
# Check node status
curl http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/nodes/1/status

# Get deployment history
curl http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/nodes/1/history

# Get overall summary
curl http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/deployment/summary
```

## Operations and Maintenance

### Service Management

```bash
# Check service status
sudo systemctl status nutanix-pxe

# Restart service
sudo systemctl restart nutanix-pxe

# View logs
sudo journalctl -u nutanix-pxe -f


### Health Monitoring

```bash
# Health check
curl http://localhost:8080/health

# Service info
curl http://localhost:8080/api/info

# Deployment summary
curl http://localhost:8080/api/deployment/summary
```

### Log Management

Key log locations:
- **Deployment**: `/var/log/nutanix-pxe-deployment.log`
- **Application**: `/var/log/nutanix-pxe/pxe-server.log`
- **Gunicorn**: `/var/log/nutanix-pxe/gunicorn-*.log`
- **System Service**: `journalctl -u nutanix-pxe`

### Database Management

```bash
# Connect to database
sudo -u postgres psql nutanix_pxe

# View nodes
SELECT node_name, deployment_status, created_at FROM nodes;

# View deployment history
SELECT n.node_name, dh.phase, dh.status, dh.timestamp 
FROM deployment_history dh 
JOIN nodes n ON dh.node_id = n.id 
ORDER BY dh.timestamp DESC;
```

## Development and Updates

### Local Development

```bash
# Clone repository
git clone https://github.com/your-org/nutanix-pxe-server.git
cd nutanix-pxe-server

# Setup development environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run locally
python app.py
```

### Deploying Updates

```bash
# Make changes and commit
git add .
git commit -m "Update feature XYZ"
git push origin main

# Update production server
ssh nutanix@nutanix-pxe-config.nutanix-ce-poc.cloud
/opt/nutanix-pxe/update.sh
```

### Creating Releases

```bash
# Tag a release
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0

# Deploy specific version
export GITHUB_BRANCH="v1.0.0"
# Redeploy with cloud-init
```

## Troubleshooting

### Common Issues

1. **Repository Clone Fails**
   ```bash
   # Check repository accessibility
   git clone https://github.com/your-org/nutanix-pxe-server.git /tmp/test-clone
   
   # Check cloud-init logs
   sudo cat /var/log/cloud-init-output.log
   ```

2. **Service Won't Start**
   ```bash
   # Check installation logs
   sudo cat /var/log/nutanix-pxe-deployment.log
   
   # Check service status
   sudo systemctl status nutanix-pxe --no-pager
   
   # Check dependencies
   /opt/nutanix-pxe/venv/bin/pip list
   ```

3. **API Endpoints Not Responding**
   ```bash
   # Check nginx configuration
   sudo nginx -t
   
   # Check if gunicorn is running
   ps aux | grep gunicorn
   
   # Check port binding
   sudo netstat -tlnp | grep :8080
   ```

### Recovery Procedures

1. **Redeploy from Scratch**
   ```bash
   # Delete and recreate VSI with cloud-init
   ibmcloud is instance-delete nutanix-poc-pxe-01
   # Redeploy with cloud-init.yaml
   ```

2. **Manual Recovery**
   ```bash
   # SSH to server and run deployment script manually
   ssh nutanix@server-ip
   sudo bash /tmp/deploy-nutanix-pxe.sh
   ```

3. **Rollback to Previous Version**
   ```bash
   cd /opt/nutanix-pxe
   sudo -u nutanix git checkout v1.0.0
   sudo systemctl restart nutanix-pxe
   ```

## Security Considerations

1. **Repository Security**
   - Use private repository for production deployments
   - Implement proper access controls
   - Use deploy keys for automated access

2. **Environment Variables**
   - Store sensitive data in secure environment variables
   - Use IBM Cloud Secrets Manager for production
   - Rotate API keys regularly

3. **Network Security**
   - Configure security groups properly
   - Use VPN for administrative access
   - Monitor access logs

This deployment guide provides a complete framework for implementing automated Nutanix CE provisioning on IBM Cloud VPC infrastructure using GitHub-based deployment and the two-phase approach.


# Single Node Cluster
Foundation alone will not configure a single node cluster in Nutanix CE. Here's what actually happens:

What Foundation Does:

- Imaging and installation of AOS and hypervisor onto the bare metal server
- Network configuration (IP addresses for hypervisor, CVM)
- Initial node preparation but stops short of cluster creation
- Can be automated via JSON configuration files for unattended installation

Foundation will prepare the node but won't automatically create the single-node cluster

Phase 1: iPXE/PXE Setup Process:

- iPXE boot loads Foundation installer from your PXE server
- Foundation uses your supplied JSON config file to:
    - Install AOS and AHV
    - Configure network settings (CVM IP, host IP, etc.)
    - Prepare storage devices
    - Complete initial node setup

Phase 2: Manual Cluster Creation (Post-Phoenix), a post-installation script in the PXE orchestration:

- Script waits for CVM to be ready
- Script SSH into the CVM: ssh nutanix@<cvm_ip> (password: nutanix/4u)
- Manually create the cluster:
    - For RF1: cluster -s <cvm_ip> --redundancy_factor=1 --dns_servers <dns_ip> create-
    - For RF2: cluster -s <cvm_ip> --redundancy_factor=2 --dns_servers <dns_ip> create

# Standard cluster
Foundation does handle cluster creation for 3+ node clusters automatically.

3+ Node Clusters (Standard):
- Foundation **automatically creates the cluster** as part of the installation process
- After imaging all nodes, Foundation proceeds with cluster creation without requiring manual intervention
- Foundation will then proceed with the imaging (if necessary) and cluster creation process

**Single Node Clusters:**
- Nutanix removed the checkbox to create a one node cluster
- Foundation only does the imaging/preparation, then stops
- Requires manual cluster creation via CLI

## Foundation Multi-Node Process

**Standard 3+ Node Flow:**
1. **Discovery:** Foundation discovers all nodes to be clustered
2. **Configuration:** Input cluster details, network settings, node IPs
3. **Validation:** Network validation across all nodes
4. **Imaging:** Install AOS and hypervisor on all nodes (if needed)
5. **Cluster Creation:** Foundation automatically creates the cluster
6. **Completion:** Once the creation is successful you'll get a completion screen

**Command Reference:**
- Multi-node: The command to create a three node cluster is: cluster -s <cvm ip1>,<cvm ip2>,<cvm ip3> –dns_servers 1.1.1.1 create
- Foundation handles this automatically for 3+ nodes
