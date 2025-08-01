#!/bin/bash
# Simple test runner
set -euo pipefail

echo "Running basic health checks..."

# Service check
for service in nutanix-pxe nginx postgresql; do
    if systemctl is-active --quiet $service; then
        echo "✓ $service: Running"
    else
        echo "✗ $service: Not Running"
        exit 1
    fi
done

# Endpoint check
if curl -s -f --max-time 10 http://localhost:8080/health >/dev/null; then
    echo "✓ Health endpoint: OK"
else
    echo "✗ Health endpoint: Failed"
    exit 1
fi

echo "All basic tests passed!"