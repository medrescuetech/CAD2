// Dashboard Manager
const DashboardManager = {
    // Configuration
    config: {
        refreshInterval: 30000, // 30 seconds
        maxRetries: 3,
        retryDelay: 5000
    },

    // State management
    state: {
        refreshTimer: null,
        ws: null,
        openIncidentWindows: new Map() // Track open incident windows
    },

    // Initialize dashboard
    init() {
        this._initEventListeners();
        this._initWebSocket();
        this._setupAutoRefresh();
        return this;
    },

    // Initialize event listeners
    _initEventListeners() {
        // New incident button
        document.getElementById('newIncidentBtn')?.addEventListener('click', () => {
            this.openNewIncident();
        });

        // Incident row clicks
        document.querySelectorAll('.incident-row').forEach(row => {
            row.addEventListener('click', () => {
                const incidentId = row.dataset.incidentId;
                if (incidentId) {
                    this.openIncident(incidentId);
                }
            });
        });
    },

    // Open new incident window
    async openNewIncident() {
        try {
            const response = await fetch('/api/incidents/new');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const data = await response.json();
            const incidentWindow = window.open('about:blank', '_blank');
            
            // Set window content
            incidentWindow.document.write(data.html);
            incidentWindow.document.title = data.title;
            incidentWindow.document.close();
            
            // Track the window
            this.state.openIncidentWindows.set('new', incidentWindow);
            
            // Listen for window close
            incidentWindow.addEventListener('unload', () => {
                this.state.openIncidentWindows.delete('new');
                this.refreshDashboard(); // Refresh dashboard when window closes
            });
            
        } catch (error) {
            console.error('Error opening new incident:', error);
            this._showAlert('Failed to open new incident', 'danger');
        }
    },

    // Open existing incident window
    async openIncident(incidentId) {
        try {
            const response = await fetch(`/api/incidents/${incidentId}/window`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const data = await response.json();
            const incidentWindow = window.open('about:blank', '_blank');
            
            // Set window content
            incidentWindow.document.write(data.html);
            incidentWindow.document.title = data.title;
            incidentWindow.document.close();
            
            // Track the window
            this.state.openIncidentWindows.set(incidentId, incidentWindow);
            
            // Listen for window close
            incidentWindow.addEventListener('unload', () => {
                this.state.openIncidentWindows.delete(incidentId);
                this.refreshDashboard(); // Refresh dashboard when window closes
            });
            
        } catch (error) {
            console.error('Error opening incident:', error);
            this._showAlert('Failed to open incident', 'danger');
        }
    },

    // Initialize WebSocket connection
    _initWebSocket() {
        this.state.ws = new WebSocket(`ws://${window.location.host}/ws`);
        
        this.state.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            switch (data.type) {
                case 'incident_update':
                    this._handleIncidentUpdate(data.incident);
                    break;
                case 'unit_update':
                    this._handleUnitUpdate(data.unit);
                    break;
                case 'new_incident':
                    this._handleNewIncident(data.incident);
                    break;
            }
        };
        
        this.state.ws.onclose = () => {
            setTimeout(() => this._initWebSocket(), 5000); // Reconnect after 5 seconds
        };
    },

    // Handle incident update
    _handleIncidentUpdate(incident) {
        // Update dashboard row
        const row = document.querySelector(`tr[data-incident-id="${incident.id}"]`);
        if (row) {
            row.querySelector('.incident-status').textContent = incident.status;
            row.querySelector('.incident-priority').textContent = incident.priority;
            // Update other fields as needed
        }
        
        // Notify open incident window if exists
        const incidentWindow = this.state.openIncidentWindows.get(incident.id);
        if (incidentWindow && !incidentWindow.closed) {
            incidentWindow.postMessage({ type: 'incident_update', incident }, '*');
        }
    },

    // Handle unit update
    _handleUnitUpdate(unit) {
        // Update unit status in all open windows
        this.state.openIncidentWindows.forEach(window => {
            if (!window.closed) {
                window.postMessage({ type: 'unit_update', unit }, '*');
            }
        });
    },

    // Handle new incident
    _handleNewIncident(incident) {
        this.refreshDashboard();
    },

    // Refresh dashboard
    async refreshDashboard() {
        try {
            const response = await fetch('/api/incidents');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const incidents = await response.json();
            this._updateIncidentTable(incidents);
            
        } catch (error) {
            console.error('Error refreshing dashboard:', error);
        }
    },

    // Update incident table
    _updateIncidentTable(incidents) {
        const tbody = document.querySelector('#incidentsTable tbody');
        if (!tbody) return;

        tbody.innerHTML = incidents.map(incident => `
            <tr class="incident-row" data-incident-id="${incident.id}">
                <td>${incident.case_number}</td>
                <td>${incident.created_at}</td>
                <td>${incident.location}</td>
                <td>${incident.description}</td>
                <td><span class="badge bg-${this._getStatusClass(incident.status)}">${incident.status}</span></td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-sm btn-primary" onclick="DashboardManager.openIncident('${incident.id}')">
                            Open
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    },

    // Get status class
    _getStatusClass(status) {
        switch(status.toUpperCase()) {
            case 'OPEN': return 'primary';
            case 'IN_PROGRESS': return 'warning';
            case 'COMPLETED': return 'success';
            case 'CANCELLED': return 'danger';
            default: return 'secondary';
        }
    },

    // Setup auto-refresh
    _setupAutoRefresh() {
        if (this.state.refreshTimer) {
            clearInterval(this.state.refreshTimer);
        }

        this.state.refreshTimer = setInterval(() => {
            this.refreshDashboard();
        }, this.config.refreshInterval);
    },

    // Show alert
    _showAlert(message, type = 'info') {
        const toast = document.getElementById('toast');
        if (!toast) return;

        const toastInstance = bootstrap.Toast.getOrCreateInstance(toast);
        toast.className = `toast align-items-center text-white bg-${type} border-0`;
        toast.querySelector('.toast-body').textContent = message;
        toastInstance.show();
    },

    // Cleanup
    destroy() {
        if (this.state.refreshTimer) {
            clearInterval(this.state.refreshTimer);
        }
        if (this.state.ws) {
            this.state.ws.close();
        }
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const manager = DashboardManager.init();
    
    // Cleanup on page unload
    window.addEventListener('unload', () => {
        manager.destroy();
    });
});
