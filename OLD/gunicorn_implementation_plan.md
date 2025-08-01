# Gunicorn Configuration Implementation Plan

## Overview
This plan outlines the steps to optimize the Gunicorn configuration for the Nutanix VPC Orchestrator, improving performance, reliability, and resource utilization while maintaining compatibility with the new Nginx reverse proxy setup.

## Implementation Phases

### Phase 1: Preparation and Analysis
1. **Current Configuration Assessment**
   - Review existing `gunicorn.conf.py` settings
   - Analyze current worker performance and resource usage
   - Identify bottlenecks and optimization opportunities
   - Document current application startup time and memory usage

2. **Environment Analysis**
   - Determine server specifications (CPU, memory, disk)
   - Check current system load and resource utilization
   - Review systemd service configuration
   - Analyze application logs for performance issues

3. **Stakeholder Communication**
   - Notify team of planned configuration changes
   - Schedule maintenance window
   - Prepare rollback plan

### Phase 2: Configuration Optimization
1. **Worker Process Optimization**
   - Calculate optimal worker count based on CPU cores
   - Select appropriate worker class (sync vs async)
   - Configure worker connections for optimal throughput
   - Set memory limits and restart policies

2. **Timeout Configuration**
   - Adjust connection timeouts based on application needs
   - Configure graceful shutdown timeouts
   - Set appropriate keepalive settings

3. **Resource Management**
   - Configure buffer sizes for efficient data transfer
   - Set memory limits to prevent resource exhaustion
   - Configure temporary directory for worker processes

### Phase 3: Advanced Configuration
1. **Performance Tuning**
   - Implement request preloading
   - Configure maximum request limits
   - Set up worker lifecycle management
   - Optimize for specific application patterns

2. **Monitoring and Logging**
   - Configure detailed access and error logging
   - Set up log rotation
   - Implement custom logging hooks
   - Configure performance metrics collection

3. **Security Enhancements**
   - Configure user and group permissions
   - Set up secure temporary directories
   - Implement secure header forwarding

### Phase 4: Testing and Validation
1. **Configuration Testing**
   - Validate syntax and configuration options
   - Test with different load patterns
   - Verify compatibility with application code
   - Check integration with Nginx reverse proxy

2. **Performance Testing**
   - Benchmark response times before and after changes
   - Test under various load conditions
   - Monitor memory and CPU usage
   - Validate error handling

### Phase 5: Production Deployment
1. **Deployment Steps**
   - Schedule maintenance window
   - Backup current configuration
   - Deploy new Gunicorn configuration
   - Restart application service
   - Monitor for issues

2. **Post-Deployment Validation**
   - Verify application functionality
   - Monitor performance metrics
   - Check logs for errors
   - Validate integration with Nginx

## Detailed Configuration Changes

### 1. Optimized Gunicorn Configuration
```python
# /opt/nutanix-pxe/gunicorn.conf.py

# Server socket
bind = "127.0.0.1:8080"
backlog = 2048

# Worker processes
import multiprocessing
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
preload_app = True

# Timeouts
timeout = 30
keepalive = 2
graceful_timeout = 30

# Process naming
proc_name = "nutanix-pxe-server"

# User and group
user = "nutanix"
group = "nutanix"

# Paths
tmp_upload_dir = None
secure_scheme_headers = {
    'X-FORWARDED-PROTOCOL': 'ssl',
    'X-FORWARDED-PROTO': 'https',
    'X-FORWARDED-SSL': 'on'
}

# Logging
errorlog = "/var/log/nutanix-pxe/gunicorn-error.log"
accesslog = "/var/log/nutanix-pxe/gunicorn-access.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Enable access logging
capture_output = True
enable_stdio_inheritance = True

# Worker process lifecycle
max_worker_memory = 200  # MB
worker_tmp_dir = "/dev/shm"

# Server mechanics
daemon = False
pidfile = "/var/run/nutanix-pxe/gunicorn.pid"
umask = 0
tmp_upload_dir = None

# Application
pythonpath = "/opt/nutanix-pxe"
chdir = "/opt/nutanix-pxe"

# Development/Debug (set to False for production)
reload = False
reload_engine = "auto"

# Performance tuning
worker_tmp_dir = "/dev/shm"
max_worker_memory = 200

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Nutanix PXE/Config Server is ready to serve requests")

def worker_int(worker):
    """Called just after a worker has been interrupted by SIGINT."""
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_worker_init(worker):
    """Called just after a worker has initialized the application."""
    worker.log.info("Worker initialized (pid: %s)", worker.pid)

def worker_abort(worker):
    """Called when a worker is aborted."""
    worker.log.info("Worker aborted (pid: %s)", worker.pid)

def worker_exit(server, worker):
    """Called just after a worker has been exited, in the worker process."""
    worker.log.info("Worker exiting (pid: %s)", worker.pid)
```

### 2. Systemd Service Configuration
```ini
# /etc/systemd/system/nutanix-pxe.service

[Unit]
Description=Nutanix PXE/Config Server
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=notify
User=nutanix
Group=nutanix
WorkingDirectory=/opt/nutanix-pxe
Environment=PATH=/opt/nutanix-pxe/venv/bin
ExecStart=/opt/nutanix-pxe/venv/bin/gunicorn --config gunicorn.conf.py app:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true

# Security
NoNewPrivileges=true
MemoryDenyWriteExecute=true
RestrictRealtime=true

# Resource limits
LimitNOFILE=65536
LimitNPROC=32768

[Install]
WantedBy=multi-user.target
```

### 3. Memory Management Script
```python
# /opt/nutanix-pxe/scripts/monitor_workers.py

import psutil
import logging
import time
import subprocess

def monitor_gunicorn_workers():
    """Monitor Gunicorn worker memory usage and restart if needed."""
    logging.basicConfig(
        filename='/var/log/nutanix-pxe/worker-monitor.log',
        level=logging.INFO,
        format='%(asctime)s - %(message)s'
    )
    
    while True:
        try:
            # Find Gunicorn processes
            for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                if 'gunicorn' in proc.info['name']:
                    memory_mb = proc.info['memory_info'].rss / 1024 / 1024
                    if memory_mb > 200:  # Configured max_worker_memory
                        logging.warning(f"Worker {proc.info['pid']} using {memory_mb:.2f}MB, restarting")
                        proc.kill()
                        # Systemd will restart the worker
        except Exception as e:
            logging.error(f"Error monitoring workers: {e}")
        
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    monitor_gunicorn_workers()
```

## Rollback Procedure
1. **In Case of Issues**
   - Stop Gunicorn service
   - Restore previous configuration files
   - Start Gunicorn service
   - Verify functionality

2. **Monitoring During Deployment**
   - Monitor Gunicorn logs
   - Check application logs
   - Watch system resources
   - Monitor response times

## Timeline
- **Preparation**: 2 hours
- **Configuration Implementation**: 3 hours
- **Testing**: 2 hours
- **Production Deployment**: 1 hour
- **Post-Deployment Monitoring**: 2 hours

## Success Criteria
- Improved response times
- Better resource utilization
- No service interruptions
- Successful rollback capability
- Proper logging and monitoring
- Compatibility with Nginx reverse proxy

This implementation plan will result in an optimized Gunicorn configuration that works efficiently with the new Nginx reverse proxy setup.