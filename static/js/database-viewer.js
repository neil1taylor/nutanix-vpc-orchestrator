// Database Viewer JavaScript
class DatabaseViewer {
    constructor() {
        this.autoRefreshInterval = null;
        this.autoRefreshEnabled = false;
        this.currentTable = null;
        this.refreshInProgress = false;
        
        this.init();
    }

    init() {
        // Get current table from URL or selection
        const urlParams = new URLSearchParams(window.location.search);
        this.currentTable = urlParams.get('table') || document.getElementById('table-select').value;
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Load initial table if specified
        if (this.currentTable) {
            this.loadTableData(this.currentTable);
        }
    }

    setupEventListeners() {
        // Handle browser back/forward
        window.addEventListener('popstate', (event) => {
            if (event.state && event.state.table) {
                this.currentTable = event.state.table;
                document.getElementById('table-select').value = this.currentTable;
                this.loadTableData(this.currentTable);
            }
        });

        // Handle page visibility change to pause/resume auto-refresh
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.pauseAutoRefresh();
            } else if (this.autoRefreshEnabled) {
                this.resumeAutoRefresh();
            }
        });
    }

    loadTable() {
        const selectElement = document.getElementById('table-select');
        const selectedTable = selectElement.value;
        
        if (!selectedTable) {
            this.clearTableData();
            return;
        }

        this.currentTable = selectedTable;
        this.loadTableData(selectedTable);
        
        // Update URL without reloading
        const url = new URL(window.location);
        url.searchParams.set('table', selectedTable);
        window.history.pushState({ table: selectedTable }, '', url);
    }

    async loadTableData(tableName, showLoading = true) {
        if (this.refreshInProgress) return;
        
        this.refreshInProgress = true;
        
        if (showLoading) {
            this.showLoading();
        }

        try {
            const response = await fetch(`/api/web/database-table?table=${encodeURIComponent(tableName)}`);
            const data = await response.json();

            if (response.ok) {
                this.updateTableDisplay(data);
                this.updateLastUpdated();
            } else {
                this.showError(data.error || 'Failed to load table data');
            }
        } catch (error) {
            console.error('Error loading table data:', error);
            this.showError('Network error while loading table data');
        } finally {
            this.hideLoading();
            this.refreshInProgress = false;
        }
    }

    updateTableDisplay(data) {
        const tableTitle = document.getElementById('table-title');
        const dataTable = document.getElementById('data-table');
        const rowCountValue = document.getElementById('row-count-value');

        if (!data.columns || data.columns.length === 0) {
            this.showNoData('Table is empty or has no columns');
            return;
        }

        // Update title and row count
        tableTitle.textContent = `${data.table_display_name} (${data.table_name})`;
        rowCountValue.textContent = data.rows.length;

        // Clear existing table
        dataTable.innerHTML = '';

        // Create header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        
        data.columns.forEach(column => {
            const th = document.createElement('th');
            th.textContent = column;
            headerRow.appendChild(th);
        });
        
        thead.appendChild(headerRow);
        dataTable.appendChild(thead);

        // Create body
        const tbody = document.createElement('tbody');
        
        if (data.rows.length === 0) {
            const emptyRow = document.createElement('tr');
            const emptyCell = document.createElement('td');
            emptyCell.colSpan = data.columns.length;
            emptyCell.textContent = 'No data found in this table';
            emptyCell.style.textAlign = 'center';
            emptyCell.style.fontStyle = 'italic';
            emptyCell.style.color = 'var(--cds-text-secondary)';
            emptyRow.appendChild(emptyCell);
            tbody.appendChild(emptyRow);
        } else {
            data.rows.forEach(row => {
                const tr = document.createElement('tr');
                row.forEach(cell => {
                    const td = document.createElement('td');
                    td.textContent = this.formatCellValue(cell);
                    td.title = this.formatCellValue(cell); // Tooltip for full value
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            });
        }
        
        dataTable.appendChild(tbody);

        // Show the table container
        document.querySelector('.card-content').style.display = 'block';
    }

    formatCellValue(value) {
        if (value === null || value === undefined) {
            return '';
        }
        
        if (typeof value === 'object') {
            return JSON.stringify(value);
        }
        
        if (typeof value === 'boolean') {
            return value ? 'true' : 'false';
        }
        
        return String(value);
    }

    showLoading() {
        const refreshBtn = document.getElementById('refresh-btn');
        const refreshIcon = document.getElementById('refresh-icon');
        
        refreshBtn.disabled = true;
        refreshIcon.classList.add('refresh-spinning');
        document.querySelector('.card-content').classList.add('loading');
    }

    hideLoading() {
        const refreshBtn = document.getElementById('refresh-btn');
        const refreshIcon = document.getElementById('refresh-icon');
        
        refreshBtn.disabled = false;
        refreshIcon.classList.remove('refresh-spinning');
        document.querySelector('.card-content').classList.remove('loading');
    }

    showError(message) {
        const cardContent = document.querySelector('.card-content');
        cardContent.innerHTML = `
            <div class="alert alert-error">
                <strong>Error:</strong> ${message}
            </div>
        `;
    }

    showNoData(message = 'No data available') {
        const cardContent = document.querySelector('.card-content');
        cardContent.innerHTML = `
            <div class="no-data">
                <p>${message}</p>
            </div>
        `;
    }

    clearTableData() {
        document.getElementById('table-title').textContent = 'Select a table to view data';
        document.getElementById('row-count-value').textContent = '0';
        this.showNoData('Select a table from the dropdown above to view its contents.');
    }

    updateLastUpdated() {
        const now = new Date();
        const timeString = now.toLocaleTimeString();
        document.getElementById('update-time').textContent = timeString;
    }

    toggleAutoRefresh() {
        const toggle = document.getElementById('auto-refresh-toggle');
        this.autoRefreshEnabled = toggle.checked;

        if (this.autoRefreshEnabled) {
            this.startAutoRefresh();
        } else {
            this.stopAutoRefresh();
        }
    }

    startAutoRefresh() {
        this.stopAutoRefresh(); // Clear any existing interval
        
        this.autoRefreshInterval = setInterval(() => {
            if (this.currentTable && !document.hidden) {
                this.loadTableData(this.currentTable, false); // Don't show loading for auto-refresh
            }
        }, 10000); // 10 seconds
    }

    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
    }

    pauseAutoRefresh() {
        this.stopAutoRefresh();
    }

    resumeAutoRefresh() {
        if (this.autoRefreshEnabled) {
            this.startAutoRefresh();
        }
    }

    refreshCurrentTable() {
        if (this.currentTable) {
            this.loadTableData(this.currentTable, true);
        }
    }

    async exportTable() {
        if (!this.currentTable) {
            alert('Please select a table first');
            return;
        }

        try {
            const response = await fetch(`/api/web/database-export?table=${encodeURIComponent(this.currentTable)}&format=csv`);
            
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${this.currentTable}_${new Date().toISOString().split('T')[0]}.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            } else {
                const error = await response.json();
                alert(`Export failed: ${error.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Export error:', error);
            alert('Export failed: Network error');
        }
    }

    async showTableSchema() {
        if (!this.currentTable) {
            alert('Please select a table first');
            return;
        }

        try {
            const response = await fetch(`/api/web/database-schema?table=${encodeURIComponent(this.currentTable)}`);
            const data = await response.json();

            if (response.ok) {
                this.displaySchema(data);
            } else {
                alert(`Schema fetch failed: ${data.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Schema error:', error);
            alert('Schema fetch failed: Network error');
        }
    }

    displaySchema(schemaData) {
        const modal = document.getElementById('schema-modal');
        const tableNameSpan = document.getElementById('schema-table-name');
        const tbody = document.getElementById('schema-tbody');

        tableNameSpan.textContent = this.currentTable;
        
        // Clear existing schema
        tbody.innerHTML = '';

        schemaData.columns.forEach(column => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${column.name}</td>
                <td>${column.type}</td>
                <td>${column.nullable ? 'Yes' : 'No'}</td>
                <td>${column.default || ''}</td>
            `;
            tbody.appendChild(row);
        });

        modal.style.display = 'flex';
    }

    hideSchema() {
        document.getElementById('schema-modal').style.display = 'none';
    }
}

// Global functions for template
function loadTable() {
    window.dbViewer.loadTable();
}

function refreshCurrentTable() {
    window.dbViewer.refreshCurrentTable();
}

function toggleAutoRefresh() {
    window.dbViewer.toggleAutoRefresh();
}

function exportTable() {
    window.dbViewer.exportTable();
}

function showTableSchema() {
    window.dbViewer.showTableSchema();
}

function hideSchema() {
    window.dbViewer.hideSchema();
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    window.dbViewer = new DatabaseViewer();
});

// Close modal when clicking outside
document.addEventListener('click', function(event) {
    const modal = document.getElementById('schema-modal');
    if (event.target === modal) {
        hideSchema();
    }
});