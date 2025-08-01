# Nginx Configuration Implementation Plan

## Overview
This plan outlines the steps to implement an optimized Nginx reverse proxy configuration for the Nutanix VPC Orchestrator, consolidating the current multi-port setup into a single, efficient configuration.

## Implementation Phases

### Phase 1: Preparation and Backup
1. **Backup Current Configuration**
   - Backup existing Nginx configuration files
   - Document current port mappings and service endpoints
   - Create rollback procedure

2. **Environment Assessment**
   - Verify current Nginx version and modules
   - Check available disk space for logs and cache
   - Review current SSL certificate setup

3. **Stakeholder Communication**
   - Notify team of planned maintenance window
   - Document expected downtime
   - Prepare rollback plan

### Phase 2: Configuration Restructuring
1. **Create Modular Configuration Structure**
   ```bash
   # Create configuration directories
   sudo mkdir -p /etc/nginx/conf.d
   sudo mkdir -p /etc/nginx/snippets
   sudo mkdir -p /var/cache/nginx
   ```

2. **Implement Security Configuration**
   - Create `/etc/nginx/conf.d/security.conf` with security headers
   - Create `/etc/nginx/conf.d/ssl.conf` with SSL settings
   - Create `/etc/nginx/conf.d/gzip.conf` with compression settings

3. **Implement Performance Configuration**
   - Create `/etc/nginx/conf.d/proxy.conf` with proxy settings
   - Configure caching strategies
   - Set up rate limiting where appropriate

### Phase 3: Main Configuration Implementation
1. **Create Consolidated Site Configuration**
   - Create `/etc/nginx/sites-available/nutanix-pxe` with path-based routing
   - Implement service routing as defined in port consolidation plan
   - Configure static file serving for CSS, JS, and boot images

2. **SSL Configuration**
   - Update SSL certificate paths if needed
   - Implement SSL stapling
   - Configure strong cipher suites

3. **WebSocket Support**
   - Add WebSocket upgrade headers
   - Configure appropriate timeouts

### Phase 4: Testing and Validation
1. **Configuration Syntax Check**
   ```bash
   sudo nginx -t
   ```

2. **Staging Environment Testing**
   - Deploy to staging environment first
   - Test all endpoints and services
   - Validate static file serving
   - Verify SSL configuration

3. **Performance Testing**
   - Test response times
   - Verify caching is working
   - Check resource utilization

### Phase 5: Production Deployment
1. **Deployment Steps**
   - Schedule maintenance window
   - Stop current Nginx service
   - Deploy new configuration
   - Start Nginx service
   - Monitor logs for errors

2. **Post-Deployment Validation**
   - Verify all services are accessible
   - Test API endpoints
   - Check web interface functionality
   - Monitor performance metrics

## Detailed Configuration Changes

### 1. Main Site Configuration
```nginx
# /etc/nginx/sites-available/nutanix-pxe

# HTTPS Server Block
server {
    listen 443 ssl http2;
    server_name _;
    
    # SSL Configuration
    include /etc/nginx/conf.d/ssl.conf;
    
    # Security Headers
    include /etc/nginx/conf.d/security.conf;
    
    # Boot server endpoints
    location /boot/ {
        proxy_pass http://127.0.0.1:8080/boot/;
        include /etc/nginx/conf.d/proxy.conf;
        proxy_set_header Host $host;
    }
    
    # Configuration API endpoints
    location /api/config/ {
        proxy_pass http://127.0.0.1:8080/api/config/;
        include /etc/nginx/conf.d/proxy.conf;
        proxy_set_header Host $host;
    }
    
    # Status monitoring endpoints
    location /api/status/ {
        proxy_pass http://127.0.0.1:8080/api/status/;
        include /etc/nginx/conf.d/proxy.conf;
        proxy_set_header Host $host;
    }
    
    # DNS service endpoints
    location /api/dns/ {
        proxy_pass http://127.0.0.1:8080/api/dns/;
        include /etc/nginx/conf.d/proxy.conf;
        proxy_set_header Host $host;
    }
    
    # Cleanup service endpoints
    location /api/cleanup/ {
        proxy_pass http://127.0.0.1:8080/api/cleanup/;
        include /etc/nginx/conf.d/proxy.conf;
        proxy_set_header Host $host;
    }
    
    # Web interface
    location / {
        proxy_pass http://127.0.0.1:8080;
        include /etc/nginx/conf.d/proxy.conf;
        proxy_set_header Host $host;
    }
    
    # Static files
    location /static/ {
        alias /opt/nutanix-pxe/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        gzip on;
        gzip_vary on;
        gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
    }
    
    # Boot images and scripts
    location /boot-images/ {
        alias /var/www/pxe/images/;
        expires 1h;
        add_header Cache-Control "public";
    }
    
    location /boot-scripts/ {
        alias /var/www/pxe/scripts/;
        expires 1h;
        add_header Cache-Control "public";
    }
    
    # Health check endpoint
    location /health {
        access_log off;
        proxy_pass http://127.0.0.1:8080/health;
        proxy_set_header Host $host;
    }
    
    # Error pages
    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /var/www/html;
    }
}
```

### 2. Security Configuration
```nginx
# /etc/nginx/conf.d/security.conf

# Security Headers
add_header X-Frame-Options DENY;
add_header X-Content-Type-Options nosniff;
add_header X-XSS-Protection "1; mode=block";
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header Referrer-Policy "strict-origin-when-cross-origin";
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'";
```

### 3. SSL Configuration
```nginx
# /etc/nginx/conf.d/ssl.conf

# SSL Configuration
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
ssl_stapling on;
ssl_stapling_verify on;
```

### 4. Proxy Configuration
```nginx
# /etc/nginx/conf.d/proxy.conf

# Proxy Settings
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $server_name;

# WebSocket support
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
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
```

### 5. Gzip Configuration
```nginx
# /etc/nginx/conf.d/gzip.conf

# Gzip compression
gzip on;
gzip_vary on;
gzip_min_length 1024;
gzip_proxied any;
gzip_comp_level 6;
gzip_types
    text/plain
    text/css
    text/xml
    text/javascript
    application/json
    application/javascript
    application/xml+rss
    application/atom+xml
    image/svg+xml;
```

## Rollback Procedure
1. **In Case of Issues**
   - Stop Nginx service
   - Restore previous configuration files
   - Start Nginx service
   - Verify functionality

2. **Monitoring During Deployment**
   - Monitor Nginx error logs
   - Check access logs for errors
   - Monitor application logs
   - Watch system resources

## Timeline
- **Preparation**: 2 hours
- **Configuration Implementation**: 4 hours
- **Testing**: 3 hours
- **Production Deployment**: 1 hour
- **Post-Deployment Monitoring**: 2 hours

## Success Criteria
- All services accessible through single HTTPS endpoint
- Improved response times
- Proper SSL configuration
- Working static file serving
- No service interruptions
- Successful rollback capability

This implementation plan will result in a more efficient, secure, and maintainable Nginx configuration for the Nutanix VPC Orchestrator.