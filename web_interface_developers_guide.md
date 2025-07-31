# Nutanix VPC Orchestrator - Web Interface Developer Guide

## Architecture Overview

The web interface is built as a Flask extension to the existing API-based Nutanix VPC Orchestrator, following a **hybrid API-first + web UI** architecture that maintains backward compatibility while adding modern web capabilities.

### Core Design Principles

- **Non-Breaking Integration**: All existing API endpoints remain unchanged
- **Shared Backend Services**: Web routes use the same business logic as API endpoints
- **Progressive Enhancement**: JavaScript enhances the experience but isn't required for core functionality
- **Mobile-First Responsive Design**: Built with IBM Carbon Design System
- **Real-Time Updates**: WebSocket-ready architecture with AJAX fallbacks

## Technical Stack

### Backend
- **Flask 2.3+**: Web framework with Jinja2 templating
- **PostgreSQL**: Existing database with minimal schema extensions
- **Python 3.8+**: Leverages existing application dependencies
- **Gunicorn**: WSGI server (existing configuration)
- **Nginx**: Reverse proxy for static assets (existing configuration)

### Frontend
- **IBM Carbon Design System**: Official IBM design language
- **Vanilla JavaScript ES6+**: No framework dependencies
- **CSS Grid + Flexbox**: Modern responsive layouts
- **Progressive Web App Ready**: Service worker compatible

### Integration Layer
```python
# web_routes.py - Bridge between web and API layers
def register_web_routes(app, db, node_provisioner, status_monitor):
    # Web routes use existing services without modification
    @app.route('/provision', methods=['POST'])
    def provision_node():
        # Form data → API data transformation
        result = node_provisioner.provision_node(transformed_data)
        # API response → Web response transformation
        return render_template_or_redirect(result)
```

## File Structure and Components

```
nutanix-pxe-server/
├── web_routes.py              # Flask web routes
├── templates/                 # Jinja2 templates
│   ├── base.html             # Master layout template
│   ├── dashboard.html        # Dashboard view
│   ├── nodes.html           # Node management
│   ├── provision_form.html   # Node provisioning form
│   ├── node_details.html     # Individual node details
│   ├── deployments.html      # Deployment history
│   └── monitoring.html       # System health monitoring
├── static/
│   ├── css/
│   │   └── styles.css        # IBM Carbon-based styles
│   └── js/
│       ├── main.js           # Core JavaScript functionality
│       └── deployment-monitor.js  # Real-time updates
└── requirements.txt          # Additional Python dependencies
```

## Database Schema Extensions

Minimal additions to existing schema for web UI support:

```sql
-- Optional columns for enhanced web UI functionality
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS progress_percentage INTEGER DEFAULT 0;
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS current_phase VARCHAR(100);
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS cluster_name VARCHAR(100);

-- Performance indexes for web queries
CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(deployment_status);
CREATE INDEX IF NOT EXISTS idx_nodes_created ON nodes(created_at);
CREATE INDEX IF NOT EXISTS idx_deployment_history_node ON deployment_history(node_id);
CREATE INDEX IF NOT EXISTS idx_deployment_history_timestamp ON deployment_history(timestamp);
```

## API Integration Patterns

### 1. Form-to-API Data Transformation

```python
def transform_form_to_api(form_data):
    """Transform HTML form data to API-compatible format"""
    return {
        'node_config': {
            'node_name': form_data.get('node_name'),
            'node_position': form_data.get('node_position'),
            'server_profile': form_data.get('server_profile'),
            'cluster_role': form_data.get('cluster_role'),
            'storage_config': {
                'data_drives': form_data.getlist('data_drives')
            }
        },
        'network_config': {
            'management_subnet': form_data.get('management_subnet'),
            'workload_subnet': form_data.get('workload_subnet', 'auto'),
            'cluster_operation': form_data.get('cluster_operation')
        }
    }
```

### 2. Dual Response Handling

