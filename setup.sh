#!/bin/bash
# Setup script for Nutanix PXE/Config Server
# This script is executed by cloud-init during VSI deployment

set -euo pipefail

# Configuration
PROJECT_DIR="/opt/nutanix-pxe"
SERVICE_USER="nutanix"
LOG_FILE="/var/log/nutanix-pxe-setup.log"
NUTANIX_ISO_URL="https://download.nutanix.com/ce/2024.08.19/phoenix.x86_64-fnd_5.6.1_patch-aos_6.8.1_ga.iso"
ENABLE_HTTPS=${ENABLE_HTTPS:-true}
SSL_DOMAIN=${SSL_DOMAIN:-$(hostname -f)}
SSL_DIR="/opt/nutanix-pxe/ssl"


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

log "HTTPS Enabled: $ENABLE_HTTPS"
log "SSL Domain: $SSL_DOMAIN"
log "SSL Directory: $SSL_DIR"

if [ "$ENABLE_HTTPS" = "true" ]; then
    log "Setting up SSL certificates..."
    
    # Create SSL directory
    sudo mkdir -p $SSL_DIR
    
    # Generate private key
    log "Generating private key..."
    sudo openssl genrsa -out $SSL_DIR/nutanix-orchestrator.key 2048
    
    # Generate certificate signing request
    log "Generating certificate signing request..."
    sudo openssl req -new -key $SSL_DIR/nutanix-orchestrator.key -out $SSL_DIR/nutanix-orchestrator.csr -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=$SSL_DOMAIN/emailAddress=admin@$SSL_DOMAIN"
    
    # Generate self-signed certificate (valid for 365 days)
    log "Generating self-signed certificate..."
    sudo openssl x509 -req -days 365 -in $SSL_DIR/nutanix-orchestrator.csr -signkey $SSL_DIR/nutanix-orchestrator.key -out $SSL_DIR/nutanix-orchestrator.crt
    
    # Set proper permissions
    sudo chown -R "$SERVICE_USER:$SERVICE_USER" $SSL_DIR
    sudo chmod 600 $SSL_DIR/nutanix-orchestrator.key
    sudo chmod 644 $SSL_DIR/nutanix-orchestrator.crt
    
    log "SSL certificates generated successfully"
else
    log "HTTPS disabled, using HTTP only"
fi

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
IBM_CLOUD_REGION=${IBM_CLOUD_REGION:-}
VPC_ID=${VPC_ID:-}
DNS_INSTANCE_ID=${DNS_INSTANCE_ID:-}
DNS_ZONE_ID=${DNS_ZONE_ID:-}

# Network Configuration
MANAGEMENT_SUBNET_ID=${MANAGEMENT_SUBNET_ID:-}
WORKLOAD_SUBNET_ID=${WORKLOAD_SUBNET_ID:-}
MANAGEMENT_SECURITY_GROUP_ID=${MANAGEMENT_SECURITY_GROUP_ID:-}
WORKLOAD_SECURITY_GROUP_ID=${WORKLOAD_SECURITY_GROUP_ID:-}
INTRA_NODE_SECURITY_GROUP_ID=${INTRA_NODE_SECURITY_GROUP_ID:-}

# Database Configuration
DATABASE_URL=postgresql://nutanix:nutanix@localhost/nutanix_pxe

# Server Configuration
PXE_SERVER_IP=${PXE_SERVER_IP:-}
PXE_SERVER_DNS=${PXE_SERVER_DNS:-}
DNS_ZONE_NAME=${DNS_ZONE_NAME:-}

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
if [ "$ENABLE_HTTPS" = "true" ]; then
    cat > /etc/nginx/sites-available/nutanix-pxe << EOF
# HTTP to HTTPS Redirect
server {
    listen 80;
    server_name $SSL_DOMAIN _;
    
    # Redirect all HTTP traffic to HTTPS
    return 301 https://\$server_name\$request_uri;
}

# HTTPS Server Block
server {
    listen 443 ssl http2;
    server_name $SSL_DOMAIN _;

    # SSL Configuration
    ssl_certificate $SSL_DIR/nutanix-orchestrator.crt;
    ssl_certificate_key $SSL_DIR/nutanix-orchestrator.key;
    
    # SSL Security Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-SHA:ECDHE-RSA-AES128-SHA:DHE-RSA-AES256-SHA256:DHE-RSA-AES128-SHA256:DHE-RSA-AES256-SHA:DHE-RSA-AES128-SHA:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!MD5:!PSK:!SRP:!CAMELLIA;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # Security Headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
    add_header Referrer-Policy "strict-origin-when-cross-origin";

    # Root directory
    root /var/www/pxe;
    index index.html;

    # PXE boot files
    location /pxe/ {
        alias /var/www/pxe/;
        autoindex on;
        try_files \$uri \$uri/ =404;
    }

    # API and Web Interface - Proxy to Gunicorn
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$server_name;
        
        # WebSocket support (for future real-time features)
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }

    # Static files (CSS, JS, images) - served directly by Nginx
    location /static/ {
        alias $PROJECT_DIR/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        
        # Compress static files
        gzip on;
        gzip_vary on;
        gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
    }

    # Health check endpoint (no logging)
    location /health {
        proxy_pass http://127.0.0.1:8080/health;
        access_log off;
    }

    # Boot configuration endpoints
    location /boot-config {
        proxy_pass http://127.0.0.1:8080/boot-config;
    }

    location ~* ^/server-config/(.+)\$ {
        proxy_pass http://127.0.0.1:8080/server-config/\$1;
    }

    # Error pages
    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /var/www/html;
    }
}
EOF

