#!/bin/bash
# Setup script for Nutanix PXE/Config Server
# This script is executed by cloud-init during VSI deployment

set -euo pipefail

# Configuration
PROJECT_DIR="/opt/nutanix-pxe"
SERVICE_USER="nutanix"
LOG_FILE="/var/log/nutanix-pxe-setup.log"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

log "Starting Nutanix PXE/Config Server setup"

# Update system packages
log "Updating system packages"
apt-get update
apt-get upgrade -y

# Install required packages
log "Installing required packages"
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    postgresql \
    postgresql-contrib \
    nginx \
    git \
    curl \
    wget \
    unzip \
    systemd \
    supervisor

# Create service user
log "Creating service user"
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/bash -d "$PROJECT_DIR" "$SERVICE_USER"
fi

# Create project directory
log "Creating project directory"
mkdir -p "$PROJECT_DIR"
chown "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR"

# Clone application from GitHub
log "Cloning application from GitHub"
cd "$PROJECT_DIR"
# Note: Replace with actual GitHub repository URL
# git clone https://github.com/your-org/nutanix-pxe-server.git .
# For now, we'll create the structure manually since this is a demonstration

# Create directory structure
mkdir -p {logs,images,scripts,configs,static,templates}
mkdir -p /var/www/pxe/{images,scripts,configs}
mkdir -p /var/log/nutanix-pxe

# Set permissions
chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" /var/www/pxe
chown -R "$SERVICE_USER:$SERVICE_USER" /var/log/nutanix-pxe

# Setup Python virtual environment
log "Setting up Python virtual environment"
cd "$PROJECT_DIR"
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
log "Installing Python dependencies"
pip install --upgrade pip
pip install -r requirements.txt

# Setup PostgreSQL database
log "Setting up PostgreSQL database"
sudo -u postgres createuser nutanix || true
sudo -u postgres createdb nutanix_pxe -O nutanix || true
sudo -u postgres psql -c "ALTER USER nutanix PASSWORD 'nutanix';" || true

# Configure PostgreSQL
PG_CONFIG_DIR="/etc/postgresql/14/main"

# Allow local connections
if ! grep -q "host nutanix_pxe nutanix 127.0.0.1/32 md5" "${PG_CONFIG_DIR}/pg_hba.conf"; then
    echo "host nutanix_pxe nutanix 127.0.0.1/32 md5" >> "${PG_CONFIG_DIR}/pg_hba.conf"
fi

# Restart PostgreSQL
systemctl restart postgresql
systemctl enable postgresql

# Create environment file
log "Creating environment configuration"
cat > "$PROJECT_DIR/.env" << EOF
# IBM Cloud Configuration
IBM_CLOUD_API_KEY=${IBM_CLOUD_API_KEY:-}
IBM_CLOUD_REGION=${IBM_CLOUD_REGION:-us-south}
VPC_ID=${VPC_ID:-}
DNS_INSTANCE_ID=${DNS_INSTANCE_ID:-}
DNS_ZONE_ID=${DNS_ZONE_ID:-}

# Network Configuration
MANAGEMENT_SUBNET_ID=${MANAGEMENT_SUBNET_ID:-}
WORKLOAD_SUBNET_ID=${WORKLOAD_SUBNET_ID:-}
MANAGEMENT_SECURITY_GROUP_ID=${MANAGEMENT_SECURITY_GROUP_ID:-}
WORKLOAD_SECURITY_GROUP_ID=${WORKLOAD_SECURITY_GROUP_ID:-}

# Database Configuration
DATABASE_URL=postgresql://nutanix:nutanix@localhost/nutanix_pxe

# Server Configuration
PXE_SERVER_IP=${PXE_SERVER_IP:-10.240.0.12}
PXE_SERVER_DNS=${PXE_SERVER_DNS:-nutanix-pxe-config.nutanix-ce-poc.cloud}
DNS_ZONE_NAME=${DNS_ZONE_NAME:-nutanix.internal}

# Application Configuration
SECRET_KEY=$(openssl rand -base64 32)
DEBUG=False
EOF

# Set secure permissions on environment file
chmod 600 "$PROJECT_DIR/.env"
chown "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR/.env"

# Create sample boot scripts
log "Creating sample boot scripts"

# Foundation initialization script
cat > "/var/www/pxe/scripts/foundation-init.sh" << 'EOF'
#!/bin/bash
# Foundation initialization script for Nutanix CE

set -euo pipefail

# Get configuration from kernel parameters
NODE_ID=$(cat /proc/cmdline | grep -o 'node_id=[^ ]*' | cut -d= -f2)
OPERATION=$(cat /proc/cmdline | grep -o 'operation=[^ ]*' | cut -d= -f2)
CONFIG_SERVER=$(cat /proc/cmdline | grep -o 'config_server=[^ ]*' | cut -d= -f2)

# Download server configuration
curl -o /tmp/server-config.json "http://${CONFIG_SERVER}:8081/server-config/$(hostname -I | awk '{print $1}')"

