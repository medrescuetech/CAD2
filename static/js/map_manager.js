class MapManager {
    static state = {
        map: null,
        markers: {},
        defaultLocation: [-20.7256, 116.8464],  // Port Hedland
        hospitalLocation: [-20.732023, 116.8404525],  // Port Hedland Hospital
        pickupPointMarkers: [],
        incidentMarkers: [],
        unitMarkers: [],
        settings: null,
        routeLayer: null
    };

    static async init(containerId) {
        try {
            // Load map settings from our new geospatial API
            const response = await fetch('/api/map/config');
            if (!response.ok) throw new Error('Failed to load map settings');
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'Failed to load map settings');
            
            this.state.settings = data.config;

            // Initialize map with configured settings
            const mapSettings = this.state.settings;
            
            this.state.map = L.map(containerId, {
                center: [
                    mapSettings.default_center.lat, 
                    mapSettings.default_center.lng
                ],
                zoom: mapSettings.default_zoom,
                maxZoom: 18,
                minZoom: 8,
                worldCopyJump: true,
                maxBounds: mapSettings.max_bounds || [[-90, -180], [90, 180]],
                maxBoundsViscosity: 1.0
            });
            
            // Add tile layer
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: ' OpenStreetMap contributors',
                maxZoom: 18,
                minZoom: 8
            }).addTo(this.state.map);
            
            // Initialize marker layers
            this.state.pickupPointLayer = L.layerGroup().addTo(this.state.map);
            this.state.incidentLayer = L.layerGroup().addTo(this.state.map);
            this.state.unitLayer = L.layerGroup().addTo(this.state.map);
            this.state.routeLayer = L.layerGroup().addTo(this.state.map);
            
            // Add hospital marker
            L.marker([this.state.hospitalLocation[0], this.state.hospitalLocation[1]], {
                icon: L.divIcon({
                    className: 'hospital-marker',
                    html: '<i class="fas fa-hospital"></i>',
                    iconSize: [25, 25]
                })
            })
            .bindPopup('Main Hospital')
            .addTo(this.state.map);
            
            // Initialize markers arrays
            this.state.pickupPointMarkers = [];
            this.state.incidentMarkers = [];
            this.state.unitMarkers = [];
            
            // Load initial data using our new Geospatial API
            await this.loadMapData();
            
            // Set up event listeners for the control buttons
            this.setupEventListeners();
            
            // Set up real-time updates
            this.initializeWebSocket();
            
            // Setup map controls
            this.setupMapControls();
            
            return true;
        } catch (error) {
            console.error('Error initializing map:', error);
            return false;
        }
    }
    
    static createLegendContent() {
        return `
            <h6>Unit Location Types</h6>
            <div class="legend-item">
                <div class="legend-icon" style="border: 3px solid #28a745; background: #fff;"></div>
                <span class="legend-text">At Incident Location</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="border: 2px dashed #28a745; background: #f8f9fa;"></div>
                <span class="legend-text">At Home Base</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="border: 2px dotted #28a745; background: #f8f9fa; opacity: 0.9;"></div>
                <span class="legend-text">At Default Location</span>
            </div>
            <h6 class="mt-3">Unit Status</h6>
            <div class="legend-item">
                <div class="legend-icon" style="border-color: #28a745;"></div>
                <span class="legend-text">Available</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="border-color: #ffc107;"></div>
                <span class="legend-text">Assigned</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="border-color: #17a2b8;"></div>
                <span class="legend-text">En Route</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="border-color: #dc3545;"></div>
                <span class="legend-text">On Scene</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="border-color: #6c757d; opacity: 0.7;"></div>
                <span class="legend-text">Out of Service</span>
            </div>
        `;
    }

    static setupMapControls() {
        // Add layer control
        const baseLayers = {
            'OpenStreetMap': L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: ' OpenStreetMap contributors'
            }),
            'Satellite': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
                attribution: ' Esri'
            })
        };

        const overlays = {
            'Incidents': this.state.incidentLayer,
            'Units': this.state.unitLayer,
            'Pickup Points': this.state.pickupPointLayer,
            'Routes': this.state.routeLayer
        };

        L.control.layers(baseLayers, overlays).addTo(this.state.map);
        
        // Add scale control
        L.control.scale().addTo(this.state.map);

        // Add legend
        const legend = L.control({ position: 'bottomright' });
        legend.onAdd = () => {
            const div = L.DomUtil.create('div', 'map-legend leaflet-bar');
            div.innerHTML = this.createLegendContent();
            return div;
        };
        legend.addTo(this.state.map);
    }
    
    static setupEventListeners() {
        // Center map button
        const centerMapBtn = document.getElementById('centerMap');
        if (centerMapBtn) {
            centerMapBtn.addEventListener('click', () => {
                this.centerMap();
            });
        }
        
        // Toggle layer buttons
        const toggleIncidentsBtn = document.getElementById('toggleIncidents');
        if (toggleIncidentsBtn) {
            toggleIncidentsBtn.addEventListener('click', () => {
                if (this.state.map.hasLayer(this.state.incidentLayer)) {
                    this.state.map.removeLayer(this.state.incidentLayer);
                    toggleIncidentsBtn.classList.remove('btn-primary');
                    toggleIncidentsBtn.classList.add('btn-outline-primary');
                } else {
                    this.state.map.addLayer(this.state.incidentLayer);
                    toggleIncidentsBtn.classList.remove('btn-outline-primary');
                    toggleIncidentsBtn.classList.add('btn-primary');
                }
            });
        }
        
        const toggleUnitsBtn = document.getElementById('toggleUnits');
        if (toggleUnitsBtn) {
            toggleUnitsBtn.addEventListener('click', () => {
                if (this.state.map.hasLayer(this.state.unitLayer)) {
                    this.state.map.removeLayer(this.state.unitLayer);
                    toggleUnitsBtn.classList.remove('btn-primary');
                    toggleUnitsBtn.classList.add('btn-outline-primary');
                } else {
                    this.state.map.addLayer(this.state.unitLayer);
                    toggleUnitsBtn.classList.remove('btn-outline-primary');
                    toggleUnitsBtn.classList.add('btn-primary');
                }
            });
        }
        
        const togglePickupPointsBtn = document.getElementById('togglePickupPoints');
        if (togglePickupPointsBtn) {
            togglePickupPointsBtn.addEventListener('click', () => {
                if (this.state.map.hasLayer(this.state.pickupPointLayer)) {
                    this.state.map.removeLayer(this.state.pickupPointLayer);
                    togglePickupPointsBtn.classList.remove('btn-primary');
                    togglePickupPointsBtn.classList.add('btn-outline-primary');
                } else {
                    this.state.map.addLayer(this.state.pickupPointLayer);
                    togglePickupPointsBtn.classList.remove('btn-outline-primary');
                    togglePickupPointsBtn.classList.add('btn-primary');
                }
            });
        }
    }
    
    static centerMap() {
        if (this.state.settings && this.state.settings.default_center) {
            this.state.map.setView(
                [this.state.settings.default_center.lat, this.state.settings.default_center.lng],
                this.state.settings.default_zoom
            );
        }
    }

    static async loadMapData() {
        try {
            const response = await fetch('/api/map/data');
            if (!response.ok) throw new Error('Failed to load map data');
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Failed to load map data');
            }
            
            // Process units
            if (data.data.units) {
                this.updateUnitMarkers(data.data.units);
            }
            
            // Process incidents
            if (data.data.incidents) {
                this.updateIncidentMarkers(data.data.incidents);
            }
            
            return true;
        } catch (error) {
            console.error('Error loading map data:', error);
            return false;
        }
    }
    
    static updateIncidentMarkers(incidents) {
        // Clear existing incident markers
        this.state.incidentLayer.clearLayers();
        this.state.incidentMarkers = [];
        
        incidents.forEach(incident => {
            if (incident.latitude && incident.longitude) {
                // Customize icon based on priority
                const priorityClass = incident.priority ? 
                    `priority-${incident.priority.toLowerCase()}` : '';
                
                const marker = L.marker([incident.latitude, incident.longitude], {
                    icon: L.divIcon({
                        className: `incident-marker ${priorityClass}`,
                        html: `<i class="fas fa-exclamation-triangle"></i>
                               <div class="incident-number">${incident.incident_number}</div>`,
                        iconSize: [40, 40],
                        iconAnchor: [20, 40],
                        popupAnchor: [0, -40]
                    })
                });
                
                // Create popup content
                const popupContent = `
                    <div class="incident-popup">
                        <h3>${incident.incident_number}</h3>
                        <p><strong>Type:</strong> ${incident.type || 'N/A'}</p>
                        <p><strong>Priority:</strong> ${incident.priority || 'N/A'}</p>
                        <p><strong>Status:</strong> ${incident.status || 'N/A'}</p>
                        <p><strong>Location:</strong> ${incident.address || 'N/A'}</p>
                        <div class="mt-2">
                            <button class="btn btn-sm btn-primary" 
                                    onclick="window.location.href='/incident/${incident.incident_id}'">
                                View Details
                            </button>
                            <button class="btn btn-sm btn-outline-primary" 
                                    onclick="MapManager.findNearestUnits(${incident.incident_id})">
                                Find Nearest Units
                            </button>
                        </div>
                    </div>
                `;
                
                marker.bindPopup(popupContent);
                marker.incident_id = incident.incident_id;
                marker.addTo(this.state.incidentLayer);
                this.state.incidentMarkers.push(marker);
            }
        });
    }
    
    static updateUnitMarkers(units) {
        // Clear existing unit markers
        this.state.unitMarkers.forEach(marker => {
            this.state.unitLayer.removeLayer(marker);
        });
        this.state.unitMarkers = [];

        units.forEach(unit => {
            if (!unit.latitude || !unit.longitude) return;

            // Create marker icon based on unit type and status
            const markerIcon = this.createUnitMarkerIcon(unit);

            // Create the marker
            const marker = L.marker([unit.latitude, unit.longitude], {
                icon: markerIcon,
                title: unit.unit_name
            });

            // Create popup content with location source information
            let popupContent = `
                <div class="unit-popup">
                    <h6>${unit.unit_name}</h6>
                    <p class="status ${unit.status.toLowerCase()}">${unit.status}</p>
                    <p class="location-source">Location: ${this.getLocationSourceLabel(unit.source)}</p>
                    <p class="address">${unit.address || 'No address available'}</p>
                    <p class="timestamp">Last updated: ${this.formatTimestamp(unit.timestamp)}</p>
                </div>
            `;

            marker.bindPopup(popupContent);
            marker.addTo(this.state.unitLayer);
            this.state.unitMarkers.push(marker);
        });
    }

    static getLocationSourceLabel(source) {
        const sourceMap = {
            'incident_assignment': 'At Incident Location',
            'home_location': 'At Home Base',
            'default_location': 'At Default Location'
        };
        return sourceMap[source] || 'Unknown';
    }

    static createUnitMarkerIcon(unit) {
        // Base class for the marker
        let markerClass = 'unit-marker';
        
        // Add status class
        if (unit.status) {
            markerClass += ` status-${unit.status.toLowerCase()}`;
        }
        
        // Add location source class
        if (unit.source) {
            markerClass += ` source-${unit.source}`;
        }

        // Create different icons based on unit type
        let iconHtml = '<i class="fas fa-ambulance"></i>';
        if (unit.unit_type) {
            switch(unit.unit_type.toLowerCase()) {
                case 'ambulance':
                    iconHtml = '<i class="fas fa-ambulance"></i>';
                    break;
                case 'fire':
                    iconHtml = '<i class="fas fa-fire-truck"></i>';
                    break;
                case 'police':
                    iconHtml = '<i class="fas fa-police-car"></i>';
                    break;
                case 'helicopter':
                    iconHtml = '<i class="fas fa-helicopter"></i>';
                    break;
                default:
                    iconHtml = '<i class="fas fa-truck-medical"></i>';
            }
        }

        return L.divIcon({
            className: markerClass,
            html: iconHtml,
            iconSize: [30, 30],
            iconAnchor: [15, 15],
            popupAnchor: [0, -15]
        });
    }

    static formatTimestamp(timestamp) {
        if (!timestamp) return 'Unknown';
        const date = new Date(timestamp);
        return date.toLocaleString();
    }
    
    static async findNearestUnits(incidentId) {
        try {
            const response = await fetch(`/api/map/nearest-units/${incidentId}?limit=5&maxDistance=30`);
            if (!response.ok) throw new Error('Failed to find nearest units');
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Failed to find nearest units');
            }
            
            const units = data.units;
            
            // Create a popup with the list of nearest units
            let popupContent = `
                <div class="nearest-units-popup">
                    <h3>Nearest Available Units</h3>
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>Unit</th>
                                <th>Distance</th>
                                <th>ETA</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
            `;
            
            units.forEach(unit => {
                popupContent += `
                    <tr>
                        <td>${unit.unit_name}</td>
                        <td>${unit.distance_km} km</td>
                        <td>${unit.estimated_arrival_minutes} min</td>
                        <td>
                            <button class="btn btn-xs btn-primary" 
                                    onclick="MapManager.showRouteToIncident(${unit.unit_id}, ${incidentId})">
                                Route
                            </button>
                        </td>
                    </tr>
                `;
            });
            
            popupContent += `
                        </tbody>
                    </table>
                </div>
            `;
            
            // Find the incident marker and open a popup with the nearest units
            const incidentMarker = this.state.incidentMarkers.find(marker => marker.incident_id === incidentId);
            if (incidentMarker) {
                incidentMarker.setPopupContent(popupContent);
                incidentMarker.openPopup();
            } else {
                // Create a temporary popup if the incident marker is not found
                const incident = await this.getIncidentLocation(incidentId);
                if (incident && incident.latitude && incident.longitude) {
                    L.popup()
                        .setLatLng([incident.latitude, incident.longitude])
                        .setContent(popupContent)
                        .openOn(this.state.map);
                }
            }
        } catch (error) {
            console.error('Error finding nearest units:', error);
            alert('Error finding nearest units: ' + error.message);
        }
    }
    
    static async getIncidentLocation(incidentId) {
        try {
            const response = await fetch(`/api/map/incidents/${incidentId}`);
            if (!response.ok) throw new Error('Failed to get incident location');
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Failed to get incident location');
            }
            
            return data.location;
        } catch (error) {
            console.error('Error getting incident location:', error);
            return null;
        }
    }
    
    static async getUnitLocation(unitId) {
        try {
            const response = await fetch(`/api/map/units/${unitId}`);
            if (!response.ok) throw new Error('Failed to get unit location');
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Failed to get unit location');
            }
            
            return data.location;
        } catch (error) {
            console.error('Error getting unit location:', error);
            return null;
        }
    }
    
    static async showRouteToIncident(unitId, incidentId) {
        try {
            // Get unit and incident locations
            const unitLocation = await this.getUnitLocation(unitId);
            const incidentLocation = await this.getIncidentLocation(incidentId);
            
            if (!unitLocation || !incidentLocation) {
                throw new Error('Could not determine locations for routing');
            }
            
            // Calculate route
            const response = await fetch(`/api/map/route?startLat=${unitLocation.latitude}&startLng=${unitLocation.longitude}&endLat=${incidentLocation.latitude}&endLng=${incidentLocation.longitude}`);
            if (!response.ok) throw new Error('Failed to calculate route');
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Failed to calculate route');
            }
            
            // Clear existing routes
            this.state.routeLayer.clearLayers();
            
            // Draw the route on the map
            const routePoints = data.route.route_geometry.map(point => [point[0], point[1]]);
            
            const routeLine = L.polyline(routePoints, {
                color: '#FF5722',
                weight: 5,
                opacity: 0.7,
                dashArray: '10, 10',
                lineCap: 'round'
            }).addTo(this.state.routeLayer);
            
            // Create popup with route info
            const popupContent = `
                <div class="route-popup">
                    <h3>Route Information</h3>
                    <p><strong>Distance:</strong> ${data.route.distance_km} km</p>
                    <p><strong>Estimated Time:</strong> ${data.route.duration_minutes} minutes</p>
                    <p><strong>From:</strong> ${data.route.start_address}</p>
                    <p><strong>To:</strong> ${data.route.end_address}</p>
                </div>
            `;
            
            routeLine.bindPopup(popupContent);
            routeLine.openPopup();
            
            // Zoom to show the entire route
            this.state.map.fitBounds(routeLine.getBounds(), { padding: [50, 50] });
            
        } catch (error) {
            console.error('Error showing route:', error);
            alert('Error calculating route: ' + error.message);
        }
    }
    
    static initializeWebSocket() {
        const socket = io();
        
        socket.on('incident_update', (data) => {
            // Refresh all map data when an incident is updated
            this.loadMapData();
        });
        
        socket.on('unit_update', (data) => {
            // Refresh all map data when a unit is updated
            this.loadMapData();
        });
    }
    
    static loadFallbackTileLayer() {
        // Fallback to Carto basemap if OpenStreetMap fails
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png', {
            attribution: ' OpenStreetMap contributors, CARTO',
            maxZoom: 18,
            minZoom: 8,
            subdomains: 'abcd'
        }).addTo(this.state.map);
    }
    
    static async geocodeAddress(address) {
        try {
            const response = await fetch(`/api/geocode?address=${encodeURIComponent(address)}`);
            if (!response.ok) throw new Error('Failed to geocode address');
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Failed to geocode address');
            }
            
            return data.result;
        } catch (error) {
            console.error('Error geocoding address:', error);
            return null;
        }
    }
}
