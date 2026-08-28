// Unit Management Module
const UnitManager = {
    // Configuration
    config: {
        refreshInterval: 30000,
        maxRetries: 3,
        retryDelay: 5000,
        validationRules: {
            callsign: {
                required: true,
                pattern: '^[A-Z0-9-]{3,10}$'
            },
            type: {
                required: true,
                values: ['AMBULANCE', 'FIRE', 'POLICE', 'RESCUE']
            },
            status: {
                required: true,
                values: [
                    'AVAILABLE',
                    'MEAL_BREAK',
                    'OUT_OF_SERVICE',
                    'EN_ROUTE',
                    'ARRIVED',
                    'LOADED',
                    'AT_MEDICAL_CENTRE',
                    'PATROL',
                    'RETURNING'
                ]
            }
        }
    },

    // State management
    state: {
        units: new Map(),
        selectedUnit: null,
        isLoading: false,
        lastUpdate: null,
        errorCount: 0,
        websocket: null
    },

    // Initialize unit management
    init() {
        this._setupWebSocket();
        this._setupEventListeners();
        this._setupValidation();
        this._initializeMap();
        this._startPeriodicRefresh();
        return this;
    },

    // Setup WebSocket for real-time updates
    _setupWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/units`;
        
        this.state.websocket = new WebSocket(wsUrl);
        
        this.state.websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this._handleRealtimeUpdate(data);
        };

        this.state.websocket.onclose = () => {
            setTimeout(() => this._setupWebSocket(), 5000);
        };
    },

    // Handle real-time updates
    _handleRealtimeUpdate(data) {
        switch(data.type) {
            case 'unit_update':
                this._updateUnit(data.unit);
                break;
            case 'unit_location':
                this._updateUnitLocation(data.unit);
                break;
            case 'unit_status':
                this._updateUnitStatus(data.unit);
                break;
        }
    },

    // Setup event listeners
    _setupEventListeners() {
        // Unit list click handler
        document.getElementById('unit-list')?.addEventListener('click', (e) => {
            const unitItem = e.target.closest('.unit-item');
            if (unitItem) {
                this._selectUnit(unitItem.dataset.unitId);
            }
        });

        // Status change handler
        document.getElementById('unit-status')?.addEventListener('change', (e) => {
            if (this.state.selectedUnit) {
                this._updateUnitStatus(this.state.selectedUnit, e.target.value);
            }
        });

        // Form submission handler
        const form = document.getElementById('unit-form');
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                if (!this._validateForm()) {
                    this._showAlert('Please correct the errors before submitting.', 'warning');
                    return;
                }
                await this._submitForm(new FormData(form));
            });
        }

        // Filter input handler
        document.getElementById('unit-filter')?.addEventListener('input', (e) => {
            this._filterUnits(e.target.value);
        });
    },

    // Setup form validation
    _setupValidation() {
        const form = document.getElementById('unit-form');
        if (!form) return;

        // Add validation attributes
        Object.entries(this.config.validationRules).forEach(([field, rules]) => {
            const input = form.querySelector(`[name="${field}"]`);
            if (!input) return;

            if (rules.required) {
                input.required = true;
            }
            if (rules.pattern) {
                input.pattern = rules.pattern;
            }
            if (rules.values) {
                input.dataset.validValues = JSON.stringify(rules.values);
            }
        });
    },

    // Validate form
    _validateForm() {
        const form = document.getElementById('unit-form');
        if (!form) return true;

        let isValid = true;
        const fields = form.querySelectorAll('input, select');

        fields.forEach(field => {
            if (!this._validateField(field)) {
                isValid = false;
            }
        });

        return isValid;
    },

    // Validate individual field
    _validateField(field) {
        const rules = this.config.validationRules[field.name];
        if (!rules) return true;

        let isValid = true;
        const errorMessages = [];

        // Required validation
        if (rules.required && !field.value.trim()) {
            isValid = false;
            errorMessages.push('This field is required');
        }

        // Pattern validation
        if (rules.pattern && !new RegExp(rules.pattern).test(field.value)) {
            isValid = false;
            errorMessages.push('Invalid format');
        }

        // Values validation
        if (rules.values && !rules.values.includes(field.value)) {
            isValid = false;
            errorMessages.push('Invalid value selected');
        }

        this._updateFieldValidationUI(field, isValid, errorMessages);
        return isValid;
    },

    // Update field validation UI
    _updateFieldValidationUI(field, isValid, messages) {
        const container = field.closest('.form-group');
        if (!container) return;

        // Remove existing validation classes and feedback
        container.classList.remove('has-success', 'has-error');
        container.querySelectorAll('.invalid-feedback').forEach(el => el.remove());

        // Add appropriate validation class
        container.classList.add(isValid ? 'has-success' : 'has-error');

        // Add error messages if any
        if (!isValid && messages.length > 0) {
            const feedback = document.createElement('div');
            feedback.className = 'invalid-feedback';
            feedback.textContent = messages.join('. ');
            field.parentNode.appendChild(feedback);
        }
    },

    // Initialize map
    _initializeMap() {
        const mapContainer = document.getElementById('unit-map');
        if (!mapContainer) return;

        this.map = L.map('unit-map').setView([51.505, -0.09], 13);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(this.map);

        // Add markers for all units
        this.state.units.forEach(unit => {
            if (unit.latitude && unit.longitude) {
                this._addUnitMarker(unit);
            }
        });
    },

    // Add unit marker to map
    _addUnitMarker(unit) {
        if (!this.map) return;

        const marker = L.marker([unit.latitude, unit.longitude])
            .bindPopup(this._createUnitPopup(unit))
            .addTo(this.map);

        // Store marker reference
        unit.marker = marker;
    },

    // Create unit popup content
    _createUnitPopup(unit) {
        return `
            <div class="unit-popup">
                <h6>${unit.callsign}</h6>
                <p>Type: ${unit.type}</p>
                <p>Status: ${unit.status}</p>
                <p>Last Updated: ${new Date(unit.lastUpdate).toLocaleTimeString()}</p>
                <button class="btn btn-sm btn-primary" 
                        onclick="UnitManager._selectUnit('${unit.id}')">
                    View Details
                </button>
            </div>
        `;
    },

    // Start periodic refresh
    _startPeriodicRefresh() {
        setInterval(() => this.refreshUnits(), this.config.refreshInterval);
    },

    // Refresh units data
    async refreshUnits() {
        if (this.state.isLoading) return;

        try {
            this.state.isLoading = true;
            this._showLoading(true);

            const response = await fetch('/api/units', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const data = await response.json();
            this._updateUnits(data.units);
            
            this.state.lastUpdate = new Date();
            this.state.errorCount = 0;
            
        } catch (error) {
            console.error('Units refresh failed:', error);
            this.state.errorCount++;
            
            if (this.state.errorCount >= this.config.maxRetries) {
                this._showAlert('Failed to refresh units. Please reload the page.', 'error');
            } else {
                setTimeout(() => this.refreshUnits(), this.config.retryDelay);
            }
        } finally {
            this.state.isLoading = false;
            this._showLoading(false);
        }
    },

    // Update units data
    _updateUnits(units) {
        // Update state
        units.forEach(unit => {
            this.state.units.set(unit.id, unit);
        });

        // Update UI
        this._updateUnitList();
        this._updateMapMarkers();
        this._updateStatistics();
    },

    // Update unit list UI
    _updateUnitList() {
        const list = document.getElementById('unit-list');
        if (!list) return;

        list.innerHTML = '';
        this.state.units.forEach(unit => {
            const item = document.createElement('div');
            item.className = 'unit-item';
            item.dataset.unitId = unit.id;
            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-center p-2 border-bottom">
                    <div>
                        <strong>${unit.callsign}</strong>
                        <span class="badge bg-${this._getStatusClass(unit.status)} ms-2">
                            ${unit.status}
                        </span>
                    </div>
                    <div>
                        <button class="btn btn-sm btn-outline-primary me-2" 
                                onclick="UnitManager._selectUnit('${unit.id}')">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-secondary" 
                                onclick="UnitManager._showUnitLocation('${unit.id}')">
                            <i class="fas fa-map-marker-alt"></i>
                        </button>
                    </div>
                </div>
            `;
            list.appendChild(item);
        });
    },

    // Update map markers
    _updateMapMarkers() {
        if (!this.map) return;

        // Clear existing markers
        this.map.eachLayer((layer) => {
            if (layer instanceof L.Marker) {
                this.map.removeLayer(layer);
            }
        });

        // Add markers for all units
        this.state.units.forEach(unit => {
            if (unit.latitude && unit.longitude) {
                this._addUnitMarker(unit);
            }
        });
    },

    // Update statistics
    _updateStatistics() {
        const stats = {
            total: this.state.units.size,
            available: 0,
            busy: 0,
            outOfService: 0
        };

        this.state.units.forEach(unit => {
            switch(unit.status) {
                case 'AVAILABLE':
                    stats.available++;
                    break;
                case 'BUSY':
                    stats.busy++;
                    break;
                case 'OUT_OF_SERVICE':
                    stats.outOfService++;
                    break;
            }
        });

        // Update statistics in UI
        Object.entries(stats).forEach(([key, value]) => {
            const element = document.getElementById(`stat-${key}`);
            if (element) {
                element.textContent = value;
            }
        });
    },

    // Select unit
    _selectUnit(unitId) {
        const unit = this.state.units.get(unitId);
        if (!unit) return;

        this.state.selectedUnit = unit;
        this._updateUnitDetails(unit);

        // Center map on selected unit
        if (this.map && unit.latitude && unit.longitude) {
            this.map.setView([unit.latitude, unit.longitude], 15);
        }
    },

    // Update unit details
    _updateUnitDetails(unit) {
        const details = document.getElementById('unit-details');
        if (!details) return;

        details.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <h5 class="card-title mb-0">
                        ${unit.callsign}
                        <span class="badge bg-${this._getStatusClass(unit.status)} ms-2">
                            ${unit.status}
                        </span>
                    </h5>
                </div>
                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">Type</label>
                        <input type="text" class="form-control" value="${unit.type}" readonly>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Status</label>
                        <select class="form-select" id="unit-status">
                            ${this._createStatusOptions(unit.status)}
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Last Updated</label>
                        <input type="text" class="form-control" 
                               value="${new Date(unit.lastUpdate).toLocaleString()}" readonly>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Current Location</label>
                        <input type="text" class="form-control" 
                               value="${unit.latitude}, ${unit.longitude}" readonly>
                    </div>
                </div>
            </div>
        `;
    },

    // Create status options
    _createStatusOptions(currentStatus) {
        return this.config.validationRules.status.values
            .map(status => `
                <option value="${status}" ${status === currentStatus ? 'selected' : ''}>
                    ${status}
                </option>
            `)
            .join('');
    },

    // Get status class for badges
    _getStatusClass(status) {
        switch(status) {
            case 'AVAILABLE':
                return 'success';
            case 'MEAL_BREAK':
                return 'info';
            case 'OUT_OF_SERVICE':
                return 'danger';
            case 'EN_ROUTE':
                return 'primary';
            case 'ARRIVED':
                return 'warning';
            case 'LOADED':
                return 'warning';
            case 'AT_MEDICAL_CENTRE':
                return 'warning';
            case 'PATROL':
                return 'info';
            case 'RETURNING':
                return 'primary';
            default:
                return 'secondary';
        }
    },

    // Filter units
    _filterUnits(query) {
        const list = document.getElementById('unit-list');
        if (!list) return;

        const items = list.querySelectorAll('.unit-item');
        const lowerQuery = query.toLowerCase();

        items.forEach(item => {
            const text = item.textContent.toLowerCase();
            item.style.display = text.includes(lowerQuery) ? '' : 'none';
        });
    },

    // Show unit location on map
    _showUnitLocation(unitId) {
        const unit = this.state.units.get(unitId);
        if (!unit || !this.map) return;

        if (unit.latitude && unit.longitude) {
            this.map.setView([unit.latitude, unit.longitude], 15);
            if (unit.marker) {
                unit.marker.openPopup();
            }
        } else {
            this._showAlert('No location data available for this unit', 'warning');
        }
    },

    // Show/hide loading state
    _showLoading(show) {
        const container = document.getElementById('unit-container');
        if (!container) return;

        container.classList.toggle('loading', show);
    },

    // Show alert message
    _showAlert(message, level = 'info', duration = 5000) {
        const alertContainer = document.getElementById('alert-container');
        if (!alertContainer) return;

        const alert = document.createElement('div');
        alert.className = `alert alert-${level} alert-dismissible fade show`;
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        alertContainer.appendChild(alert);
        if (duration > 0) {
            setTimeout(() => alert.remove(), duration);
        }
    },

    // Cleanup
    destroy() {
        if (this.state.websocket) {
            this.state.websocket.close();
        }
        if (this.map) {
            this.map.remove();
        }
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const manager = UnitManager.init();
    
    // Cleanup on page unload
    window.addEventListener('unload', () => {
        manager.destroy();
    });
});