```python
@app.route('/api/v1/nodes', methods=['POST'])  # Existing API endpoint
def api_provision_node():
    """Original API endpoint - unchanged"""
    return jsonify(node_provisioner.provision_node(request.json))

@app.route('/provision', methods=['POST'])     # New web endpoint
def web_provision_node():
    """Web form endpoint - uses same business logic"""
    api_data = transform_form_to_api(request.form)
    result = node_provisioner.provision_node(api_data)  # Same service!
    
    if result.get('success'):
        flash('Node provisioning started successfully!', 'success')
        return redirect(url_for('deployments'))
    else:
        flash(f'Error: {result.get("error")}', 'error')
        return render_template('provision_form.html')
```

## Real-Time Updates Architecture

### AJAX-Based Status Updates

```javascript
class DeploymentMonitor {
    constructor() {
        this.activeDeployments = new Set();
        this.refreshInterval = 15000; // 15 seconds
    }

    async updateSingleDeployment(nodeId) {
        try {
            // Uses existing API endpoint
            const response = await fetch(`/api/v1/nodes/${nodeId}/status`);
            const data = await response.json();
            
            this.updateDeploymentUI(nodeId, data);
            
            // Remove from monitoring when complete
            if (['running', 'completed', 'error'].includes(data.status)) {
                this.activeDeployments.delete(nodeId);
            }
        } catch (error) {
            console.error(`Error updating deployment ${nodeId}:`, error);
        }
    }
}
```

### WebSocket Extension Point

```python
# Future WebSocket support (using Flask-SocketIO)
def init_websocket_support(app):
    """Optional WebSocket integration for real-time updates"""
    from flask_socketio import SocketIO
    
    socketio = SocketIO(app, cors_allowed_origins="*")
    
    @socketio.on('subscribe_deployment')
    def handle_subscription(data):
        join_room(f"deployment_{data['node_id']}")
    
    # Emit updates from existing status_monitor
    def broadcast_status_update(node_id, status_data):
        socketio.emit('status_update', status_data, room=f"deployment_{node_id}")
```

## Frontend Architecture

### CSS Architecture (IBM Carbon Design)

```css
/* CSS Custom Properties for theming */
:root {
    --cds-background: #161616;
    --cds-layer-01: #262626;
    --cds-text-primary: #f4f4f4;
    --cds-interactive-01: #0f62fe;
    /* ... other Carbon Design tokens */
}

/* Component-based CSS structure */
.header { /* Global navigation */ }
.container { /* Main content wrapper */ }
.card { /* Reusable card component */ }
.stats-grid { /* Dashboard statistics layout */ }
.table { /* Data table styling */ }
.form-grid { /* Form layout system */ }
```

### JavaScript Module Pattern

```javascript
// main.js - Core functionality
window.nutanixOrchestrator = {
    // Public API for other modules
    updateNodeStatus: function(nodeId, statusData) { /* ... */ },
    validateProvisionForm: function(form) { /* ... */ },
    refreshActiveDeployments: function() { /* ... */ }
};

// deployment-monitor.js - Specialized monitoring
class DeploymentMonitor {
    // Uses public API from main.js
    // Focuses solely on real-time updates
}
```

## Template System

### Master Layout Template (base.html)

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{% block title %}Nutanix VPC Orchestrator{% endblock %}</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/carbon-components/10.58.0/css/carbon-components.min.css" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/styles.css') }}">
</head>
<body>
    <header class="header">
        <!-- Global Navigation -->
        <nav class="header-nav">
            <a href="{{ url_for('dashboard') }}" 
               class="nav-item {% if request.endpoint == 'dashboard' %}active{% endif %}">
                Dashboard
            </a>
            <!-- ... other nav items -->
        </nav>
    </header>
    
    <div class="container">
        <!-- Flash message system -->
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </div>
    
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    {% block extra_js %}{% endblock %}
</body>
</html>
```

### Data-Driven Templates

```html
<!-- dashboard.html - Example of data binding -->
<div class="stats-grid">
    {% for stat in [
        ('active_nodes', 'Active Nodes'),
        ('total_clusters', 'Clusters'),
        ('total_deployments', 'Total Deployments'),
        ('success_rate', 'Success Rate')
    ] %}
    <div class="stat-card">
        <div class="stat-value">{{ stats[stat[0]] or 0 }}</div>
        <div class="stat-label">{{ stat[1] }}</div>
    </div>
    {% endfor %}
