#!/bin/bash
# Optimized Setup script for Nutanix PXE/Config Server
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

# Test configuration
TEST_LOG="/var/log/nutanix-pxe-tests.log"
FAILED_TESTS=0
TOTAL_TESTS=0

# Colors for output
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

# ============================================================================
# CORE FUNCTIONS
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

test_result() {
    local test_name="$1" result="$2" message="$3" duration="${4:-0}"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    case "$result" in
        "PASS") echo -e "${GREEN}✓ PASS${NC} $test_name (${duration}s): $message" ;;
        "FAIL") echo -e "${RED}✗ FAIL${NC} $test_name (${duration}s): $message"; FAILED_TESTS=$((FAILED_TESTS + 1)) ;;
        "WARN") echo -e "${YELLOW}⚠ WARN${NC} $test_name (${duration}s): $message" ;;
        *) echo -e "${BLUE}ℹ INFO${NC} $test_name (${duration}s): $message" ;;
    esac | tee -a "${TEST_LOG}"
}

run_test() {
    local test_name="$1" test_command="$2" timeout="${3:-30}"
    local start_time=$(date +%s)
    
    if timeout "$timeout" bash -c "$test_command" >/dev/null 2>&1; then
        local duration=$(($(date +%s) - start_time))
        test_result "$test_name" "PASS" "Command completed successfully" "$duration"
        return 0
    else
        local exit_code=$? duration=$(($(date +%s) - start_time))
        local msg="Command failed with exit code $exit_code"
        [[ $exit_code -eq 124 ]] && msg="Test timed out after ${timeout}s"
        test_result "$test_name" "FAIL" "$msg" "$duration"
        return 1
    fi
}

test_http() {
    local name="$1" url="$2" expected="${3:-200}" timeout="${4:-10}"
    local start_time=$(date +%s)
    
    local status=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$timeout" "$url" 2>/dev/null || echo "000")
    local duration=$(($(date +%s) - start_time))
    
    if [[ "$status" == "$expected" ]]; then
        test_result "$name" "PASS" "HTTP $status" "$duration"
        return 0
    else
        test_result "$name" "FAIL" "HTTP $status (expected $expected)" "$duration"
        return 1
    fi
}

# ============================================================================
# CONSOLIDATED TEST FUNCTIONS
# ============================================================================

