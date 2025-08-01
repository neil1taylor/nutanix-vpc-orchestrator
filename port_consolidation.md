# Port Consolidation Opportunities

## Current Port Usage Analysis

The current architecture uses 5 separate ports for different services:
- **Port 8080**: Boot server endpoints (iPXE configuration, boot images, scripts)
- **Port 8081**: Configuration API endpoints (node provisioning)
- **Port 8082**: Status monitoring endpoints (deployment status, history)
- **Port 8083**: DNS registration endpoints
- **Port 8084**: Cleanup management endpoints

## Issues with Current Approach

1. **Resource Inefficiency**: Each port requires a separate Nginx server block, leading to:
   - Increased memory usage
   - More complex configuration management
   - Higher maintenance overhead

2. **Operational Complexity**: 
   - Multiple server blocks with duplicated SSL configurations
   - More points of failure
   - Complex troubleshooting

3. **Scalability Concerns**:
   - Difficult to add new services
   - Inconsistent endpoint management
   - Non-standard approach to service organization

## Consolidation Strategy

### Option 1: Path-Based Routing (Recommended)
Consolidate all services under a single port (8080) with path-based routing:

```
https://server/boot/          → Boot server endpoints
https://server/api/config/    → Configuration API endpoints
https://server/api/status/    → Status monitoring endpoints
https://server/api/dns/       → DNS registration endpoints
https://server/api/cleanup/   → Cleanup management endpoints
https://server/               → Web interface
```

### Option 2: Subdomain-Based Routing
Use subdomains to separate services:

```
https://boot.server/          → Boot server endpoints
https://config.server/        → Configuration API endpoints
https://status.server/        → Status monitoring endpoints
https://dns.server/           → DNS registration endpoints
https://cleanup.server/       → Cleanup management endpoints
https://server/               → Web interface
```

## Benefits of Consolidation

1. **Simplified Nginx Configuration**:
   - Single server block instead of 5+ separate blocks
   - Centralized SSL configuration
   - Easier maintenance and updates

2. **Improved Resource Utilization**:
   - Reduced memory footprint
   - Better connection handling
   - More efficient use of system resources

3. **Enhanced Security**:
   - Centralized security policies
   - Consistent security headers
   - Simplified certificate management

4. **Better Monitoring and Logging**:
   - Unified access logs
   - Simplified analytics
   - Easier troubleshooting

## Implementation Approach

### Phase 1: Path-Based Consolidation
1. Update Flask application to handle path-based routing
2. Modify Nginx configuration to use single server block with path routing
3. Update API endpoints to use new paths
4. Maintain backward compatibility during transition

### Phase 2: Service Refactoring
1. Organize services into logical modules
2. Implement consistent API patterns
3. Add proper API versioning
4. Improve documentation

## Detailed Path Mapping

| Current Endpoint | New Consolidated Path | Service |
|------------------|----------------------|---------|
| /boot-config | /boot/config | Boot Service |
| /server-config/{ip} | /boot/server/{ip} | Boot Service |
| /images/{filename} | /boot/images/{filename} | Boot Service |
| /scripts/{script_name} | /boot/scripts/{script_name} | Boot Service |
| /api/v1/nodes | /api/config/nodes | Node Provisioner |
| /api/v1/nodes/{id} | /api/config/nodes/{id} | Node Provisioner |
| /api/v1/nodes/{id}/status | /api/status/nodes/{id} | Status Monitor |
| /deployment-status/{ip} | /api/status/deployment/{ip} | Status Monitor |
| /phase-update | /api/status/phase | Status Monitor |
| /api/v1/nodes/{id}/history | /api/status/history/{id} | Status Monitor |
| /api/v1/deployment/summary | /api/status/summary | Status Monitor |
| /api/v1/dns/records | /api/dns/records | DNS Service |
| /api/v1/dns/records/{name} | /api/dns/records/{name} | DNS Service |
| /api/v1/cleanup/node/{id} | /api/cleanup/node/{id} | Cleanup Service |
| /api/v1/cleanup/deployment/{id} | /api/cleanup/deployment/{id} | Cleanup Service |
| /api/v1/cleanup/script/{id} | /api/cleanup/script/{id} | Cleanup Service |

## Backward Compatibility

During the transition period, we'll maintain backward compatibility by:
1. Keeping old endpoints functional with deprecation warnings
2. Implementing redirects from old paths to new paths
3. Providing a migration period for clients to update
4. Removing deprecated endpoints in a future major release