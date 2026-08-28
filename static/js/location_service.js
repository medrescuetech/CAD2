/**
 * LocationService - A JavaScript class for managing location services
 * 
 * This class handles location-related operations such as:
 * - Location search and autocomplete
 * - Map integration and marker handling
 * - Geocoding and reverse geocoding
 */
class LocationService {
    /**
     * Initialize the LocationService
     * 
     * @param {Object} options - Configuration options
     * @param {string} options.apiBase - Base URL for location API endpoints
     * @param {HTMLElement} options.mapContainer - Container element for the map
     * @param {HTMLElement} options.searchInput - Input element for location search
     * @param {HTMLElement} options.suggestionsContainer - Container for location suggestions
     * @param {Function} options.onLocationSelect - Callback when a location is selected
     */
    constructor(options = {}) {
        this.apiBase = options.apiBase || '/locations';
        this.mapContainer = options.mapContainer;
        this.searchInput = options.searchInput;
        this.suggestionsContainer = options.suggestionsContainer;
        this.onLocationSelect = options.onLocationSelect || function() {};
        
        this.map = null;
        this.marker = null;
        this.selectedLocation = null;
        this.searchTimeout = null;
        
        this.init();
    }
    
    /**
     * Initialize the LocationService
     */
    init() {
        if (this.mapContainer) {
            this.initializeMap();
        }
        
        if (this.searchInput) {
            this.initializeSearch();
        }
    }
    
    /**
     * Initialize the map
     * 
     * @param {Array} center - Initial center coordinates [lat, lng]
     * @param {number} zoom - Initial zoom level
     */
    initializeMap(center = [0, 0], zoom = 13) {
        if (!this.mapContainer) return;
        
        // Create map
        this.map = L.map(this.mapContainer).setView(center, zoom);
        
        // Add tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(this.map);
        
        // Add marker
        this.marker = L.marker(center, { draggable: true }).addTo(this.map);
        
        // Handle marker drag events
        this.marker.on('dragend', (e) => {
            const latlng = this.marker.getLatLng();
            this.reverseGeocode(latlng.lat, latlng.lng);
        });
        
        // Handle map click events
        this.map.on('click', (e) => {
            this.marker.setLatLng(e.latlng);
            this.reverseGeocode(e.latlng.lat, e.latlng.lng);
        });
        
        // Fix map rendering issues when container is initially hidden
        setTimeout(() => this.map.invalidateSize(), 100);
    }
    
