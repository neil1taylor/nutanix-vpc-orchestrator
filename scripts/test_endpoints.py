#!/usr/bin/env python3
"""
Test script to verify that all endpoints work with the new path structure
"""

import requests
import sys
from urllib.parse import urljoin

# Base URL for testing
BASE_URL = "http://localhost:8080"

# Test endpoints
ENDPOINTS = [
    # Health check endpoint
    ("/health", "GET"),
    
    # Boot server endpoints
    ("/boot/config", "GET"),
    ("/boot/server/192.168.1.100", "GET"),
    ("/boot/images/vmlinuz-foundation", "GET"),
    ("/boot/scripts/foundation-init.sh", "GET"),
    
    # Configuration API endpoints
    ("/api/config/nodes", "POST"),
    ("/api/config/nodes/1", "GET"),
    ("/api/config/nodes", "GET"),
    
    # Status monitoring endpoints
    ("/api/status/nodes/1", "GET"),
    ("/api/status/deployment/192.168.1.100", "GET"),
    ("/api/status/phase", "POST"),
    ("/api/status/history/1", "GET"),
    ("/api/status/summary", "GET"),
    
    # DNS registration endpoints
    ("/api/dns/records", "POST"),
    ("/api/dns/records/test-record", "DELETE"),
    
    # Cleanup management endpoints
    ("/api/cleanup/node/1", "POST"),
    ("/api/cleanup/deployment/test-deployment", "POST"),
    ("/api/cleanup/script/test-deployment", "GET"),
    
    # Web interface endpoints
    ("/", "GET"),
    ("/nodes", "GET"),
    ("/provision", "GET"),
]

def test_endpoint(endpoint, method):
    """Test a single endpoint"""
    url = urljoin(BASE_URL, endpoint)
    try:
        if method == "GET":
            response = requests.get(url, timeout=5)
        elif method == "POST":
            response = requests.post(url, timeout=5)
        elif method == "DELETE":
            response = requests.delete(url, timeout=5)
        else:
            print(f"  ❓ Unknown method {method} for {endpoint}")
            return False
            
        # Check if endpoint exists (not 404)
        if response.status_code == 404:
            print(f"  ❌ {method} {endpoint} - Not Found (404)")
            return False
        elif response.status_code >= 500:
            print(f"  ⚠️  {method} {endpoint} - Server Error ({response.status_code})")
            return False
        else:
            print(f"  ✅ {method} {endpoint} - OK ({response.status_code})")
            return True
    except requests.exceptions.ConnectionError:
        print(f"  ❌ {method} {endpoint} - Connection Error")
        return False
    except requests.exceptions.Timeout:
        print(f"  ❌ {method} {endpoint} - Timeout")
        return False
    except Exception as e:
        print(f"  ❌ {method} {endpoint} - Error: {e}")
        return False

def main():
    """Main test function"""
    print(f"Testing endpoints at {BASE_URL}")
    print("=" * 50)
    
    passed = 0
    total = len(ENDPOINTS)
    
    for endpoint, method in ENDPOINTS:
        if test_endpoint(endpoint, method):
            passed += 1
    
    print("=" * 50)
    print(f"Results: {passed}/{total} endpoints passed")
    
    if passed == total:
        print("🎉 All endpoints are working correctly!")
        return 0
    else:
        print("⚠️  Some endpoints failed. Please check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())