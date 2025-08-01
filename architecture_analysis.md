# Current Architecture Analysis

## Overview
The Nutanix VPC Orchestrator is a Python-based application that provides automated provisioning of Nutanix CE nodes on IBM Cloud VPC bare metal servers. The application uses a Flask web framework with a hybrid API-first + web UI architecture.

## Key Components

### 1. Application Layer
- **Main Application**: Flask-based Python application (`app.py`)
- **Web Routes**: Separate module for web interface routes (`web_routes.py`)
- **API Endpoints**: RESTful API endpoints for various services
- **Services**:
  - Node Provisioning Service (`node_provisioner.py`)
  - Boot Service (`boot_service.py`)
  - Status Monitoring Service (`status_monitor.py`)
  - IBM Cloud Client (`ibm_cloud_client.py`)
  - Database Service (`database.py`)

### 2. Data Layer
- **Database**: PostgreSQL for persistent storage
- **Configuration**: Environment-based configuration (`config.py`)

### 3. Web Interface
- **Frontend Framework**: IBM Carbon Design System
- **Templates**: Jinja2 templates for server-side rendering
- **Static Assets**: CSS and JavaScript files
- **Responsive Design**: Mobile-first approach

### 4. Infrastructure Components
- **Web Server**: Nginx for reverse proxy and static file serving
- **Application Server**: Gunicorn as WSGI server
- **Process Manager**: Systemd for service management
- **Deployment**: Cloud-init for initial setup

### 5. Current Port Structure
The application currently uses multiple ports for different services:
- **Port 8080**: Boot server endpoints (iPXE configuration, boot images, scripts)
- **Port 8081**: Configuration API endpoints (node provisioning)
- **Port 8082**: Status monitoring endpoints (deployment status, history)
- **Port 8083**: DNS registration endpoints
- **Port 8084**: Cleanup management endpoints

### 6. Current Nginx Configuration
The setup script creates a complex Nginx configuration with:
- Separate server blocks for each service port (8080-8084)
- HTTPS support with SSL termination
- Static file serving for CSS, JS, and boot images
- Proxy pass configurations for each service
- Security headers and SSL configurations
- WebSocket support for future real-time features

### 7. Current Gunicorn Configuration
- Binds to port 8080
- 4 worker processes
- Preloaded application
- Configured logging
- Process management settings

## Identified Issues
1. **Port Proliferation**: Using 5 different ports (8080-8084) for different services
2. **Complex Nginx Configuration**: Multiple server blocks with duplicated configurations
3. **Inefficient Resource Usage**: Multiple server blocks may not be using resources optimally
4. **Maintenance Overhead**: Complex configuration makes maintenance more difficult

## Opportunities for Improvement
1. **Port Consolidation**: Consolidate services to use fewer ports
2. **Simplified Nginx Configuration**: Reduce complexity by using path-based routing
3. **Enhanced Security**: Implement more robust security measures
4. **Performance Optimization**: Optimize configurations for better performance