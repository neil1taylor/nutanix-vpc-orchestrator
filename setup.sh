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

build_initrd-vpc() {
    local work_dir="/tmp/nutanix-build-$(date +%s)"
    local output_dir="/var/www/pxe/images"
    
    log "Building initrd-vpc..."
    
    # Ensure output directory exists
    mkdir -p "$output_dir"
    
    # Create working directory
    mkdir -p "$work_dir"
    cd "$work_dir"
    
    # Extract original initrd
    log "Extracting original initrd..."
    # Handle both compressed and uncompressed initrd files
    if [[ ! -f "$output_dir/initrd.img" ]]; then
        log "ERROR: initrd.img not found at $output_dir/initrd.img"
        return 1
    fi
    
    if file "$output_dir/initrd.img" | grep -q "gzip"; then
        log "Extracting gzip compressed initrd..."
        if ! gunzip -c "$output_dir/initrd.img" | cpio -i -d -H newc --no-absolute-filenames; then
            log "ERROR: Failed to extract compressed initrd"
            return 1
        fi
    else
        log "Extracting uncompressed initrd..."
        if ! cat "$output_dir/initrd.img" | cpio -i -d -H newc --no-absolute-filenames; then
            log "ERROR: Failed to extract uncompressed initrd"
            return 1
        fi
    fi
    
    # Find and add ionic driver
    log "Locating ionic driver..."
    local ionic_driver=""
    for path in \
        "/lib/modules/$(uname -r)/kernel/drivers/net/ethernet/pensando/ionic/ionic.ko" \
        "/lib/modules/$(uname -r)/extra/ionic.ko" \
        "/lib/modules/$(uname -r)/updates/ionic.ko"; do
        if [ -f "$path" ]; then
            ionic_driver="$path"
            break
        fi
    done
    
    if [ -z "$ionic_driver" ]; then
        log "ERROR: Ionic driver not found on host system"
        exit 1
    fi
    
    log "Found ionic driver: $ionic_driver"
    
    # Add ionic driver to initrd
    local kernel_ver=$(uname -r)
    mkdir -p "./lib/modules/$kernel_ver/kernel/drivers/net/ethernet/pensando/ionic"
    cp "$ionic_driver" "./lib/modules/$kernel_ver/kernel/drivers/net/ethernet/pensando/ionic/"
    
    # Verify the driver was copied successfully
    if [[ ! -f "./lib/modules/$kernel_ver/kernel/drivers/net/ethernet/pensando/ionic/ionic.ko" ]]; then
        log "ERROR: Failed to copy ionic driver to initrd"
        return 1
    fi
    
    # Update modules.dep
    echo "kernel/drivers/net/ethernet/pensando/ionic/ionic.ko:" >> "./lib/modules/$kernel_ver/modules.dep"
    
    # Copy the vpc_init script to the $work_dir
    log "Copying vpc_init script to ${work_dir}..."
    if [[ -f "$PROJECT_DIR/vpc_init" ]]; then
        cp "$PROJECT_DIR/vpc_init" vpc_init
        chmod +x vpc_init
    else
        log "WARNING: vpc_init script not found at $PROJECT_DIR/vpc_init"
    fi

    # Copy the vpc_ce_installation.py script to the $work_dir
    log "Copying vpc_ce_installation.py script to ${work_dir}..."
    if [[ -f "$PROJECT_DIR/vpc_ce_installation.py" ]]; then
        # Create phoenix directory if it doesn't exist
        mkdir -p phoenix
        cp "$PROJECT_DIR/vpc_ce_installation.py" phoenix/vpc_ce_installation.py
        chmod +x phoenix/vpc_ce_installation.py
    else
        log "WARNING: vpc_ce_installation.py script not found at $PROJECT_DIR/vpc_ce_installation.py"
    fi

    # Repack initrd
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local output_file="$output_dir/initrd-ionic-$timestamp.img"
    
    log "Repacking initrd..."
    find . | cpio -o -H newc | gzip > "$output_file"
    
    # Create symlink
    cd "$output_dir"
    ln -sf "initrd-ionic-$timestamp.img" "initrd-vpc.img"
    
    # Verify integrity
    if gzip -t "$output_file"; then
        log "Ionic-enabled initrd created successfully: $(basename "$output_file")"
    else
        log "ERROR: Failed to create valid initrd"
        exit 1
    fi
    
    # Cleanup
    rm -rf "$work_dir"
}