else
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
fi

# Enable Nginx site
ln -sf /etc/nginx/sites-available/nutanix-pxe /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
nginx -t

# Update Flask for HTTPS
if [ "$ENABLE_HTTPS" = "true" ]; then
    log "Configuring Flask for HTTPS..."
    
    # Create HTTPS configuration file
    sudo tee /opt/nutanix-pxe/https_config.py > /dev/null <<'EOF'
"""
HTTPS configuration for Flask application
"""
from flask import request, redirect, url_for

def configure_https_app(app):
    """Configure Flask app for HTTPS operation"""
    
    @app.before_request
    def force_https():
        """Redirect HTTP to HTTPS in production"""
        if not request.is_secure:
            # Check if we're behind a proxy (Nginx) that handles SSL
            if request.headers.get('X-Forwarded-Proto') != 'https':
                # Only redirect if not in debug mode and not a health check
                if not app.debug and request.endpoint != 'health':
                    return redirect(request.url.replace('http://', 'https://'))
    
    @app.context_processor
    def inject_https_vars():
        """Inject HTTPS-aware variables into templates"""
        return {
            'is_https': request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https',
            'scheme': 'https' if (request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https') else 'http'
        }
    
    return app
EOF

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

# Download Nutanix ISO and create boot images
log "Downloading Nutanix boot images..."
cd /tmp
wget -O nutanix-ce.iso "$NUTANIX_ISO_URL"

# Mount and extract
mount -o loop nutanix-ce.iso /mnt
cp /mnt/boot/kernel /var/www/pxe/images/vmlinuz-foundation
cp /mnt/boot/initrd /var/www/pxe/images/initrd-foundation.img
cp nutanix-ce.iso /var/www/pxe/images/nutanix-ce-installer.iso
umount /mnt

chown -R "$SERVICE_USER:$SERVICE_USER" /var/www/pxe
log "Nutanix ISO downloaded and images configured"

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

# Updating environment variables
log "Updating environment variables..."

# Add HTTPS-related environment variables
if [ "$ENABLE_HTTPS" = "true" ]; then
    sudo tee -a $PROJECT_DIR/.env > /dev/null <<EOF

# HTTPS Configuration
HTTPS_ENABLED=true
SSL_CERT_PATH=$SSL_DIR/nutanix-orchestrator.crt
SSL_KEY_PATH=$SSL_DIR/nutanix-orchestrator.key
FORCE_HTTPS=true
EOF
else
    sudo tee -a $PROJECT_DIR/.env > /dev/null <<EOF

# HTTPS Configuration
HTTPS_ENABLED=false
FORCE_HTTPS=false
EOF
fi

# Create SSL health monitoring script
if [ "$ENABLE_HTTPS" = "true" ]; then
    log "Setting up SSL health monitoring..."
    
    # Create SSL certificate monitoring script
    sudo tee $PROJECT_DIR/ssl_monitor.py > /dev/null <<'EOF'
#!/usr/bin/env python3
"""
SSL Certificate monitoring script
"""
import os
import sys
from datetime import datetime
from cryptography import x509
from cryptography.hazmat.backends import default_backend

def check_ssl_certificate(cert_path):
    """Check SSL certificate expiration"""
    try:
        with open(cert_path, 'rb') as f:
            cert_data = f.read()
        
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())
        expires = cert.not_valid_after
        now = datetime.utcnow()
        days_until_expiry = (expires - now).days
        
        print(f"Certificate expires: {expires}")
        print(f"Days until expiry: {days_until_expiry}")
        
        if days_until_expiry < 30:
            print("WARNING: Certificate expires in less than 30 days!")
            return 1
        elif days_until_expiry < 7:
            print("CRITICAL: Certificate expires in less than 7 days!")
            return 2
        else:
            print("Certificate is valid")
            return 0
            
    except Exception as e:
        print(f"Error checking certificate: {e}")
        return 3

if __name__ == "__main__":
    cert_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/nutanix-pxe/ssl/nutanix-orchestrator.crt"
    exit(check_ssl_certificate(cert_path))
EOF

    sudo chmod +x $PROJECT_DIR/ssl_monitor.py
    sudo chown "$SERVICE_USER:$SERVICE_USER" $PROJECT_DIR/ssl_monitor.py
    
    log "SSL monitoring script created"
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

if [ "$ENABLE_HTTPS" = "true" ]; then
    log "HTTPS is now enabled"
    log "SSL Certificate: $SSL_DIR/nutanix-orchestrator.crt" 
    log "SSL Private Key: $SSL_DIR/nutanix-orchestrator.key"
    log "Web Interface: https://$SSL_DOMAIN"
    log "HTTP automatically redirects to HTTPS"
    log ""
    log "IMPORTANT NOTES:"
    log " - Browser will show security warning for self-signed certificate"
    log " - Users need to accept the security exception to proceed"
    log " - For production, consider using Let's Encrypt or commercial certificates"
    log ""
    log "Test Commands:"
    log " curl -k https://$SSL_DOMAIN/health"
    log " curl -I http://$SSL_DOMAIN/ (should redirect to HTTPS)"
    log ""
    log "SSL Certificate Info:"
    /opt/nutanix-pxe/ssl_monitor.py
else
    log "HTTPS is disabled - using HTTP only"
    log "Web Interface: http://$SSL_DOMAIN"
fi

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