</div>
```

## Error Handling and Logging

### Centralized Error Handling

```python
def register_error_handlers(app):
    """Register web-specific error handlers"""
    
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        logger.error(f'Server Error: {error}')
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        # Log the error for debugging
        logger.exception("Unhandled exception in web interface")
        
        # Return user-friendly error
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('dashboard'))
```

### Client-Side Error Handling

```javascript
// Global error handling for AJAX requests
window.addEventListener('unhandledrejection', function(event) {
    console.error('Unhandled promise rejection:', event.reason);
    
    // Show user-friendly error message
    showNotification('An error occurred. Please refresh the page.', 'error');
});

// Fetch wrapper with error handling
async function safeFetch(url, options = {}) {
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Fetch error:', error);
        showNotification('Failed to load data. Please try again.', 'error');
        throw error;
    }
}
```

## Security Considerations

### CSRF Protection

```python
# Using Flask-WTF for CSRF protection
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)

# All forms automatically include CSRF tokens
# AJAX requests need manual token handling
```

### Input Validation

```python
from wtforms import Form, StringField, SelectField, validators

class ProvisionNodeForm(Form):
    """Server-side form validation"""
    node_name = StringField('Node Name', [
        validators.Length(min=1, max=100),
        validators.Regexp(r'^[a-zA-Z0-9\-]+$', message="Invalid characters")
    ])
    server_profile = SelectField('Server Profile', choices=[
        ('bx2d-metal-24x96', 'bx2d-metal-24x96'),
        ('bx2d-metal-48x192', 'bx2d-metal-48x192'),
        ('bx2d-metal-96x384', 'bx2d-metal-96x384')
    ])
```

### Content Security Policy

```python
@app.after_request
def set_csp_header(response):
    """Set Content Security Policy headers"""
    csp = (
        "default-src 'self'; "
        "style-src 'self' https://cdnjs.cloudflare.com 'unsafe-inline'; "
        "script-src 'self' https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
    )
    response.headers['Content-Security-Policy'] = csp
    return response
```

## Performance Optimization

### Database Query Optimization

```python
def get_dashboard_stats(db):
    """Optimized dashboard queries using single connection"""
    cursor = db.cursor()
    
    # Single query for multiple stats
    cursor.execute("""
        SELECT 
            COUNT(*) as total_deployments,
            COUNT(*) FILTER (WHERE deployment_status = 'running') as active_nodes,
            COUNT(DISTINCT cluster_name) FILTER (WHERE cluster_name IS NOT NULL) as total_clusters
        FROM nodes
    """)
    
    row = cursor.fetchone()
    success_rate = (row[1] / row[0] * 100) if row[0] > 0 else 0
    
    return {
        'total_deployments': row[0],
        'active_nodes': row[1], 
        'total_clusters': row[2],
        'success_rate': f"{success_rate:.1f}%"
    }
```

### Frontend Performance

```javascript
// Debounced auto-refresh to prevent excessive API calls
const debouncedRefresh = debounce(function() {
    refreshActiveDeployments();
}, 1000);

// Intersection Observer for lazy loading
const observeDeploymentRows = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            loadDeploymentDetails(entry.target);
        }
    });
});
```

## Testing Strategy

### Backend Testing

```python
# test_web_routes.py
import pytest
from flask import url_for

def test_dashboard_loads(client):
    """Test dashboard renders without errors"""
    response = client.get(url_for('dashboard'))
    assert response.status_code == 200
    assert b'Cluster Overview' in response.data

def test_provision_form_validation(client):
    """Test form validation works correctly"""
    response = client.post(url_for('provision_node'), data={
        'node_name': '',  # Invalid: required field empty
        'server_profile': 'invalid-profile'  # Invalid: not in choices
    })
    assert response.status_code == 200
    assert b'Please fill in all required fields' in response.data

