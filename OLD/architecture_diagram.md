# Architecture Diagram

## Current Architecture Flow

```mermaid
graph LR
    A[User Browser] --> B[Nginx - Port 443]
    B --> C[Gunicorn - Port 8080]
    C --> D[Python Web App]
    
    subgraph "Service Ports"
        D --> E[Boot Server - Port 8080]
        D --> F[Config API - Port 8081]
        D --> G[Status Monitor - Port 8082]
        D --> H[DNS Service - Port 8083]
        D --> I[Cleanup Service - Port 8084]
    end
    
    subgraph "External Services"
        D --> J[IBM Cloud VPC]
        D --> K[PostgreSQL Database]
    end
    
    subgraph "Static Assets"
        B --> L[CSS/JS Files]
        B --> M[Boot Images]
    end
```

## Proposed Architecture Flow

```mermaid
graph LR
    A[User Browser] --> B[Nginx - Port 443]
    B --> C[Gunicorn - Port 8080]
    C --> D[Python Web App]
    
    subgraph "Unified Service Endpoints"
        D --> E[Boot Server Endpoints]
        D --> F[Config API Endpoints]
        D --> G[Status Monitor Endpoints]
        D --> H[DNS Service Endpoints]
        D --> I[Cleanup Service Endpoints]
    end
    
    subgraph "External Services"
        D --> J[IBM Cloud VPC]
        D --> K[PostgreSQL Database]
    end
    
    subgraph "Static Assets"
        B --> L[CSS/JS Files]
        B --> M[Boot Images]
    end
```

## Component Details

### User Browser
- Accesses web interface and API endpoints
- Communicates over HTTPS (port 443)

### Nginx (Port 443)
- SSL termination
- Static file serving (CSS, JS, boot images)
- Reverse proxy to Gunicorn
- Security headers
- Request routing based on path

### Gunicorn (Port 8080)
- WSGI server for Python application
- Multiple worker processes
- Request handling and load distribution

### Python Web App
- Flask-based application
- Multiple service modules:
  - Boot Service: Handles iPXE boot requests
  - Node Provisioner: Manages node provisioning
  - Status Monitor: Tracks deployment progress
  - DNS Service: Manages DNS records
  - Cleanup Service: Handles resource cleanup
- Database integration
- IBM Cloud API integration

### External Services
- IBM Cloud VPC: Infrastructure provisioning
- PostgreSQL Database: Persistent storage for node and deployment data

### Static Assets
- CSS/JS files for web interface
- Boot images for node provisioning