    /**
     * Initialize search functionality
     */
    initializeSearch() {
        if (!this.searchInput) return;
        
        // Add input event listener for search
        this.searchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            
            // Clear previous timeout
            clearTimeout(this.searchTimeout);
            
            // Clear suggestions if query is empty
            if (!query) {
                this.clearSuggestions();
                return;
            }
            
            // Set new timeout for search
            this.searchTimeout = setTimeout(() => {
                this.searchLocations(query);
            }, 300);
        });
        
        // Add focus event listener
        this.searchInput.addEventListener('focus', (e) => {
            const query = e.target.value.trim();
            if (query) {
                this.searchLocations(query);
            }
        });
        
        // Add blur event listener to hide suggestions when focus is lost
        this.searchInput.addEventListener('blur', (e) => {
            // Delay hiding suggestions to allow for clicks on suggestions
            setTimeout(() => {
                this.clearSuggestions();
            }, 200);
        });
    }
    
    /**
     * Search for locations
     * 
     * @param {string} query - Search query
     */
    async searchLocations(query) {
        try {
            // Build URL
            let url = `${this.apiBase}?q=${encodeURIComponent(query)}&active=true`;
            
            // Fetch results
            const response = await fetch(url);
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Failed to search locations');
            }
            
            // Display suggestions
            this.displaySuggestions(data.locations);
        } catch (error) {
            console.error('Error searching locations:', error);
            this.clearSuggestions();
        }
    }
    
    /**
     * Display location suggestions
     * 
     * @param {Array} locations - Array of location objects
     */
    displaySuggestions(locations) {
        if (!this.suggestionsContainer) return;
        
        // Clear existing suggestions
        this.clearSuggestions();
        
        // Check if there are locations to display
        if (!locations || !locations.length) {
            this.suggestionsContainer.style.display = 'none';
            return;
        }
        
        // Create suggestions elements
        locations.forEach(location => {
            const item = document.createElement('a');
            item.className = 'dropdown-item';
            item.href = '#';
            item.textContent = location.name;
            
            // Add click event listener
            item.addEventListener('click', (e) => {
                e.preventDefault();
                this.selectLocation(location);
            });
            
            this.suggestionsContainer.appendChild(item);
        });
        
        // Show suggestions
        this.suggestionsContainer.style.display = 'block';
    }
    
    /**
     * Clear location suggestions
     */
    clearSuggestions() {
        if (!this.suggestionsContainer) return;
        
        // Clear suggestions container
        this.suggestionsContainer.innerHTML = '';
        this.suggestionsContainer.style.display = 'none';
    }
    
    /**
     * Select a location
     * 
     * @param {Object} location - Location object
     */
    selectLocation(location) {
        // Store selected location
        this.selectedLocation = location;
        
        // Update search input
        if (this.searchInput) {
            this.searchInput.value = location.name;
        }
        
        // Update map if available
        if (this.map && this.marker) {
            const latlng = [location.latitude, location.longitude];
            this.map.setView(latlng, 15);
            this.marker.setLatLng(latlng);
        }
        
        // Clear suggestions
        this.clearSuggestions();
        
        // Call onLocationSelect callback
        if (typeof this.onLocationSelect === 'function') {
            this.onLocationSelect(location);
        }
    }
    
    /**
     * Geocode an address to get coordinates
     * 
     * @param {string} address - Address to geocode
     * @returns {Promise} - Promise resolving to geocoded result
     */
    async geocode(address) {
        try {
            const url = `${this.apiBase}/geocode?address=${encodeURIComponent(address)}`;
            const response = await fetch(url);
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Geocoding failed');
            }
            
            return data.result;
        } catch (error) {
            console.error('Geocoding error:', error);
            throw error;
        }
    }
    
    /**
     * Reverse geocode coordinates to get address
     * 
     * @param {number} lat - Latitude
     * @param {number} lng - Longitude
     */
    async reverseGeocode(lat, lng) {
        try {
            const url = `${this.apiBase}/reverse_geocode?lat=${lat}&lng=${lng}`;
            const response = await fetch(url);
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Reverse geocoding failed');
            }
            
            // Create a location object from the result
            const location = {
                id: null, // This is a temporary location
                name: data.result.address,
                latitude: lat,
                longitude: lng,
                active: true
            };
            
            // Select this location
            this.selectLocation(location);
            
            return data.result;
        } catch (error) {
            console.error('Reverse geocoding error:', error);
            
            // Even if reverse geocoding fails, we still want to select the location
            // with just the coordinates
            const location = {
                id: null,
                name: `Location at ${lat.toFixed(6)}, ${lng.toFixed(6)}`,
                latitude: lat,
                longitude: lng,
                active: true
            };
            
            this.selectLocation(location);
            
            throw error;
        }
    }
    
    /**
     * Get the current selected location
     * 
     * @returns {Object|null} - Selected location or null
     */
    getSelectedLocation() {
        return this.selectedLocation;
    }
    
    /**
     * Set the map view to a specific location
     * 
     * @param {number} lat - Latitude
     * @param {number} lng - Longitude
     * @param {number} zoom - Zoom level
     */
    setMapView(lat, lng, zoom = 15) {
        if (!this.map) return;
        
        this.map.setView([lat, lng], zoom);
        
        if (this.marker) {
            this.marker.setLatLng([lat, lng]);
        }
    }
    
    /**
     * Create a new location
     * 
     * @param {Object} locationData - Location data
     * @returns {Promise} - Promise resolving to created location
     */
    async createLocation(locationData) {
        try {
            const response = await fetch(this.apiBase, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(locationData)
            });
            
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Failed to create location');
            }
            
            return data.location;
        } catch (error) {
            console.error('Error creating location:', error);
            throw error;
        }
    }
    
    /**
     * Update an existing location
     * 
     * @param {number} locationId - ID of the location to update
     * @param {Object} locationData - Updated location data
     * @returns {Promise} - Promise resolving to updated location
     */
    async updateLocation(locationId, locationData) {
        try {
            const response = await fetch(`${this.apiBase}/${locationId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(locationData)
            });
            
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Failed to update location');
            }
            
            return data.location;
        } catch (error) {
            console.error('Error updating location:', error);
            throw error;
        }
    }
    
    /**
     * Delete a location
     * 
     * @param {number} locationId - ID of the location to delete
     * @returns {Promise} - Promise resolving to success status
     */
    async deleteLocation(locationId) {
        try {
            const response = await fetch(`${this.apiBase}/${locationId}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Failed to delete location');
            }
            
            return true;
        } catch (error) {
            console.error('Error deleting location:', error);
            throw error;
        }
    }
}

// Export the LocationService class for use in other files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LocationService;
}