@pytest.fixture
def mock_node_provisioner():
    """Mock the node provisioner for testing"""
    with patch('web_routes.node_provisioner') as mock:
        mock.provision_node.return_value = {'success': True, 'node_id': 123}
        yield mock
```

### Frontend Testing

```javascript
// Using Jest for JavaScript testing
describe('DeploymentMonitor', () => {
    let monitor;
    
    beforeEach(() => {
        // Mock DOM elements
        document.body.innerHTML = `
            <tr data-node-id="123">
                <td>test-node</td>
                <td><span class="status-indicator status-pending"></span></td>
            </tr>
        `;
        monitor = new DeploymentMonitor();
    });
    
    test('should update status indicator correctly', () => {
        const row = document.querySelector('tr[data-node-id="123"]');
        monitor.updateRowStatus(row, 'running', 100, 'Complete');
        
        const indicator = row.querySelector('.status-indicator');
        expect(indicator.classList.contains('status-running')).toBe(true);
    });
});
```

## Deployment and CI/CD

### Docker Integration

```dockerfile
# Dockerfile additions for web UI assets
FROM python:3.9-slim

# ... existing setup ...

# Install Node.js for asset building (optional)
RUN curl -fsSL https://deb.nodesource.com/setup_16.x | bash - \
    && apt-get install -y nodejs

# Copy and build frontend assets
COPY static/ /app/static/
COPY templates/ /app/templates/

# ... rest of existing Dockerfile ...
```

### GitHub Actions Workflow

```yaml
name: Test Web Interface
on: [push, pull_request]

jobs:
  test-web-ui:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.9
          
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-flask
          
      - name: Run web interface tests
        run: |
          pytest tests/test_web_routes.py -v
          
      - name: Test frontend JavaScript
        run: |
          npm install jest jsdom
          npm test
```

## Migration Guide

### From API-Only to Hybrid

1. **Phase 1: Add web routes alongside existing API**
   ```python
   # Existing API routes continue to work
   @app.route('/api/v1/nodes', methods=['POST'])
   def api_provision_node():
       return jsonify(provision_logic(request.json))
   
   # New web routes use same logic
   @app.route('/provision', methods=['POST']) 
   def web_provision_node():
       return handle_web_form(provision_logic)
   ```

2. **Phase 2: Optional database schema updates**
   ```sql
   -- Non-breaking additions only
   ALTER TABLE nodes ADD COLUMN IF NOT EXISTS progress_percentage INTEGER DEFAULT 0;
   ```

3. **Phase 3: Deploy static assets**
   ```bash
   mkdir -p static/css static/js templates/
   # Copy template and static files
   ```

### Backward Compatibility

- **All existing API endpoints** remain unchanged
- **Database schema** only adds optional columns
- **Configuration** uses existing environment variables
- **Authentication** leverages existing mechanisms

## Extending the Interface

### Adding New Pages

```python
# 1. Add route to web_routes.py
@app.route('/clusters')
def clusters():
    clusters = get_cluster_data(db)
    return render_template('clusters.html', clusters=clusters)

# 2. Create template: templates/clusters.html
{% extends "base.html" %}
{% block content %}
<!-- New page content -->
{% endblock %}

# 3. Add navigation link to base.html
<a href="{{ url_for('clusters') }}" class="nav-item">Clusters</a>
```

### Adding Custom Components

```css
/* New component in styles.css */
.cluster-topology {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
}

.cluster-node {
    background: var(--cds-layer-01);
    border: 1px solid var(--cds-border-subtle);
    border-radius: 8px;
    padding: 1rem;
}
```

### API Extensions

```python
# Add web-specific API endpoints
@app.route('/api/web/cluster-topology/<cluster_id>')
def cluster_topology(cluster_id):
    """Web-specific API for topology visualization"""
    topology = generate_cluster_topology(cluster_id)
    return jsonify(topology)
```

This comprehensive developer guide provides all the technical details needed to understand, modify, and extend the web interface while maintaining the robust API-first architecture of the original system.