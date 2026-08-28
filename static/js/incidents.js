// Incidents page functionality

let socket = io();
let currentPage = 1;
let itemsPerPage = 20;
let totalItems = 0;
let isLoading = false;
let hasMoreData = true;

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips and other Bootstrap components
    Utils.initializeBootstrapComponents();
    
    // Setup double-click on incident rows
    document.querySelectorAll('#incidentsTable tbody tr').forEach(row => {
        row.addEventListener('dblclick', () => {
            const incidentId = row.getAttribute('data-incident-id');
            if (incidentId) {
                viewIncident(incidentId);
            }
        });
    });

    // Register keyboard shortcuts
    shortcutManager.registerMany({
        'Ctrl+N': () => showNewIncident(),
        'ArrowUp': () => {
            const selected = document.querySelector('#incidentsTable tbody tr.selected');
            if (selected && selected.previousElementSibling) {
                selectRow(selected.previousElementSibling);
            } else {
                const rows = document.querySelectorAll('#incidentsTable tbody tr');
                if (rows.length > 0) {
                    selectRow(rows[rows.length - 1]);
                }
            }
        },
        'ArrowDown': () => {
            const selected = document.querySelector('#incidentsTable tbody tr.selected');
            if (selected && selected.nextElementSibling) {
                selectRow(selected.nextElementSibling);
            } else {
                const rows = document.querySelectorAll('#incidentsTable tbody tr');
                if (rows.length > 0) {
                    selectRow(rows[0]);
                }
            }
        },
        'Enter': () => {
            const selected = document.querySelector('#incidentsTable tbody tr.selected');
            if (selected) {
                const incidentId = selected.getAttribute('data-incident-id');
                if (incidentId) {
                    viewIncident(incidentId);
                }
            }
        }
    });
    
    // Initialize lazy loading
    initLazyLoading();
    
    // Load initial data
    loadIncidents();
});

// Initialize lazy loading for incidents table
function initLazyLoading() {
    // Set up scroll event on the incidents container
    const container = document.querySelector('.table-responsive');
    if (container) {
        container.addEventListener('scroll', function() {
            // If we're within 200px of the bottom, load more
            if (container.scrollHeight - container.scrollTop - container.clientHeight < 200) {
                if (!isLoading && hasMoreData) {
                    loadMoreIncidents();
                }
            }
        });
    }
    
    // Set up the load more button if it exists
    const loadMoreBtn = document.getElementById('loadMoreIncidents');
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', function() {
            if (!isLoading && hasMoreData) {
                loadMoreIncidents();
            }
        });
    }
}

// Load incidents with pagination
function loadIncidents(reset = false) {
    if (reset) {
        currentPage = 1;
        document.querySelector('#incidentsTable tbody').innerHTML = '';
        hasMoreData = true;
    }
    
    if (isLoading || !hasMoreData) return;
    isLoading = true;
    
    // Show loading indicator
    const loadingIndicator = document.getElementById('incidentsLoading');
    if (loadingIndicator) loadingIndicator.style.display = 'block';
    
    // Make API request with pagination parameters
    fetch(`/api/incidents?page=${currentPage}&per_page=${itemsPerPage}`)
        .then(response => response.json())
        .then(data => {
            // Hide loading indicator
            if (loadingIndicator) loadingIndicator.style.display = 'none';
            
            if (data.incidents && data.incidents.length > 0) {
                // Render incidents
                renderIncidents(data.incidents);
                
                // Update pagination info
                totalItems = data.total;
                currentPage++;
                hasMoreData = data.incidents.length >= itemsPerPage;
                
                // Update UI elements
                updatePaginationStatus();
            } else {
                hasMoreData = false;
                updatePaginationStatus();
            }
            
            isLoading = false;
        })
        .catch(error => {
            console.error('Error loading incidents:', error);
            if (loadingIndicator) loadingIndicator.style.display = 'none';
            isLoading = false;
        });
}

// Load more incidents (next page)
function loadMoreIncidents() {
    loadIncidents(false);
}

// Render incidents to the table
function renderIncidents(incidents) {
    const tbody = document.querySelector('#incidentsTable tbody');
    
    incidents.forEach(incident => {
        const row = document.createElement('tr');
        row.setAttribute('data-incident-id', incident.id);
        row.innerHTML = `
            <td>${incident.case_number}</td>
            <td>${incident.incident_type.name}</td>
            <td>${incident.location}</td>
            <td>${incident.status}</td>
            <td>${incident.priority}</td>
            <td>${formatDateTime(incident.created_at)}</td>
            <td>
                <button class="btn btn-sm btn-primary view-incident" onclick="viewIncident(${incident.id})">
                    <i class="fas fa-eye"></i>
                </button>
                ${incident.status !== 'Closed' ? 
                    `<button class="btn btn-sm btn-warning close-incident" onclick="closeIncident(${incident.id})">
                        <i class="fas fa-check"></i>
                    </button>` : ''}
            </td>
        `;
        tbody.appendChild(row);
    });
}