test_system_health() {
    log "Testing system health..."
    
    # Service status
    local services=("postgresql" "nginx" "nutanix-pxe")
    local failed_services=()
    
    for service in "${services[@]}"; do
        if ! systemctl is-active --quiet "$service" 2>/dev/null; then
            failed_services+=("$service")
        fi
    done
    
    if [[ ${#failed_services[@]} -eq 0 ]]; then
        test_result "System Services" "PASS" "All services running" "1"
    else
        test_result "System Services" "FAIL" "Failed: $(IFS=','; echo "${failed_services[*]}")" "1"
    fi
    
    # Database connectivity
    if sudo -u postgres psql -d nutanix_pxe -c "SELECT 1;" >/dev/null 2>&1; then
        test_result "Database Connection" "PASS" "PostgreSQL accessible" "1"
    else
        test_result "Database Connection" "FAIL" "Cannot connect to database" "1"
    fi
    
    # Python environment
    if cd "$PROJECT_DIR" && sudo -u "$SERVICE_USER" bash -c "source venv/bin/activate && python3 -c 'import flask, psycopg2'" >/dev/null 2>&1; then
        test_result "Python Environment" "PASS" "Virtual environment and packages OK" "1"
    else
        test_result "Python Environment" "FAIL" "Virtual environment or packages missing" "1"
    fi
}

test_configuration() {
    log "Testing configuration..."
    
    # Environment variables
    local required_vars=("IBM_CLOUD_REGION" "VPC_ID" "DNS_INSTANCE_ID" "DNS_INSTANCE_GUID" "DNS_ZONE_ID")
    local missing_vars=()
    
    if [[ -f "/etc/profile.d/app-vars.sh" ]]; then
        source /etc/profile.d/app-vars.sh
        for var in "${required_vars[@]}"; do
            [[ -z "${!var:-}" ]] && missing_vars+=("$var")
        done
    else
        missing_vars=("${required_vars[@]}")
    fi
    
    if [[ ${#missing_vars[@]} -eq 0 ]]; then
        test_result "Environment Variables" "PASS" "All required variables set" "1"
    else
        test_result "Environment Variables" "FAIL" "Missing: $(IFS=','; echo "${missing_vars[*]}")" "1"
    fi
    
    # File permissions
    local errors=()
    local paths=("$PROJECT_DIR:755" "/var/www/pxe:755" "/var/log/nutanix-pxe:755")
    
    for path_perm in "${paths[@]}"; do
        local path="${path_perm%:*}"
        if [[ ! -e "$path" ]]; then
            errors+=("$path missing")
        elif [[ ! -r "$path" ]] || [[ ! -w "$path" ]]; then
            errors+=("$path permissions")
        fi
    done
    
    if [[ ${#errors[@]} -eq 0 ]]; then
        test_result "File Permissions" "PASS" "All paths accessible" "1"
    else
        test_result "File Permissions" "FAIL" "Issues: $(IFS=','; echo "${errors[*]}")" "1"
    fi
}

test_ssl_config() {
    if [[ "$ENABLE_HTTPS" != "true" ]]; then
        test_result "SSL Configuration" "SKIP" "HTTPS disabled" "0"
        return 0
    fi
    
    local errors=()
    
    # Check certificate files
    [[ ! -f "$SSL_DIR/nutanix-orchestrator.crt" ]] && errors+=("cert missing")
    [[ ! -f "$SSL_DIR/nutanix-orchestrator.key" ]] && errors+=("key missing")
    
    # Validate certificate
    if [[ -f "$SSL_DIR/nutanix-orchestrator.crt" ]]; then
        if ! openssl x509 -in "$SSL_DIR/nutanix-orchestrator.crt" -noout -checkend 86400 >/dev/null 2>&1; then
            errors+=("cert expires soon")
        fi
    fi
    
    if [[ ${#errors[@]} -eq 0 ]]; then
        test_result "SSL Configuration" "PASS" "Certificate valid" "1"
    else
        test_result "SSL Configuration" "FAIL" "Issues: $(IFS=','; echo "${errors[*]}")" "1"
    fi
}

test_endpoints() {
    log "Testing API endpoints..."
    
    # Wait for services
    sleep 5
    
    # Core endpoints
    test_http "Health Check" "http://localhost:8080/health" "200" 10
    test_http "API Info" "http://localhost:8080/api/info" "200" 10
    test_http "Web Interface" "http://localhost:8080/" "200" 10
    test_http "Boot Config" "http://localhost:8080/boot/config?mgmt_ip=192.168.1.100&mgmt_mac=00:11:22:33:44:55" "200" 10
    
    # HTTPS tests
    if [[ "$ENABLE_HTTPS" == "true" ]]; then
        test_http "HTTP Redirect" "http://localhost/" "301" 10
        if curl -k -s --max-time 10 "https://localhost/health" >/dev/null 2>&1; then
            test_result "HTTPS Endpoint" "PASS" "HTTPS accessible" "1"
        else
            test_result "HTTPS Endpoint" "FAIL" "HTTPS not accessible" "1"
        fi
    fi
}

test_static_files() {
    log "Testing static files..."
    
    local missing_files=()
    local required_files=(
        "/var/www/pxe/images/vmlinuz-foundation"
        "/var/www/pxe/images/initrd-foundation.img"
        "/var/www/pxe/scripts/foundation-init.sh"
    )
    
    for file in "${required_files[@]}"; do
        [[ ! -f "$file" ]] && missing_files+=("$(basename "$file")")
    done
    
    if [[ ${#missing_files[@]} -eq 0 ]]; then
        test_result "Static Files" "PASS" "All PXE files present" "1"
    else
        test_result "Static Files" "FAIL" "Missing: $(IFS=','; echo "${missing_files[*]}")" "1"
    fi
}

test_network() {
    log "Testing network connectivity..."
    
    local issues=()
    
    # DNS resolution
    nslookup google.com >/dev/null 2>&1 || issues+=("DNS")
    
    # Outbound connectivity
    curl -s --max-time 10 https://httpbin.org/ip >/dev/null 2>&1 || issues+=("Internet")
    
    # Required ports
    local ports=("80" "443" "8080")
    for port in "${ports[@]}"; do
        netstat -tuln 2>/dev/null | grep -q ":$port " || issues+=("Port $port")
    done
    
    if [[ ${#issues[@]} -eq 0 ]]; then
        test_result "Network Connectivity" "PASS" "All network tests passed" "1"
    else
        test_result "Network Connectivity" "FAIL" "Issues: $(IFS=','; echo "${issues[*]}")" "1"
    fi
}

# ============================================================================
# SETUP FUNCTIONS
# ============================================================================

setup_system() {
    log "Setting up system packages..."
    
    apt-get update
    apt-get upgrade -y
    apt-get install -y \
        python3 python3-pip python3-venv \
        postgresql postgresql-contrib \
        nginx git curl wget unzip \
        bc netstat-nat openssl sshpass
}

setup_ssl() {
    if [[ "$ENABLE_HTTPS" != "true" ]]; then
        log "HTTPS disabled, skipping SSL setup"
        return 0
    fi
    
    log "Setting up SSL certificates..."
    mkdir -p "$SSL_DIR"
    
    # Generate self-signed certificate
    openssl req -x509 -newkey rsa:2048 -keyout "$SSL_DIR/nutanix-orchestrator.key" \
        -out "$SSL_DIR/nutanix-orchestrator.crt" -days 365 -nodes \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=$SSL_DOMAIN"
    
    chown -R "$SERVICE_USER:$SERVICE_USER" "$SSL_DIR"
    chmod 600 "$SSL_DIR/nutanix-orchestrator.key"
    chmod 644 "$SSL_DIR/nutanix-orchestrator.crt"
}

setup_user_and_directories() {
    log "Setting up user and directories..."
    
    # Create service user
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd -r -s /bin/bash -d "$PROJECT_DIR" "$SERVICE_USER"
    fi
    
    # Create directories
    mkdir -p "$PROJECT_DIR"/{logs,images,scripts,configs,static,templates}
    mkdir -p /var/www/pxe/{images,scripts,configs}
    mkdir -p /var/log/nutanix-pxe
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR" /var/www/pxe /var/log/nutanix-pxe
}

setup_ssh_keys() {
    log "Setting up SSH keys for $SERVICE_USER..."
    
    # Create .ssh directory for the service user
    sudo -u "$SERVICE_USER" mkdir -p "/home/$SERVICE_USER/.ssh"
    sudo -u "$SERVICE_USER" chmod 700 "/home/$SERVICE_USER/.ssh"
    
    # Generate SSH key pair if it doesn't exist
    if [[ ! -f "/home/$SERVICE_USER/.ssh/id_rsa" ]]; then
        sudo -u "$SERVICE_USER" ssh-keygen -t rsa -b 4096 -f "/home/$SERVICE_USER/.ssh/id_rsa" -N "" -C "nutanix-orchestrator@$(hostname)"
        log "SSH key pair generated for $SERVICE_USER"
    else
        log "SSH key pair already exists for $SERVICE_USER"
    fi
    
    # Set proper permissions
    sudo -u "$SERVICE_USER" chmod 600 "/home/$SERVICE_USER/.ssh/id_rsa"
    sudo -u "$SERVICE_USER" chmod 644 "/home/$SERVICE_USER/.ssh/id_rsa.pub"
    
    # Create authorized_keys file
    sudo -u "$SERVICE_USER" touch "/home/$SERVICE_USER/.ssh/authorized_keys"
    sudo -u "$SERVICE_USER" chmod 600 "/home/$SERVICE_USER/.ssh/authorized_keys"
}

setup_python() {
    log "Setting up Python environment..."
    
    cd "$PROJECT_DIR"
    sudo -u "$SERVICE_USER" python3 -m venv venv
    sudo -u "$SERVICE_USER" bash -c "
        cd '$PROJECT_DIR'
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
    "
}

setup_database() {
    log "Setting up PostgreSQL database..."
    
    sudo -u postgres createuser nutanix || true
    sudo -u postgres createdb nutanix_pxe -O nutanix || true
    sudo -u postgres psql -c "ALTER USER nutanix PASSWORD 'nutanix';" || true
    
    # Configure PostgreSQL access
    local pg_config="/etc/postgresql/14/main/pg_hba.conf"
    if [[ -f "$pg_config" ]] && ! grep -q "host nutanix_pxe nutanix 127.0.0.1/32 md5" "$pg_config"; then
        echo "host nutanix_pxe nutanix 127.0.0.1/32 md5" >> "$pg_config"
    fi
    
    systemctl restart postgresql
    systemctl enable postgresql
}

setup_nginx() {
    log "Configuring Nginx..."
    
    local nginx_config="/etc/nginx/sites-available/nutanix-pxe"
    
    if [[ "$ENABLE_HTTPS" == "true" ]]; then
        cat > "$nginx_config" << 'EOF'
server {
    listen 80;
    server_name _;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name _;
    
    ssl_certificate /opt/nutanix-pxe/ssl/nutanix-orchestrator.crt;
    ssl_certificate_key /opt/nutanix-pxe/ssl/nutanix-orchestrator.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /static/ {
        alias /opt/nutanix-pxe/static/;
        expires 1y;
    }
    
    location /boot-images/ {
        alias /var/www/pxe/images/;
        expires 1h;
    }
    
    location /boot-scripts/ {
        alias /var/www/pxe/scripts/;
        expires 1h;
    }
}
EOF
    else
        cat > "$nginx_config" << 'EOF'
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /static/ {
        alias /opt/nutanix-pxe/static/;
        expires 1y;
    }
    
    location /boot-images/ {
        alias /var/www/pxe/images/;
        expires 1h;
    }
    
    location /boot-scripts/ {
        alias /var/www/pxe/scripts/;
        expires 1h;
    }
}
EOF
    fi
    
    ln -sf "$nginx_config" /etc/nginx/sites-enabled
    rm -f /etc/nginx/sites-enabled/default
    nginx -t
    systemctl enable nginx
}

setup_boot_files() {
    log "Setting up boot files..."
    
    # Copy boot scripts
    cp $PROJECT_DIR/scripts/foundation-init.sh /var/www/pxe/scripts/foundation-init.sh

    # Set permissions
    chmod +x /var/www/pxe/scripts/*.sh
    
    # Download Nutanix ISO if not exists
    if [[ ! -f "/var/www/pxe/images/nutanix-ce-installer.iso" ]]; then
        log "Downloading Nutanix CE ISO..."
        cd /tmp
        wget -q -O nutanix-ce.iso "$NUTANIX_ISO_URL" || {
            log "Warning: Could not download Nutanix ISO, creating placeholder files"
            touch /var/www/pxe/images/{vmlinuz-foundation,initrd-foundation.img,nutanix-ce-installer.iso}
            return 0
        }
        
        # Extract boot files
        mount -o loop nutanix-ce.iso /mnt 2>/dev/null || {
            log "Warning: Could not mount ISO, creating placeholder files"
            touch /var/www/pxe/images/{vmlinuz-foundation,initrd-foundation.img,nutanix-ce-installer.iso}
            return 0
        }
        
        cp /mnt/boot/kernel /var/www/pxe/images/vmlinuz-foundation 2>/dev/null || true
        cp /mnt/boot/initrd /var/www/pxe/images/initrd-foundation.img 2>/dev/null || true
        cp nutanix-ce.iso /var/www/pxe/images/nutanix-ce-installer.iso
        
        umount /mnt 2>/dev/null || true
    fi
    
    chown -R "$SERVICE_USER:$SERVICE_USER" /var/www/pxe
}

setup_systemd_service() {
    log "Creating systemd service..."
    
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
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/etc/profile.d/app-vars.sh
ExecStartPre=/bin/bash -c 'set -a; source /etc/profile.d/app-vars.sh; set +a'
ExecStart=/bin/bash -c "set -a; source /etc/profile.d/app-vars.sh; exec $PROJECT_DIR/venv/bin/gunicorn --config $PROJECT_DIR/gunicorn.conf.py app:app"
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    # Create tmpfiles.d configuration for runtime directory
    cat > /etc/tmpfiles.d/nutanix-pxe.conf << EOF
d /var/run/nutanix-pxe 0755 $SERVICE_USER $SERVICE_USER - -
EOF

    systemctl daemon-reload
    systemctl enable nutanix-pxe
}

create_utilities() {
    log "Enabling utility scripts..."

    chmod +x "$PROJECT_DIR/scripts/check-status.sh"
    chown "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR/scripts/check-status.sh"

    chmod +x "$PROJECT_DIR/scripts/run-tests.sh"
    chown "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR/scripts/run-tests.sh"

    # Make post-install script executable
    chmod +x "$PROJECT_DIR/scripts/post-install.sh"
    chown "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR/scripts/post-install.sh"

    # Make network-config script executable
    chmod +x "$PROJECT_DIR/scripts/network-config.sh"
    chown "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR/scripts/network-config.sh"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    log "Starting optimized Nutanix PXE/Config Server setup"
    echo "Test run started at $(date)" > "$TEST_LOG"
    
    # Setup phase
    setup_system
    setup_user_and_directories
    setup_ssh_keys
    setup_ssl
    setup_python
    setup_database
    setup_nginx
    setup_boot_files
    setup_systemd_service
    create_utilities
    
    # Initialize database
    log "Initializing database..."
    cd "$PROJECT_DIR"
    sudo -u "$SERVICE_USER" bash -c "
        source venv/bin/activate
        python3 -c 'from database import Database; Database().initialize()' 2>/dev/null || echo 'Database initialization skipped (module not found)'
    "
    
    # Start services
    log "Starting services..."
    systemctl start postgresql nginx nutanix-pxe
    
    # Testing phase
    log "Running comprehensive tests..."
    echo -e "\n${BLUE}==================== TESTING PHASE ====================${NC}" | tee -a "$TEST_LOG"
    
    test_system_health
    test_configuration
    test_ssl_config
    test_endpoints
    test_static_files
    test_network
    
    # Results
    echo -e "\n${BLUE}==================== TEST SUMMARY ====================${NC}" | tee -a "$TEST_LOG"
    log "Test Summary: $((TOTAL_TESTS - FAILED_TESTS))/$TOTAL_TESTS passed"
    
    if [[ $FAILED_TESTS -eq 0 ]]; then
        echo -e "${GREEN}✓ ALL TESTS PASSED - System ready for production${NC}"
        log "Setup completed successfully"
    else
        echo -e "${RED}✗ $FAILED_TESTS TESTS FAILED - Review and fix issues${NC}"
        log "Setup completed with $FAILED_TESTS failed tests"
    fi
    
    # Final information
    echo
    log "Service endpoints:"
    log "  - Health: http://$(hostname -I | awk '{print $1}'):8080/health"
    log "  - API: http://$(hostname -I | awk '{print $1}'):8080/api/nfo"
    [[ "$ENABLE_HTTPS" == "true" ]] && log "  - Web: https://$SSL_DOMAIN"
    
    log "Utility scripts:"
    log "  - Status check: $PROJECT_DIR/check-status.sh"
    log "  - Run tests: $PROJECT_DIR/run-tests.sh"
    
    log "Log files:"
    log "  - Setup: $LOG_FILE"
    log "  - Tests: $TEST_LOG"
    log "  - Service: journalctl -u nutanix-pxe"
}

# Run main function
main "$@"