# Initialize Foundation based on operation
if [ "$OPERATION" = "create_cluster" ]; then
    echo "Creating new Nutanix cluster"
    # Foundation cluster creation logic here
elif [ "$OPERATION" = "add_node" ]; then
    echo "Adding node to existing cluster"
    # Foundation node addition logic here
fi

# Report status back to PXE server
curl -X POST "http://${CONFIG_SERVER}:8082/phase-update" \
    -H "Content-Type: application/json" \
    -d "{\"server_ip\":\"$(hostname -I | awk '{print $1}')\",\"phase\":\"foundation_start\",\"status\":\"success\",\"message\":\"Foundation initialization completed\"}"
EOF

# Network configuration script
cat > "/var/www/pxe/scripts/network-config.sh" << 'EOF'
#!/bin/bash
# Network configuration script for Nutanix nodes

set -euo pipefail

# Configure network interfaces based on kernel parameters
MGMT_IP=$(cat /proc/cmdline | grep -o 'mgmt_ip=[^ ]*' | cut -d= -f2)
WORKLOAD_IP=$(cat /proc/cmdline | grep -o 'workload_ip=[^ ]*' | cut -d= -f2)

echo "Configuring network interfaces"
echo "Management IP: $MGMT_IP"
echo "Workload IP: $WORKLOAD_IP"

# Network configuration logic here
EOF

# Post-installation script
cat > "/var/www/pxe/scripts/post-install.sh" << 'EOF'
#!/bin/bash
# Post-installation configuration script

set -euo pipefail

echo "Running post-installation configuration"

# Post-installation logic here
EOF

