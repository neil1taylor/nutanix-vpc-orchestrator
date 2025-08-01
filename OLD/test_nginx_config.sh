#!/bin/bash

# Test script for Nginx configuration
echo "Testing Nginx configuration..."

# Test Nginx configuration syntax
echo "1. Testing Nginx configuration syntax..."
sudo nginx -t
if [ $? -ne 0 ]; then
    echo "ERROR: Nginx configuration test failed"
    exit 1
fi
echo "✓ Nginx configuration syntax is valid"

# Test if configuration files exist
echo "2. Checking configuration files..."
CONFIG_FILES=(
    "/etc/nginx/conf.d/security.conf"
    "/etc/nginx/conf.d/ssl.conf"
    "/etc/nginx/conf.d/proxy.conf"
    "/etc/nginx/conf.d/gzip.conf"
    "/etc/nginx/sites-available/nutanix-pxe"
)

for file in "${CONFIG_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "ERROR: Configuration file $file does not exist"
        exit 1
    fi
    echo "✓ $file exists"
done

# Test if sites-enabled symlink exists
echo "3. Checking sites-enabled symlink..."
if [ ! -L "/etc/nginx/sites-enabled/nutanix-pxe" ]; then
    echo "ERROR: Sites-enabled symlink does not exist"
    exit 1
fi
echo "✓ Sites-enabled symlink exists"

# Test if default site is disabled
echo "4. Checking default site..."
if [ -L "/etc/nginx/sites-enabled/default" ]; then
    echo "WARNING: Default site is still enabled"
else
    echo "✓ Default site is disabled"
fi

# Test if log directories exist
echo "5. Checking log directories..."
LOG_DIRS=(
    "/var/log/nutanix-pxe"
    "/var/log/nginx"
)

for dir in "${LOG_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        echo "ERROR: Log directory $dir does not exist"
        exit 1
    fi
    echo "✓ $dir exists"
done

# Test if log rotation configuration exists
echo "6. Checking log rotation configuration..."
if [ ! -f "/etc/logrotate.d/nutanix-pxe" ]; then
    echo "ERROR: Log rotation configuration does not exist"
    exit 1
fi
echo "✓ Log rotation configuration exists"

echo "All tests passed! Nginx configuration is ready."