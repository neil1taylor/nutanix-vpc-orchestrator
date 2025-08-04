# Gunicorn configuration for Nutanix PXE/Config Server

# Server socket
bind = "0.0.0.0:8080"
backlog = 2048

# Worker processes
workers = 4
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

# Enable access logging. capture_output = True means stdout/stderr from the application will be captured by Gunicorn
capture_output = True
enable_stdio_inheritance = True

# SSL (if needed in the future)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

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