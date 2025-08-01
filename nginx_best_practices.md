# Nginx Reverse Proxy Best Practices Recommendations

## 1. Configuration Structure

### Modular Configuration
Organize Nginx configuration into modular files for better maintainability:
```
/etc/nginx/
├── nginx.conf              # Main configuration
├── sites-available/        # Site configurations
│   └── nutanix-pxe         # Main site configuration
├── sites-enabled/          # Symlinks to enabled sites
├── conf.d/                 # Additional configuration snippets
│   ├── security.conf       # Security headers
│   ├── ssl.conf            # SSL configuration
│   └── proxy.conf          # Proxy settings
└── snippets/               # Reusable configuration snippets
    ├── ssl-params          # SSL parameters
    └── proxy-params        # Proxy parameters
```

### Main Configuration (nginx.conf)
```nginx
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;

# Load dynamic modules
include /usr/share/nginx/modules/*.conf;

events {
    worker_connections 1024;
}

http {
    # Basic settings
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';
    
    access_log /var/log/nginx/access.log main;
    
    # Performance settings
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    
    # MIME types
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    # Security headers (global)
    include /etc/nginx/conf.d/security.conf;
    
    # SSL configuration
    include /etc/nginx/conf.d/ssl.conf;
    
    # Gzip compression
    include /etc/nginx/conf.d/gzip.conf;
    
    # Site configurations
    include /etc/nginx/sites-enabled/*;
}
```

## 2. Security Best Practices

### SSL/TLS Configuration
```nginx
# SSL Configuration (conf.d/ssl.conf)
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
ssl_stapling on;
ssl_stapling_verify on;
```

### Security Headers
```nginx
# Security Headers (conf.d/security.conf)
add_header X-Frame-Options DENY;
add_header X-Content-Type-Options nosniff;
add_header X-XSS-Protection "1; mode=block";
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header Referrer-Policy "strict-origin-when-cross-origin";
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'";
```

### Rate Limiting
```nginx
# Rate limiting
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=login:10m rate=1r/s;

server {
    # API rate limiting
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://backend;
    }
    
    # Login rate limiting
    location /login {
        limit_req zone=login burst=5 nodelay;
        proxy_pass http://backend;
    }
}
```

### Access Control
```nginx
# IP-based access control for sensitive endpoints
location /admin {
    allow 192.168.1.0/24;
    allow 10.0.0.0/8;
    deny all;
    proxy_pass http://backend;
}
```

## 3. Performance Optimization

### Caching Strategy
```nginx
# Static file caching
location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
    add_header Vary Accept-Encoding;
    try_files $uri =404;
}

# Dynamic content caching
location /api/status {
    proxy_cache_valid 200 30s;
    proxy_cache_valid 404 1m;
    proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
    proxy_cache_bypass $http_cache_control;
    add_header X-Cache-Status $upstream_cache_status;
    proxy_pass http://backend;
}
```

### Buffer Tuning
```nginx
# Proxy buffer settings (conf.d/proxy.conf)
proxy_buffering on;
proxy_buffer_size 128k;
proxy_buffers 4 256k;
proxy_busy_buffers_size 256k;
proxy_temp_file_write_size 256k;

# Timeouts
proxy_connect_timeout 60s;
proxy_send_timeout 60s;
proxy_read_timeout 60s;
proxy_redirect off;
```

### Gzip Compression
```nginx
# Gzip configuration
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

## 4. Load Balancing and High Availability

### Upstream Configuration
```nginx
# Upstream servers
upstream backend {
    least_conn;
    server 127.0.0.1:8080 weight=3 max_fails=3 fail_timeout=30s;
    server 127.0.0.1:8081 weight=2 max_fails=3 fail_timeout=30s;
    server 127.0.0.1:8082 weight=1 max_fails=3 fail_timeout=30s;
    
    # Health checks
    keepalive 32;
}

server {
    location / {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

### Health Checks
```nginx
# Active health checks (requires nginx-plus or nginx-module-njs)
location /health-check {
    access_log off;
    return 200 "healthy\n";
    add_header Content-Type text/plain;
}
```

## 5. Logging and Monitoring

### Structured Logging
```nginx
# Enhanced log format for better monitoring
log_format detailed '$remote_addr - $remote_user [$time_local] "$request" '
                   '$status $body_bytes_sent "$http_referer" '
                   '"$http_user_agent" "$http_x_forwarded_for" '
                   '$request_time $upstream_response_time $pipe';

access_log /var/log/nginx/access.log detailed;
```

### Error Handling
```nginx
# Custom error pages
error_page 400 401 403 404 /errors/40x.html;
error_page 500 502 503 504 /errors/50x.html;

location = /errors/40x.html {
    root /usr/share/nginx/html;
    internal;
}

location = /errors/50x.html {
    root /usr/share/nginx/html;
    internal;
}
```

## 6. Path-Based Routing

### Service Routing
```nginx
server {
    listen 443 ssl http2;
    server_name _;
    
    # Web interface
    location / {
        proxy_pass http://127.0.0.1:8080;
        include /etc/nginx/conf.d/proxy.conf;
        proxy_set_header Host $host;
    }
    
    # Boot service endpoints
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
}
```

## 7. WebSocket Support

### WebSocket Configuration
```nginx
location /ws {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;
}
```

## 8. Maintenance and Operations

### Health Check Endpoint
```nginx
# Health check endpoint (no logging)
location /health {
    access_log off;
    proxy_pass http://127.0.0.1:8080/health;
    proxy_set_header Host $host;
}
```

### Configuration Testing
```bash
# Test configuration syntax
nginx -t

# Reload configuration without downtime
nginx -s reload

# Check configuration
nginx -T
```

## 9. Security Considerations

### Request Size Limits
```nginx
# Limit request sizes
client_max_body_size 10M;
client_body_buffer_size 128k;
```

### Timeout Settings
```nginx
# Timeout settings for security
client_body_timeout 12;
client_header_timeout 12;
send_timeout 10;
```

### Hide Version Information
```nginx
# Hide nginx version
server_tokens off;
```

## 10. Monitoring and Metrics

### Stub Status Module
```nginx
location /nginx_status {
    stub_status on;
    access_log off;
    allow 127.0.0.1;
    deny all;
}
```

These best practices will help ensure a secure, performant, and maintainable Nginx reverse proxy configuration for the Nutanix VPC Orchestrator.