test_result() {
    local test_name="$1" result="$2" message="$3" duration="${4:-0}"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    case "$result" in
        "PASS") echo -e "${GREEN}PASS${NC} $test_name (${duration}s): $message" ;;
        "FAIL") echo -e "${RED}FAIL${NC} $test_name (${duration}s): $message"; FAILED_TESTS=$((FAILED_TESTS + 1)) ;;
        "WARN") echo -e "${YELLOW}WARN${NC} $test_name (${duration}s): $message" ;;
        *) echo -e "${BLUE}INFO${NC} $test_name (${duration}s): $message" ;;
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
    
    local test_failures=0
    
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
        test_failures=$((test_failures + 1))
    fi
    
    # Database connectivity
    if sudo -u postgres psql -d nutanix_pxe -c "SELECT 1;" >/dev/null 2>&1; then
        test_result "Database Connection" "PASS" "PostgreSQL accessible" "1"
    else
        test_result "Database Connection" "FAIL" "Cannot connect to database" "1"
        test_failures=$((test_failures + 1))
    fi
    
    # Python environment
    if cd "$PROJECT_DIR" && sudo -u "$SERVICE_USER" bash -c "source venv/bin/activate && python3 -c 'import flask, psycopg2'" >/dev/null 2>&1; then
        test_result "Python Environment" "PASS" "Virtual environment and packages OK" "1"
    else
        test_result "Python Environment" "FAIL" "Virtual environment or packages missing" "1"
        test_failures=$((test_failures + 1))
    fi
    
    # Return overall status
    if [[ $test_failures -gt 0 ]]; then
        return 1
    else
        return 0
    fi
}

