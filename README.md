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

- **Node Provisioning**: `POST /api/v1/nodes`
- **Node Status**: `GET /api/v1/nodes/{id}/status`
- **Boot Configuration**: `GET /boot-config` (for iPXE)
- **Server Configuration**: `GET /server-config/{ip}` (for Foundation)
- **Health Check**: `GET /health`

### Provision First Node (Create Cluster)



### Provision Additional Node (Join Cluster)



### Monitor Deployment Progress

```bash
# Check node status
curl http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/v1/nodes/1/status

# Get deployment history
curl http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/v1/nodes/1/history

# Get overall summary
curl http://nutanix-pxe-config.nutanix-ce-poc.cloud:8080/api/v1/deployment/summary
```

## Post-Deployment Setup

### Upload Nutanix Boot Images

Replace the placeholder boot images with actual Nutanix images:

```bash
# SSH to PXE server
ssh nutanix@nutanix-pxe-config.nutanix-ce-poc.cloud

# Upload actual Nutanix images
sudo cp nutanix-foundation-kernel /var/www/pxe/images/vmlinuz-foundation
sudo cp nutanix-foundation-initrd.img /var/www/pxe/images/initrd-foundation.img
sudo cp nutanix-ce-installer.iso /var/www/pxe/images/

# Set permissions
sudo chown -R nutanix:nutanix /var/www/pxe/images/
```

### Update Configuration

```bash
# Edit environment file
sudo nano /opt/nutanix-pxe/.env

# Restart service to apply changes
sudo systemctl restart nutanix-pxe
```

### Update Application from GitHub

```bash
# Use the built-in update script
/opt/nutanix-pxe/update.sh

# Or manually update
cd /opt/nutanix-pxe
sudo -u nutanix git pull origin main
sudo -u nutanix ./venv/bin/pip install -r requirements.txt
sudo systemctl restart nutanix-pxe
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
curl http://localhost:8080/api/v1/info

# Deployment summary
curl http://localhost:8080/api/v1/deployment/summary
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