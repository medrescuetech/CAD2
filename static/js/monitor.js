// Initialize monitor dashboard
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltips = document.querySelectorAll('[title]');
    tooltips.forEach(el => new bootstrap.Tooltip(el));
    
    // Initialize log modal
    const logModal = new bootstrap.Modal(document.getElementById('logModal'));
    
    // Add click handlers
    attachEventHandlers();
    
    // Start auto-refresh
    setInterval(refreshData, 30000); // Every 30 seconds
    
    // Add WebSocket integration
    const socket = io();

    socket.on('incident_update', (data) => {
        if (data.incidentId) {
            updateIncident(data);
        }
    });

    socket.on('unit_update', (data) => {
        if (data.unitId) {
            updateUnit(data);
        }
    });
});

// Attach all event handlers
function attachEventHandlers() {
    // View log buttons
    document.querySelectorAll('.view-log').forEach(button => {
        button.addEventListener('click', function() {
            const incidentId = this.dataset.incidentId;
            loadIncidentLog(incidentId);
            bootstrap.Modal.getInstance(document.getElementById('logModal')).show();
        });
    });
    
    // View on map buttons
    document.querySelectorAll('.view-map').forEach(button => {
        button.addEventListener('click', function() {
            const incidentId = this.dataset.incidentId;
            window.open(`/map?incident=${incidentId}`, '_blank');
        });
    });
}

// Toggle fullscreen mode
function toggleFullscreen() {
    const container = document.querySelector('.container-fluid');
    container.classList.toggle('fullscreen');
    
    const button = document.querySelector('[onclick="toggleFullscreen()"] i');
    button.classList.toggle('fa-expand');
    button.classList.toggle('fa-compress');
}

// Load incident log
async function loadIncidentLog(incidentId) {
    try {
        const response = await fetch(`/api/incidents/${incidentId}/logs`);
        const data = await response.json();
        
        if (data.success) {
            const logContainer = document.getElementById('incidentLog');
            logContainer.innerHTML = data.logs.map(log => `
                <div class="log-entry">
                    <div class="log-timestamp">
                        ${new Date(log.created_at).toLocaleString()}
                    </div>
                    <div class="log-message">
                        ${log.message}
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        handleError(error);
    }
}

// Refresh dashboard data
async function refreshData() {
    try {
        const response = await fetch('/api/monitor/data');
        const data = await response.json();
        
        if (data.success) {
            updateActiveIncidents(data.active_incidents);
            updateRecentIncidents(data.recent_incidents);
        }
    } catch (error) {
        handleError(error);
    }
}

// Update active incidents table
function updateActiveIncidents(incidents) {
    const tbody = document.getElementById('activeIncidents');
    tbody.innerHTML = incidents.map(incident => `
        <tr class="incident-row" data-incident-id="${incident.id}">
            <td>${incident.number}</td>
            <td>${new Date(incident.created_at).toLocaleTimeString()}</td>
            <td>${incident.location}</td>
            <td>${incident.problem}</td>
            <td>
                ${incident.assigned_units.map(unit => `
                    <span class="badge bg-${unit.status_color}">
                        ${unit.unit_number}
                    </span>
                `).join(' ')}
            </td>
            <td>
                <span class="badge bg-${incident.status_color}">
                    ${incident.status}
                </span>
            </td>
            <td>
                <button class="btn btn-sm btn-info view-log" 
                        data-incident-id="${incident.id}">
                    View Log
                </button>
            </td>
        </tr>
    `).join('');
    
    // Reattach event listeners
    attachLogHandlers();
}

// Update recent incidents table
function updateRecentIncidents(incidents) {
    const tbody = document.getElementById('recentIncidents');
    tbody.innerHTML = incidents.map(incident => `
        <tr>
            <td>${incident.number}</td>
            <td>${new Date(incident.created_at).toLocaleTimeString()}</td>
            <td>${incident.location}</td>
            <td>${incident.problem}</td>
            <td>
                ${incident.assigned_units.map(unit => `
                    <span class="badge bg-secondary">
                        ${unit.unit_number}
                    </span>
                `).join(' ')}
            </td>
            <td>${new Date(incident.closed_at).toLocaleTimeString()}</td>
        </tr>
    `).join('');
}

// Attach log button handlers
function attachLogHandlers() {
    document.querySelectorAll('.view-log').forEach(button => {
        button.addEventListener('click', function() {
            const incidentId = this.dataset.incidentId;
            loadIncidentLog(incidentId);
            bootstrap.Modal.getInstance(document.getElementById('logModal')).show();
        });
    });
}

// Add error handling
const handleError = (error) => {
    console.error(error);
    showAlert('danger', error.message || 'An error occurred');
    throw error;
};

// Add loading states
const setLoading = (isLoading) => {
    document.body.classList.toggle('loading', isLoading);
};

// Add map layer controls
const addLayerControls = () => {
    const baseLayers = {
        'OpenStreetMap': L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: ' OpenStreetMap contributors',
            maxZoom: 18,
            minZoom: 8
        }),
        'Satellite': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: ' Esri',
            maxZoom: 18,
            minZoom: 8
        })
    };

    const overlayLayers = {
        'Incidents': this.state.incidentLayer,
        'Units': this.state.unitLayer,
        'Pickup Points': this.state.pickupPointLayer
    };

    L.control.layers(baseLayers, overlayLayers).addTo(this.state.map);
};

// Add geolocation functionality
const locateUser = () => {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition((position) => {
            this.state.map.setView([position.coords.latitude, position.coords.longitude], 15);
        }, (error) => {
            console.error('Error getting location:', error);
            showAlert('warning', 'Unable to get your location');
        });
    } else {
        showAlert('warning', 'Geolocation is not supported by your browser');
    }
};

// Add search functionality
const addSearchControl = () => {
    const searchControl = new L.Control.Search({
        position: 'topright',
        layer: L.layerGroup([this.state.incidentLayer, this.state.unitLayer, this.state.pickupPointLayer]),
        propertyName: 'name',
        marker: false,
        moveToLocation: function(latlng, title, map) {
            map.setView(latlng, 15);
        }
    });

    searchControl.on('search:locationfound', function(e) {
        e.layer.openPopup();
    });

    this.state.map.addControl(searchControl);
};