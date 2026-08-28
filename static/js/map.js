// Map initialization and update functions
let map;
let markers = [];
let socket;

function initMap() {
    // Initialize WebSocket connection
    socket = io();
    
    // Request default location
    socket.emit('get_default_location');
    
    // Listen for default location response
    socket.on('default_location_result', function(data) {
        const location = data.location;
        map = L.map('map').setView(
            [location.latitude, location.longitude], 
            13 // Default zoom level
        );

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: ' OpenStreetMap contributors'
        }).addTo(map);

        // Now that map is initialized, request initial data
        socket.emit('get_active_incidents');
        socket.emit('get_active_units');
    });
    
    // Listen for location search results
    socket.on('locations_search_result', function(data) {
        updateLocationMarkers(data.locations);
    });
    
    // Listen for incident updates
    socket.on('incident_update', function(data) {
        updateIncidentMarkers(data.incidents);
    });
    
    // Listen for unit updates
    socket.on('unit_update', function(data) {
        updateUnitMarkers(data.units);
    });
}

function searchLocation(query) {
    socket.emit('search_locations', { query: query });
}

function updateLocationMarkers(locations) {
    // Clear existing location markers
    markers.forEach(marker => {
        if (marker.type === 'location') {
            map.removeLayer(marker);
        }
    });
    markers = markers.filter(marker => marker.type !== 'location');
    
    // Add new location markers
    locations.forEach(location => {
        const marker = L.marker([location.latitude, location.longitude], {
            icon: L.divIcon({
                className: 'location-marker',
                html: `<i class="fas fa-map-marker-alt"></i>`,
                iconSize: [25, 25]
            })
        });
        marker.type = 'location';
        marker.bindPopup(`<strong>${location.name}</strong>`);
        marker.addTo(map);
        markers.push(marker);
    });
}

function updateIncidentMarkers(incidents) {
    // Clear existing incident markers
    markers.forEach(marker => {
        if (marker.type === 'incident') {
            map.removeLayer(marker);
        }
    });
    markers = markers.filter(marker => marker.type !== 'incident');
    
    // Add new incident markers
    incidents.forEach(incident => {
        if (incident.latitude && incident.longitude) {
            const marker = L.marker([incident.latitude, incident.longitude], {
                icon: L.divIcon({
                    className: `incident-marker priority-${incident.priority}`,
                    html: `<i class="fas fa-exclamation-triangle"></i>`,
                    iconSize: [25, 25]
                })
            });
            marker.type = 'incident';
            marker.bindPopup(`
                <strong>Incident #${incident.incident_number}</strong><br>
                Type: ${incident.incident_type}<br>
                Priority: ${incident.priority}<br>
                Status: ${incident.status}
            `);
            marker.addTo(map);
            markers.push(marker);
        }
    });
}

function updateUnitMarkers(units) {
    // Clear existing unit markers
    markers.forEach(marker => {
        if (marker.type === 'unit') {
            map.removeLayer(marker);
        }
    });
    markers = markers.filter(marker => marker.type !== 'unit');
    
    // Add new unit markers
    units.forEach(unit => {
        if (unit.latitude && unit.longitude) {
            const marker = L.marker([unit.latitude, unit.longitude], {
                icon: L.divIcon({
                    className: `unit-marker status-${unit.status}`,
                    html: `<i class="fas fa-truck"></i>`,
                    iconSize: [25, 25]
                })
            });
            marker.type = 'unit';
            marker.bindPopup(`
                <strong>Unit ${unit.unit_number}</strong><br>
                Type: ${unit.unit_type}<br>
                Status: ${unit.status}
            `);
            marker.addTo(map);
            markers.push(marker);
        }
    });
}

// Initialize map when DOM is loaded
document.addEventListener('DOMContentLoaded', initMap);