test_configuration() {
    log "Testing configuration..."
    
    local test_failures=0
    
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
        test_failures=$((test_failures + 1))
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
        test_failures=$((test_failures + 1))
    fi
    
    # Return overall status
    if [[ $test_failures -gt 0 ]]; then
        return 1
    else
        return 0
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
        # Check certificate validity
        if ! openssl x509 -in "$SSL_DIR/nutanix-orchestrator.crt" -noout -checkend 86400 >/dev/null 2>&1; then
            errors+=("cert expires soon")
        fi
        
        # Check certificate subject
        local cert_subject=$(openssl x509 -in "$SSL_DIR/nutanix-orchestrator.crt" -noout -subject 2>/dev/null)
        if [[ -z "$cert_subject" ]]; then
            errors+=("cert subject invalid")
        fi
        
        # Check if nginx is using the certificate
        if ! grep -q "$SSL_DIR/nutanix-orchestrator.crt" /etc/nginx/sites-enabled/nutanix-pxe 2>/dev/null; then
            errors+=("cert not used by nginx")
        fi
        
        # Verify HTTPS connection works (without -k flag)
        if ! curl -s --max-time 5 "https://localhost/health" >/dev/null 2>&1; then
            errors+=("HTTPS connection failed")
        fi
    fi
    
    if [[ ${#errors[@]} -eq 0 ]]; then
        test_result "SSL Configuration" "PASS" "Certificate valid and properly configured" "1"
    else
        test_result "SSL Configuration" "FAIL" "Issues: $(IFS=','; echo "${errors[*]}")" "1"
    fi
}

test_endpoints() {
    log "Testing API endpoints..."
    
    # Wait for services
    sleep 5
    
    local api_errors=0
    
    # Core endpoints
    test_http "Health Check" "http://localhost:8080/health" "200" 10 || api_errors=$((api_errors + 1))
    test_http "API Info" "http://localhost:8080/api/info" "200" 10 || api_errors=$((api_errors + 1))
    test_http "Web Interface" "http://localhost:8080/" "200" 10 || api_errors=$((api_errors + 1))
    test_http "Boot Config" "http://localhost:8080/boot/config?mgmt_ip=192.168.1.100&mgmt_mac=00:11:22:33:44:55" "200" 10 || api_errors=$((api_errors + 1))
    
    # HTTPS tests
    if [[ "$ENABLE_HTTPS" == "true" ]]; then
        # Test HTTP to HTTPS redirect
        test_http "HTTP Redirect" "http://localhost/" "301" 10 || api_errors=$((api_errors + 1))
        
        # Test HTTPS with certificate validation (no -k flag)
        local start_time=$(date +%s)
        local https_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://localhost/health" 2>/dev/null || echo "000")
        local duration=$(($(date +%s) - start_time))
        
        if [[ "$https_status" == "200" ]]; then
            test_result "HTTPS Endpoint (with cert validation)" "PASS" "HTTPS accessible with valid certificate" "$duration"
        else
            test_result "HTTPS Endpoint (with cert validation)" "FAIL" "HTTPS not accessible with valid certificate: HTTP $https_status" "$duration"
            api_errors=$((api_errors + 1))
        fi
        
        # Test HTTPS content
        local https_content=$(curl -k -s --max-time 10 "https://localhost/" 2>/dev/null)
        if [[ -z "$https_content" ]]; then
            test_result "HTTPS Content" "FAIL" "No content returned from HTTPS endpoint" "1"
            api_errors=$((api_errors + 1))
        elif ! echo "$https_content" | grep -q "Nutanix"; then
            test_result "HTTPS Content" "FAIL" "Invalid content returned from HTTPS endpoint" "1"
            api_errors=$((api_errors + 1))
        else
            test_result "HTTPS Content" "PASS" "Valid content returned from HTTPS endpoint" "1"
        fi
    fi
    
    # Return overall status
    if [[ $api_errors -gt 0 ]]; then
        return 1
    else
        return 0
    fi
}

test_static_files() {
    log "Testing static files..."
    
    local missing_files=()
    local invalid_files=()
    local required_files=(
        "/var/www/pxe/images/kernel"
        "/var/www/pxe/images/initrd-vpc.img"
        "/var/www/pxe/images/squashfs.img"
        "/var/www/pxe/images/nutanix_installer_package.tar.gz"
        "/var/www/pxe/images/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso"
    )
    
    # Check for missing files
    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            missing_files+=("$(basename "$file")")
            continue
        fi
        
        # Check file size (files should not be empty)
        local file_size=$(stat -c %s "$file" 2>/dev/null || echo "0")
        if [[ "$file_size" -lt 1024 ]]; then  # Less than 1KB
            invalid_files+=("$(basename "$file") (too small: ${file_size} bytes)")
            continue
        fi
        
        # Specific validation for each file type
        case "$(basename "$file")" in
            "kernel")
                # Check if it's a valid kernel file
                if ! file "$file" | grep -q "Linux kernel"; then
                    invalid_files+=("kernel (not a valid kernel file)")
                fi
                ;;
            "initrd-vpc.img")
                # Check if it's a valid initrd file (gzip compressed)
                if ! file "$file" | grep -q "gzip compressed data"; then
                    invalid_files+=("initrd-vpc.img (not a valid initrd file)")
                fi
                ;;
            "squashfs.img")
                # Check if it's a valid squashfs file
                if ! file "$file" | grep -q "Squashfs filesystem"; then
                    invalid_files+=("squashfs.img (not a valid squashfs file)")
                fi
                ;;
        esac
    done
    
    # Check if files are accessible via HTTP
    if curl -s --head --max-time 5 "http://localhost:8080/boot-images/kernel" | grep -q "200 OK"; then
        log "Kernel file is accessible via HTTP"
    else
        invalid_files+=("kernel (not accessible via HTTP)")
    fi
    
    if curl -s --head --max-time 5 "http://localhost:8080/boot-images/initrd-vpc.img" | grep -q "200 OK"; then
        log "Initrd file is accessible via HTTP"
    else
        invalid_files+=("initrd-vpc.img (not accessible via HTTP)")
    fi
    
    # Report results
    if [[ ${#missing_files[@]} -eq 0 && ${#invalid_files[@]} -eq 0 ]]; then
        test_result "Static Files" "PASS" "All PXE files present and valid" "1"
        return 0
    else
        local error_msg=""
        [[ ${#missing_files[@]} -gt 0 ]] && error_msg+="Missing: $(IFS=','; echo "${missing_files[*]}"). "
        [[ ${#invalid_files[@]} -gt 0 ]] && error_msg+="Invalid: $(IFS=','; echo "${invalid_files[*]}")."
        test_result "Static Files" "FAIL" "$error_msg" "1"
        return 1
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
        return 0
    else
        test_result "Network Connectivity" "FAIL" "Issues: $(IFS=','; echo "${issues[*]}")" "1"
        return 1
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
        postgresql postgresql-contrib jq \
        nginx git curl wget unzip gzip \
        bc netstat-nat openssl sshpass
}

setup_ssl() {
    if [[ "$ENABLE_HTTPS" != "true" ]]; then
        log "HTTPS disabled, skipping SSL setup"
        return 0
    fi
    
    log "Setting up SSL certificates..."
    
    # Ensure SSL directory exists with proper permissions
    if [[ ! -d "$SSL_DIR" ]]; then
        log "Creating SSL directory at $SSL_DIR"
        mkdir -p "$SSL_DIR" || {
            log "ERROR: Failed to create SSL directory at $SSL_DIR"
            return 1
        }
    fi
    
    # Verify service user exists
    if ! id "$SERVICE_USER" &>/dev/null; then
        log "ERROR: Service user $SERVICE_USER does not exist. Cannot set up SSL."
        return 1
    fi
    
    log "Generating self-signed certificate..."
    # Generate self-signed certificate with error handling
    if ! openssl req -x509 -newkey rsa:2048 -keyout "$SSL_DIR/nutanix-orchestrator.key" \
        -out "$SSL_DIR/nutanix-orchestrator.crt" -days 365 -nodes \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=$SSL_DOMAIN"; then
        log "ERROR: Failed to generate SSL certificate"
        return 1
    fi
    
    # Verify certificate files were created
    if [[ ! -f "$SSL_DIR/nutanix-orchestrator.crt" ]] || [[ ! -f "$SSL_DIR/nutanix-orchestrator.key" ]]; then
        log "ERROR: SSL certificate files were not created"
        return 1
    fi
    
    log "Setting permissions on SSL files..."
    chown -R "$SERVICE_USER:$SERVICE_USER" "$SSL_DIR"
    chmod 600 "$SSL_DIR/nutanix-orchestrator.key"
    chmod 644 "$SSL_DIR/nutanix-orchestrator.crt"
    
    log "SSL certificate successfully created at $SSL_DIR/nutanix-orchestrator.crt"
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
        # Verify SSL certificates exist before configuring HTTPS
        if [[ ! -f "$SSL_DIR/nutanix-orchestrator.crt" ]] || [[ ! -f "$SSL_DIR/nutanix-orchestrator.key" ]]; then
            log "ERROR: SSL certificates not found. Falling back to HTTP-only configuration."
            ENABLE_HTTPS="false"
        else
            log "SSL certificates found. Configuring HTTPS."
        fi
    fi
    
    if [[ "$ENABLE_HTTPS" == "true" ]]; then
        log "Creating HTTPS Nginx configuration..."
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
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90;
        proxy_connect_timeout 90;
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
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90;
        proxy_connect_timeout 90;
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
    
    # Download Nutanix ISO if not exists
    if [[ ! -f "/tmp/nutanix-ce.iso" ]]; then
        log "Downloading Nutanix CE ISO..."
        cd /tmp
        wget -q -O nutanix-ce.iso "$NUTANIX_ISO_URL" || {
            log "Warning: Could not download Nutanix ISO"
            exit 0
        }
    else
        log "Nutanix CE ISO already downloaded to /tmp"
    fi
    
    # Extract boot files
    INITRD_TMP_DIR="/tmp/nutanix-initrd-extracted"
    log "Making directories /mnt and ${INITRD_TMP_DIR}"
    
    # Clean up existing directory to avoid cpio conflicts
    if [ -d "$INITRD_TMP_DIR" ]; then
        log "Cleaning up existing extraction directory"
        rm -rf "$INITRD_TMP_DIR"
    fi
    
    mkdir -p "$INITRD_TMP_DIR"
    mkdir -p /mnt
    
    # Mount ISO first
    log "Mounting the nutanix-ce.iso to /mnt..."
    mount -o loop /tmp/nutanix-ce.iso /mnt || {
        log "Warning: Could not mount ISO"
        return 0
    }
    
    cd "$INITRD_TMP_DIR"
    
    # Ensure the output directory exists
    mkdir -p /var/www/pxe/images
    
    # Copy the initrd.img from ISO before building the VPC version
    log "Copying initrd.img from ISO to /var/www/pxe/images..."
    if [[ -f "/mnt/boot/initrd.img" ]]; then
        cp /mnt/boot/initrd.img /var/www/pxe/images/
        log "Copied /mnt/boot/initrd.img to /var/www/pxe/images/"
    elif [[ -f "/mnt/boot/initrd" ]]; then
        cp /mnt/boot/initrd /var/www/pxe/images/initrd.img
        log "Copied /mnt/boot/initrd to /var/www/pxe/images/initrd.img"
    else
        log "ERROR: Could not find initrd.img in the ISO"
        exit 1
    fi
    
    # Now build the VPC version with the ionic driver
    if ! build_initrd-vpc; then
        log "ERROR: Failed to build initrd-vpc"
        exit 1
    fi
    
    cd /tmp

    # Clean up temporary directory
    #log "Clean up temporary directory by removing ${INITRD_TMP_DIR}"
    #rm -rf "$INITRD_TMP_DIR"

    # Copy files
    log "Copying the static files to /var/www/pxe/images only if they don't exist"
        if [[ ! -f "/var/www/pxe/images/kernel" ]]; then
            log "Copying the file kernel to /var/www/pxe/images..."
            cp /mnt/boot/kernel /var/www/pxe/images
        else
            log "Skipping file copy, kernel is already in /var/www/pxe/images "
        fi
        if [[ ! -f "/var/www/pxe/images/squashfs.img" ]]; then
            log "Copying the file squashfs.img to /var/www/pxe/images..."
            cp /mnt/squashfs.img /var/www/pxe/images
        else
            log "Skipping file copy, squashfs.img is already in /var/www/pxe/images "
        fi
        if [[ ! -f "/var/www/pxe/images/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso" ]]; then
            log "Copying the file AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso to /var/www/pxe/images..."
            cp /mnt/images/hypervisor/kvm/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso /var/www/pxe/images
        else
            log "Skipping file copy, AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso is already in /var/www/pxe/images "
        fi

    # Copy split installer parts
    if [[ ! -f "/var/www/pxe/images/nutanix_installer_package.tar.gz" ]]; then
        log "Copying file nutanix_installer_package.tar.gz to /var/www/pxe/images..."
        cp /mnt/images/svm/nutanix_installer_package.tar.p* /var/www/pxe/images

        # Reconstruct complete installer
        cd /var/www/pxe/images
        cat nutanix_installer_package.tar.p* > nutanix_installer_package.tar.gz
        rm nutanix_installer_package.tar.p*
    else
        log "Skipping file copy, nutanix_installer_package.tar.gz is already in /var/www/pxe/images"
    fi

    cd /tmp

    log "Unmounting /mnt"
    umount /mnt 2>/dev/null || true
    
    # Calculate and store MD5 checksums for boot files
    log "Calculating MD5 checksums for boot files..."
    CHECKSUMS_FILE="/var/www/pxe/images/checksums.json"
    
    # Create checksums JSON file
    echo "{" > "$CHECKSUMS_FILE"
    
    # Calculate MD5 for kernel
    if [[ -f "/var/www/pxe/images/kernel" ]]; then
        KERNEL_MD5=$(md5sum /var/www/pxe/images/kernel | cut -d ' ' -f 1)
        echo "  \"kernel\": \"$KERNEL_MD5\"," >> "$CHECKSUMS_FILE"
        log "Kernel MD5: $KERNEL_MD5"
    fi
    
    # Calculate MD5 for modified initrd
    if [[ -f "/var/www/pxe/images/initrd-vpc.img" ]]; then
        INITRD_MODIFIED_MD5=$(md5sum /var/www/pxe/images/initrd-vpc.img | cut -d ' ' -f 1)
        echo "  \"initrd-vpc.img\": \"$INITRD_MODIFIED_MD5\"," >> "$CHECKSUMS_FILE"
        log "Modified Initrd MD5: $INITRD_MODIFIED_MD5"
    fi
    
    # Calculate MD5 for squashfs
    if [[ -f "/var/www/pxe/images/squashfs.img" ]]; then
        SQUASHFS_MD5=$(md5sum /var/www/pxe/images/squashfs.img | cut -d ' ' -f 1)
        echo "  \"squashfs.img\": \"$SQUASHFS_MD5\"," >> "$CHECKSUMS_FILE"
        log "Squashfs MD5: $SQUASHFS_MD5"
    fi
    
    # Calculate MD5 for AHV ISO
    if [[ -f "/var/www/pxe/images/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso" ]]; then
        # For large files, just store the file size instead of calculating MD5
        AHV_SIZE=$(stat -c %s /var/www/pxe/images/AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso)
        echo "  \"AHV-DVD-x86_64-el8.nutanix.20230302.101026.iso.iso\": \"size_$AHV_SIZE\"," >> "$CHECKSUMS_FILE"
        log "AHV ISO Size: $AHV_SIZE bytes"
    fi
    
    # Calculate MD5 for installer package
    if [[ -f "/var/www/pxe/images/nutanix_installer_package.tar.gz" ]]; then
        # For large files, just store the file size instead of calculating MD5
        INSTALLER_SIZE=$(stat -c %s /var/www/pxe/images/nutanix_installer_package.tar.gz)
        echo "  \"nutanix_installer_package.tar.gz\": \"size_$INSTALLER_SIZE\"" >> "$CHECKSUMS_FILE"
        log "Installer Package Size: $INSTALLER_SIZE bytes"
    fi
    
    # Close the JSON file
    echo "}" >> "$CHECKSUMS_FILE"
    
    log "MD5 checksums saved to $CHECKSUMS_FILE"
    
    log "Changing ownership of /var/www/pxe to ${SERVICE_USER}:${SERVICE_USER}"
    chown -R "$SERVICE_USER:$SERVICE_USER" /var/www/pxe
}

setup_systemd_service() {
    log "Creating systemd service..."
    
    # Check if service user exists
    if ! id "$SERVICE_USER" &>/dev/null; then
        log "ERROR: Service user $SERVICE_USER does not exist. Cannot create systemd service."
        return 1
    fi
    
    # Create systemd service file
    if ! cat > /etc/systemd/system/nutanix-pxe.service << EOF
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
    then
        log "ERROR: Failed to create systemd service file"
        return 1
    fi

    # Create tmpfiles.d configuration for runtime directory
    if ! cat > /etc/tmpfiles.d/nutanix-pxe.conf << EOF
d /var/run/nutanix-pxe 0755 $SERVICE_USER $SERVICE_USER - -
EOF
    then
        log "ERROR: Failed to create tmpfiles.d configuration"
        return 1
    fi

    # Reload systemd and enable service
    if ! systemctl daemon-reload; then
        log "ERROR: Failed to reload systemd daemon"
        return 1
    fi
    
    if ! systemctl enable nutanix-pxe; then
        log "ERROR: Failed to enable nutanix-pxe service"
        return 1
    fi
    
    log "Systemd service successfully configured"
    return 0
}

create_utilities() {
    log "Enabling utility scripts..."
    
    # Check if service user exists
    if ! id "$SERVICE_USER" &>/dev/null; then
        log "ERROR: Service user $SERVICE_USER does not exist. Cannot set up utility scripts."
        return 1
    fi
    
    # Check if project directory exists
    if [[ ! -d "$PROJECT_DIR/scripts" ]]; then
        log "ERROR: Scripts directory $PROJECT_DIR/scripts does not exist"
        return 1
    fi
    
    local script_errors=0
    local scripts=(
        "check-status.sh"
        "run-tests.sh"
        "post-install.sh"
        "reset-database.sh"
    )
    
    for script in "${scripts[@]}"; do
        if [[ -f "$PROJECT_DIR/scripts/$script" ]]; then
            if ! chmod +x "$PROJECT_DIR/scripts/$script"; then
                log "ERROR: Failed to make $script executable"
                script_errors=$((script_errors + 1))
            fi
            
            if ! chown "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR/scripts/$script"; then
                log "ERROR: Failed to set ownership of $script"
                script_errors=$((script_errors + 1))
            fi
        else
            log "WARNING: Script $script not found in $PROJECT_DIR/scripts"
        fi
    done
    
    if [[ $script_errors -gt 0 ]]; then
        log "WARNING: Encountered $script_errors errors while setting up utility scripts"
        return 1
    fi
    
    log "Utility scripts successfully configured"
    return 0
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    log "Starting optimized Nutanix PXE/Config Server setup"
    echo "Test run started at $(date)" > "$TEST_LOG"
    
    # Setup phase with error handling
    log "Setting up system packages..."
    if ! setup_system; then
        log "WARNING: System setup encountered issues, but continuing..."
    fi
    
    log "Setting up user and directories..."
    if ! setup_user_and_directories; then
        log "ERROR: Failed to set up user and directories. Exiting."
        exit 1
    fi
    
    log "Setting up SSH keys..."
    if ! setup_ssh_keys; then
        log "WARNING: SSH key setup encountered issues, but continuing..."
    fi
    
    log "Setting up SSL certificates..."
    if ! setup_ssl; then
        log "WARNING: SSL setup failed. HTTPS will be disabled."
        ENABLE_HTTPS="false"
    fi
    
    log "Setting up Python environment..."
    if ! setup_python; then
        log "WARNING: Python setup encountered issues, but continuing..."
    fi
    
    log "Setting up database..."
    if ! setup_database; then
        log "ERROR: Database setup failed. Exiting."
        exit 1
    fi
    
    log "Setting up Nginx..."
    if ! setup_nginx; then
        log "WARNING: Nginx setup encountered issues, but continuing..."
    fi
    
    log "Setting up boot files..."
    if ! setup_boot_files; then
        log "WARNING: Boot files setup encountered issues, but continuing..."
    fi
    log "Setting up systemd service..."
    if ! setup_systemd_service; then
        log "WARNING: Systemd service setup encountered issues, but continuing..."
    fi
    
    log "Creating utility scripts..."
    if ! create_utilities; then
        log "WARNING: Utility scripts setup encountered issues, but continuing..."
    fi
    
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
    
    # Run tests and track failures
    local test_failures=0
    
    if ! test_system_health; then
        log "WARNING: System health test failed"
        test_failures=$((test_failures + 1))
    fi
    
    if ! test_configuration; then
        log "WARNING: Configuration test failed"
        test_failures=$((test_failures + 1))
    fi
    
    if ! test_ssl_config; then
        log "WARNING: SSL configuration test failed"
        test_failures=$((test_failures + 1))
    fi
    
    if ! test_endpoints; then
        log "WARNING: Endpoints test failed"
        test_failures=$((test_failures + 1))
    fi
    
    if ! test_static_files; then
        log "WARNING: Static files test failed"
        test_failures=$((test_failures + 1))
    fi
    
    if ! test_network; then
        log "WARNING: Network test failed"
        test_failures=$((test_failures + 1))
    fi
    
    # Results
    echo -e "\n${BLUE}==================== TEST SUMMARY ====================${NC}" | tee -a "$TEST_LOG"
    
    # Calculate total failures (both from test_result and test function returns)
    local total_failures=$((FAILED_TESTS + test_failures))
    
    # Ensure we don't double-count failures
    [[ $total_failures -gt $TOTAL_TESTS ]] && total_failures=$TOTAL_TESTS
    
    log "Test Summary: $(($TOTAL_TESTS - $total_failures))/$TOTAL_TESTS passed"
    
    if [[ $total_failures -eq 0 ]]; then
        echo -e "${GREEN}✓ ALL TESTS PASSED - System ready for production${NC}"
        log "Setup completed successfully"
    else
        echo -e "${RED}✗ $total_failures TESTS FAILED - Review and fix issues${NC}"
        log "Setup completed with $total_failures failed tests"
        exit 1  # Exit with error code to indicate test failures
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