// Update pagination status UI
function updatePaginationStatus() {
    const status = document.getElementById('paginationStatus');
    const loadMoreBtn = document.getElementById('loadMoreIncidents');
    
    if (status) {
        status.textContent = `Showing ${Math.min((currentPage - 1) * itemsPerPage + 1, totalItems)}-${Math.min(currentPage * itemsPerPage - (itemsPerPage - document.querySelectorAll('#incidentsTable tbody tr').length), totalItems)} of ${totalItems} incidents`;
    }
    
    if (loadMoreBtn) {
        loadMoreBtn.style.display = hasMoreData ? 'block' : 'none';
    }
}

// Format date for display
function formatDateTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString();
}

function selectRow(row) {
    document.querySelectorAll('#incidentsTable tbody tr').forEach(r => r.classList.remove('selected'));
    row.classList.add('selected');
}

function viewIncident(id) {
    window.location.href = `/incidents/${id}`;
}

function showNewIncident() {
    document.getElementById('newIncidentModal').classList.add('show');
    document.getElementById('newIncidentModal').style.display = 'block';
    document.body.classList.add('modal-open');
}

function createIncident(form) {
    const formData = new FormData(form);
    const data = {
        type: formData.get('type'),
        priority: formData.get('priority'),
        location: formData.get('location'),
        description: formData.get('description')
    };

    socket.emit('create_incident', data);
    bootstrap.Modal.getInstance(document.getElementById('newIncidentModal')).hide();
    return false;
}

function closeIncident(incidentId) {
    if (confirm('Are you sure you want to close this incident?')) {
        socket.emit('update_incident_status', {
            incident_id: incidentId,
            status: 'closed'
        });
    }
}

function refreshIncidentsList() {
    loadIncidents(true);
}

// Handle active incidents response - modified to support lazy loading
socket.on('active_incidents', (data) => {
    if (data.reset) {
        loadIncidents(true);
    } else if (data.incident) {
        // If it's a single incident update
        updateSingleIncident(data.incident);
    }
});

// Update a single incident in the table if it exists
function updateSingleIncident(incident) {
    const existingRow = document.querySelector(`#incidentsTable tbody tr[data-incident-id="${incident.id}"]`);
    
    if (existingRow) {
        // Update the existing row
        existingRow.innerHTML = `
            <td>${incident.case_number}</td>
            <td>${incident.incident_type.name}</td>
            <td>${incident.location}</td>
            <td>${incident.status}</td>
            <td>${incident.priority}</td>
            <td>${formatDateTime(incident.created_at)}</td>
            <td>
                <button class="btn btn-sm btn-primary view-incident" onclick="viewIncident(${incident.id})">
                    <i class="fas fa-eye"></i>
                </button>
                ${incident.status !== 'Closed' ? 
                    `<button class="btn btn-sm btn-warning close-incident" onclick="closeIncident(${incident.id})">
                        <i class="fas fa-check"></i>
                    </button>` : ''}
            </td>
        `;
    } else if (incident.status !== 'Closed') {
        // If it's a new incident and not closed, add it to the top
        const tbody = document.querySelector('#incidentsTable tbody');
        const row = document.createElement('tr');
        row.setAttribute('data-incident-id', incident.id);
        row.innerHTML = `
            <td>${incident.case_number}</td>
            <td>${incident.incident_type.name}</td>
            <td>${incident.location}</td>
            <td>${incident.status}</td>
            <td>${incident.priority}</td>
            <td>${formatDateTime(incident.created_at)}</td>
            <td>
                <button class="btn btn-sm btn-primary view-incident" onclick="viewIncident(${incident.id})">
                    <i class="fas fa-eye"></i>
                </button>
                <button class="btn btn-sm btn-warning close-incident" onclick="closeIncident(${incident.id})">
                    <i class="fas fa-check"></i>
                </button>
            </td>
        `;
        if (tbody.firstChild) {
            tbody.insertBefore(row, tbody.firstChild);
        } else {
            tbody.appendChild(row);
        }
        
        // Update total count
        totalItems++;
        updatePaginationStatus();
    }
}
