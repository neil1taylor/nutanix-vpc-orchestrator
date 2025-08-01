#!/bin/bash
# Status check script for Nutanix PXE Server

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

echo "=== Nutanix PXE/Config Server Status ==="
echo "Date: $(date)"
echo "Host: $(hostname) ($(hostname -I | awk '{print $1}'))"
echo

echo "Service Status:"
for service in nutanix-pxe nginx postgresql; do
    if systemctl is-active --quiet $service; then
        echo -e "${GREEN}✓${NC} $service: Running"
    else
        echo -e "${RED}✗${NC} $service: Not Running"
    fi
done

echo
echo "Network Endpoints:"
curl -s -f --max-time 5 http://localhost:8080/health >/dev/null && \
    echo -e "${GREEN}✓${NC} Health Check: OK" || \
    echo -e "${RED}✗${NC} Health Check: Failed"

echo
echo "Quick Commands:"
echo "  Restart service: systemctl restart nutanix-pxe"
echo "  View logs: journalctl -u nutanix-pxe -f"
echo "  Test endpoints: curl http://localhost:8080/health"