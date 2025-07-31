// Nutanix VPC Orchestrator - Main JavaScript file

document.addEventListener('DOMContentLoaded', function() {
    console.log('Nutanix VPC Orchestrator UI initialized');
    
    // Initialize any dynamic components
    initializeProgressBars();
    initializeAutoRefresh();
});

function initializeProgressBars() {
    // Animate progress bars on page load
    const progressBars = document.querySelectorAll('.progress-fill');
    progressBars.forEach(bar => {
        const width = bar.style.width;
        bar.style.width = '0%';
        setTimeout(() => {
            bar.style.width = width;
        }, 500);
    });
}

function initializeAutoRefresh() {
    // Auto-refresh data every 30 seconds for active deployments
    const hasActiveDeployments = document.querySelector('.status-pending');
    if (hasActiveDeployments) {
        setInterval(refreshActiveDeployments, 30000);
    }
}

function refreshActiveDeployments() {
    // Find all pending deployments and update their status
    const pendingRows = document.querySelectorAll('tr');
    pendingRows.forEach(row => {
        const statusElement = row.querySelector('.status-pending');
        if (statusElement) {
            const nodeId = row.dataset.nodeId;
            if (nodeId) {
                updateNodeStatus(nodeId, row);
            }
        }
    });
}

function updateNodeStatus(nodeId, row) {
    fetch(`/api/web/node-status/${nodeId}`)
        .then(response => response.json())
        .then(data => {
            if (data.status && data.progress !== undefined) {
                updateRowStatus(row, data.status, data.progress, data.current_phase);
            }
        })
        .catch(error => {
            console.error('Error updating node status:', error);
        });
}

function updateRowStatus(row, status, progress, currentPhase) {
    // Update status indicator
    const statusIndicator = row.querySelector('.status-indicator');
    const statusText = statusIndicator.parentElement;
    
    statusIndicator.className = `status-indicator status-${getStatusClass(status)}`;
    statusText.innerHTML = `<span class="status-indicator status-${getStatusClass(status)}"></span>${status.charAt(0).toUpperCase() + status.slice(1)}`;
    
    // Update progress bar
    const progressBar = row.querySelector('.progress-fill');
    const progressText = row.querySelector('.progress-bar + *');
    
    if (progressBar) {
        progressBar.style.width = `${progress}%`;
    }
    
    if (progressText) {
        progressText.textContent = currentPhase || `${progress}% Complete`;
    }
}

function getStatusClass(status) {
    switch (status.toLowerCase()) {
        case 'running':
        case 'completed':
        case 'healthy':
            return 'running';
        case 'provisioning':
        case 'pending':
        case 'installing':
            return 'pending';
        case 'error':
        case 'failed':
            return 'error';
        default:
            return 'stopped';
    }
}

// Utility functions for form validation
function validateProvisionForm(form) {
    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;
    
    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.style.borderColor = 'var(--cds-support-error)';
            isValid = false;
        } else {
            field.style.borderColor = 'var(--cds-border-subtle)';
        }
    });
    
    return isValid;
}

// Export functions for use in templates
window.nutanixOrchestrator = {
    updateNodeStatus,
    validateProvisionForm,
    refreshActiveDeployments
};