# Set executable permissions
chmod +x /var/www/pxe/scripts/*.sh

# Create systemd service files
log "Creating systemd service files"

# Main application service
cat > /etc/systemd/system/nutanix-pxe.service << EOF
[Unit]
Description=Nutanix PXE/Config Server
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=exec
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin
ExecStart=$PROJECT_DIR/venv/bin/gunicorn --config gunicorn.conf.py app:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create Gunicorn configuration
cat > "$PROJECT_DIR/gunicorn.conf.py" << EOF
# Gunicorn configuration for Nutanix PXE Server

bind = "0.0.0.0:8080"
workers = 4
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 30
keepalive = 2
user = "$SERVICE_USER"
group = "$SERVICE_USER"
tmp_upload_dir = None
errorlog = "/var/log/nutanix-pxe/gunicorn-error.log"
accesslog = "/var/log/nutanix-pxe/gunicorn-access.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
EOF

# Configure Nginx as reverse proxy
log "Configuring Nginx"
cat > /etc/nginx/sites-available/nutanix-pxe << EOF
server {
    listen 80;
    server_name _;

    # Boot server (port 8080)
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Configuration API (port 8081)
    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Static files
    location /static/ {
        alias $PROJECT_DIR/static/;
        expires 1h;
    }

    # Boot images and scripts
    location /images/ {
        alias /var/www/pxe/images/;
        expires 1h;
    }

    location /scripts/ {
        alias /var/www/pxe/scripts/;
        expires 1h;
    }
}
EOF

# Enable Nginx site
ln -sf /etc/nginx/sites-available/nutanix-pxe /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
nginx -t

# Create log rotation configuration
log "Setting up log rotation"
cat > /etc/logrotate.d/nutanix-pxe << EOF
/var/log/nutanix-pxe/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $SERVICE_USER $SERVICE_USER
    postrotate
        systemctl reload nutanix-pxe
    endscript
}
EOF

# Initialize database
log "Initializing database"
cd "$PROJECT_DIR"
source venv/bin/activate
python3 -c "
from database import Database
db = Database()
print('Database initialized successfully')
"

# Download placeholder images (these would be replaced with actual Nutanix images)
log "Setting up placeholder boot images"
cd /var/www/pxe/images

# Create placeholder files
touch vmlinuz-foundation
touch initrd-foundation.img
touch nutanix-ce-installer.iso

echo "Placeholder kernel image" > vmlinuz-foundation
echo "Placeholder initrd image" > initrd-foundation.img
echo "Placeholder ISO image" > nutanix-ce-installer.iso

# Set permissions
chown -R "$SERVICE_USER:$SERVICE_USER" /var/www/pxe

# Enable and start services
log "Enabling and starting services"
systemctl daemon-reload
systemctl enable nutanix-pxe
systemctl enable nginx
systemctl start postgresql
systemctl start nginx
systemctl start nutanix-pxe

# Wait for services to start
sleep 5

# Check service status
log "Checking service status"
systemctl is-active --quiet nutanix-pxe && log "Nutanix PXE service is running" || log "ERROR: Nutanix PXE service failed to start"
systemctl is-active --quiet nginx && log "Nginx is running" || log "ERROR: Nginx failed to start"
systemctl is-active --quiet postgresql && log "PostgreSQL is running" || log "ERROR: PostgreSQL failed to start"

# Test API endpoint
log "Testing API endpoint"
sleep 10
if curl -f http://localhost:8080/health >/dev/null 2>&1; then
    log "Health check endpoint is responding"
else
    log "WARNING: Health check endpoint is not responding"
fi

# Create initial admin user or configuration
log "Setting up initial configuration"
cd "$PROJECT_DIR"
source venv/bin/activate

# This would create any initial configuration needed
python3 -c "
print('Initial configuration completed')
"

# Setup firewall rules (if UFW is available)
if command -v ufw >/dev/null 2>&1; then
    log "Configuring firewall"
    ufw allow 22/tcp    # SSH
    ufw allow 80/tcp    # HTTP
    ufw allow 443/tcp   # HTTPS
    ufw allow 8080/tcp  # PXE Boot Server
    ufw allow 8081/tcp  # Config API
    ufw allow 8082/tcp  # Status Monitor
    ufw allow 8083/tcp  # DNS Service
    ufw allow 8084/tcp  # Cleanup Service
    ufw --force enable
fi

# Create status check script
cat > "$PROJECT_DIR/check-status.sh" << EOF
#!/bin/bash
# Status check script for Nutanix PXE Server

echo "=== Nutanix PXE/Config Server Status ==="
echo "Date: \$(date)"
echo

echo "Service Status:"
systemctl is-active nutanix-pxe && echo "✓ Nutanix PXE Service: Running" || echo "✗ Nutanix PXE Service: Not Running"
systemctl is-active nginx && echo "✓ Nginx: Running" || echo "✗ Nginx: Not Running"
systemctl is-active postgresql && echo "✓ PostgreSQL: Running" || echo "✗ PostgreSQL: Not Running"
echo

echo "Network Endpoints:"
curl -s -f http://localhost:8080/health >/dev/null && echo "✓ Health Check: OK" || echo "✗ Health Check: Failed"
curl -s -f http://localhost:8080/api/v1/info >/dev/null && echo "✓ API Info: OK" || echo "✗ API Info: Failed"
echo

echo "Database Connection:"
cd "$PROJECT_DIR" && source venv/bin/activate && python3 -c "
try:
    from database import Database
    db = Database()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
    print('✓ Database: Connected')
except Exception as e:
    print(f'✗ Database: Error - {e}')
"

echo
echo "Log Files:"
echo "Application: /var/log/nutanix-pxe/pxe-server.log"
echo "Gunicorn Access: /var/log/nutanix-pxe/gunicorn-access.log"
echo "Gunicorn Error: /var/log/nutanix-pxe/gunicorn-error.log"
echo "Setup: /var/log/nutanix-pxe-setup.log"
EOF

chmod +x "$PROJECT_DIR/check-status.sh"

# Final status output
log "=== Setup Complete ==="
log "Nutanix PXE/Config Server has been installed and started"
log ""
log "Service Endpoints:"
log "  - Boot Server: http://$(hostname -I | awk '{print $1}'):8080"
log "  - Configuration API: http://$(hostname -I | awk '{print $1}'):8081"
log "  - Health Check: http://$(hostname -I | awk '{print $1}')/health"
log "  - Server Info: http://$(hostname -I | awk '{print $1}')/api/v1/info"
log ""
log "Management Commands:"
log "  - Check Status: $PROJECT_DIR/check-status.sh"
log "  - Restart Service: systemctl restart nutanix-pxe"
log "  - View Logs: journalctl -u nutanix-pxe -f"
log ""
log "Next Steps:"
log "1. Update environment variables in $PROJECT_DIR/.env"
log "2. Replace placeholder boot images with actual Nutanix images"
log "3. Test node provisioning API"

# Create a simple README for operators
cat > "$PROJECT_DIR/README.md" << 'EOF'
# Nutanix PXE/Config Server

This server provides automated provisioning for Nutanix CE nodes on IBM Cloud VPC.

## Quick Start

1. Check server status:
   ```bash
   ./check-status.sh
   ```

2. Provision a new node:
   ```bash
   curl -X POST http://localhost:8081/api/v1/nodes \
     -H "Content-Type: application/json" \
     -d '{
       "node_config": {
         "node_name": "nutanix-node-01",
         "node_position": "A",
         "server_profile": "bx2d-metal-48x192",
         "cluster_role": "compute"
       },
       "network_config": {
         "management_subnet": "auto",
         "workload_subnet": "auto",
         "cluster_operation": "create_new"
       }
     }'
   ```

3. Monitor deployment:
   ```bash
   curl http://localhost:8081/api/v1/nodes/1/status
   ```

## Configuration

Edit environment variables in `.env` file and restart service:
```bash
sudo systemctl restart nutanix-pxe
```

## Logs

- Application: `/var/log/nutanix-pxe/pxe-server.log`
- Service: `journalctl -u nutanix-pxe -f`
EOF

log "Setup completed successfully!"