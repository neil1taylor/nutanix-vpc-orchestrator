// Real-time deployment monitoring
class DeploymentMonitor {
    constructor() {
        this.activeDeployments = new Set();
        this.refreshInterval = 15000; // 15 seconds
        this.init();
    }

    init() {
        this.findActiveDeployments();
        if (this.activeDeployments.size > 0) {
            this.startMonitoring();
        }
    }

    findActiveDeployments() {
        const pendingElements = document.querySelectorAll('.status-pending, .status-provisioning');
        pendingElements.forEach(element => {
            const row = element.closest('tr');
            const nodeId = this.extractNodeId(row);
            if (nodeId) {
                this.activeDeployments.add(nodeId);
            }
        });
    }

    extractNodeId(row) {
        // Try to get node ID from data attribute or link
        const viewLink = row.querySelector('a[href*="/node/"]');
        if (viewLink) {
            const matches = viewLink.href.match(/\/node\/(\d+)/);
            return matches ? matches[1] : null;
        }
        return null;
    }

    startMonitoring() {
        console.log(`Starting monitoring for ${this.activeDeployments.size} active deployments`);
        this.monitorInterval = setInterval(() => {
            this.checkDeploymentStatus();
        }, this.refreshInterval);
    }

    async checkDeploymentStatus() {
        const promises = Array.from(this.activeDeployments).map(nodeId => 
            this.updateSingleDeployment(nodeId)
        );
        
        await Promise.all(promises);
        
        // Stop monitoring if no more active deployments
        if (this.activeDeployments.size === 0) {
            this.stopMonitoring();
        }
    }

    async updateSingleDeployment(nodeId) {
        try {
            const response = await fetch(`/api/web/node-status/${nodeId}`);
            const data = await response.json();
            
            if (data.status) {
                this.updateDeploymentUI(nodeId, data);
                
                // Remove from active deployments if completed
                if (data.status === 'running' || data.status === 'completed' || data.status === 'error') {
                    this.activeDeployments.delete(nodeId);
                }
            }
        } catch (error) {
            console.error(`Error updating deployment ${nodeId}:`, error);
        }
    }

    updateDeploymentUI(nodeId, data) {
        const row = this.findRowByNodeId(nodeId);
        if (!row) return;

        // Update status
        const statusElement = row.querySelector('.status-indicator');
        if (statusElement) {
            const newClass = `status-indicator status-${this.getStatusClass(data.status)}`;
            statusElement.className = newClass;
            statusElement.parentElement.innerHTML = 
                `<span class="${newClass}"></span>${data.status.charAt(0).toUpperCase() + data.status.slice(1)}`;
        }

        // Update progress
        const progressBar = row.querySelector('.progress-fill');
        if (progressBar && data.progress !== undefined) {
            progressBar.style.width = `${data.progress}%`;
            
            const progressText = progressBar.parentElement.nextElementSibling;
            if (progressText) {
                progressText.textContent = data.current_phase || `${data.progress}% Complete`;
            }
        }
    }

    findRowByNodeId(nodeId) {
        const links = document.querySelectorAll(`a[href*="/node/${nodeId}"]`);
        return links.length > 0 ? links[0].closest('tr') : null;
    }

    getStatusClass(status) {
        const statusMap = {
            'running': 'running',
            'completed': 'running',
            'healthy': 'running',
            'provisioning': 'pending',
            'pending': 'pending',
            'installing': 'pending',
            'error': 'error',
            'failed': 'error'
        };
        return statusMap[status.toLowerCase()] || 'stopped';
    }

    stopMonitoring() {
        if (this.monitorInterval) {
            clearInterval(this.monitorInterval);
            console.log('Deployment monitoring stopped');
        }
    }
}

// Initialize deployment monitor when page loads
document.addEventListener('DOMContentLoaded', function() {
    if (document.querySelector('.table')) {
        window.deploymentMonitor = new DeploymentMonitor();
    }
});