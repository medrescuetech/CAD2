/**
 * AMPDS Protocol management functionality
 */
class AmpdsManager {
    constructor() {
        this.categories = [];
        this.subcategories = [];
        this.currentCategory = null;
        this.currentProtocol = null;
        this.favorites = JSON.parse(localStorage.getItem('ampds_favorites') || '[]');
        this.recent = JSON.parse(localStorage.getItem('ampds_recent') || '[]');
        this.isAdminPage = window.location.pathname.includes('/admin/');
    }

    /**
     * Initialize AMPDS manager with required components
     */
    init() {
        // Load categories on init
        this.loadCategories();
        
        // Only initialize admin dashboard components when on the admin page
        if (this.isAdminPage) {
            this.initAdminComponents();
        }
        
        // Bind events for the protocol selection modal
        const quickSearch = document.getElementById('quickSearch');
        if (quickSearch) {
            quickSearch.addEventListener('input', (e) => {
                this.searchProtocols(e.target.value);
            });
        }
    }
    
    /**
     * Initialize admin-specific components
     */
    initAdminComponents() {
        // Only execute this code on admin pages
        const ampdsTable = document.querySelector('.ampds-table');
        if (ampdsTable) {
            this.loadAdminDashboard();
        }
    }

    /**
     * Load all AMPDS categories
     */
    async loadCategories() {
        try {
            const response = await fetch('/api/ampds/categories');
            const result = await response.json();
            
            if (result.success) {
                this.categories = result.categories;
                
                // Populate category dropdown if it exists
                const categorySelect = document.getElementById('category');
                if (categorySelect) {
                    categorySelect.innerHTML = '<option value="">Select Category</option>';
                    
                    this.categories.forEach(category => {
                        const option = document.createElement('option');
                        option.value = category;
                        option.textContent = category;
                        categorySelect.appendChild(option);
                    });
                }
            }
        } catch (error) {
            console.error('Error loading AMPDS categories:', error);
            IncidentManager._showAlert('error', 'Error loading AMPDS categories');
        }
    }

    /**
     * Update subcategories based on selected category
     * @param {string} category - Selected category
     */
    async updateSubCategories(category) {
        if (!category) {
            const subCategorySelect = document.getElementById('subCategory');
            if (subCategorySelect) {
                subCategorySelect.innerHTML = '<option value="">Select Sub-Category</option>';
            }
            return;
        }
        
        this.currentCategory = category;
        
        try {
            const response = await fetch(`/api/ampds/subcategories/${encodeURIComponent(category)}`);
            const result = await response.json();
            
            if (result.success) {
                this.subcategories = result.subcategories;
                
                // Populate subcategory dropdown
                const subCategorySelect = document.getElementById('subCategory');
                if (subCategorySelect) {
                    subCategorySelect.innerHTML = '<option value="">Select Sub-Category</option>';
                    
                    this.subcategories.forEach(subcategory => {
                        const option = document.createElement('option');
                        option.value = subcategory.unique_id;
                        option.textContent = `${subcategory.unique_id}: ${subcategory.subcategory}`;
                        option.dataset.priority = subcategory.priority;
                        option.dataset.advice = subcategory.dispatch_advice || '';
                        subCategorySelect.appendChild(option);
                    });
                }
            }
        } catch (error) {
            console.error('Error loading AMPDS subcategories:', error);
            IncidentManager._showAlert('error', 'Error loading subcategories');
        }
    }

    /**
     * Update card number field when subcategory is selected
     */
    updateCardNumber() {
        const subCategorySelect = document.getElementById('subCategory');
        const cardNumberInput = document.getElementById('cardNumber');
        
        if (subCategorySelect && cardNumberInput && subCategorySelect.value) {
            cardNumberInput.value = subCategorySelect.value;
            this.displayProtocolInfo(subCategorySelect.value);
        }
    }

    /**
     * Search for a protocol by card number
     * @param {string} cardNumber - Card number to search for
     */
    async searchByCardNumber(cardNumber) {
        if (!cardNumber) return;
        
        try {
            const response = await fetch(`/api/ampds/protocol/${encodeURIComponent(cardNumber)}`);
            const result = await response.json();
            
            if (result.success && result.protocol) {
                const protocol = result.protocol;
                this.currentProtocol = protocol;
                
                // Update category and subcategory dropdowns
                const categorySelect = document.getElementById('category');
                if (categorySelect) {
                    categorySelect.value = protocol.category;
                    await this.updateSubCategories(protocol.category);
                }
                
                const subCategorySelect = document.getElementById('subCategory');
                if (subCategorySelect) {
                    subCategorySelect.value = protocol.unique_id;
                }
                
                // Display protocol info
                this.displayProtocolInfo(protocol.unique_id);
            } else {
                IncidentManager._showAlert('error', 'Protocol not found');
            }
        } catch (error) {
            console.error('Error searching protocol by card number:', error);
            IncidentManager._showAlert('error', 'Error searching protocol');
        }
    }

    /**
     * Display protocol information
     * @param {string} uniqueId - Unique ID of the protocol
     */
    async displayProtocolInfo(uniqueId) {
        if (!uniqueId) return;
        
        try {
            const response = await fetch(`/api/ampds/protocol/${encodeURIComponent(uniqueId)}`);
            const result = await response.json();
            
            if (result.success && result.protocol) {
                const protocol = result.protocol;
                this.currentProtocol = protocol;
                
                // Show protocol info section
                const protocolInfoSection = document.getElementById('protocolInfo');
                if (protocolInfoSection) {
                    protocolInfoSection.style.display = 'block';
                }
                
                // Set priority level
                const priorityElement = document.getElementById('priorityLevel');
                if (priorityElement) {
                    priorityElement.textContent = protocol.priority;
                    priorityElement.className = `badge priority-${protocol.priority}`;
                }
                
                // Add to recent protocols
                this.addToRecent(protocol);
            }
        } catch (error) {
            console.error('Error loading protocol details:', error);
            IncidentManager._showAlert('error', 'Error loading protocol details');
        }
    }

    /**
     * Search for protocols based on keywords
     * @param {string} query - Search query
     */
    async searchProtocols(query) {
        if (!query || query.length < 2) return;
        
        try {
            const url = `/api/ampds/search?q=${encodeURIComponent(query)}`;
            const response = await fetch(url);
            const result = await response.json();
            
            if (result.success && result.protocols.length > 0) {
                // Take the first result and display it
                const protocol = result.protocols[0];
                this.currentProtocol = protocol;
                
                // Update card number
                const cardNumberInput = document.getElementById('cardNumber');
                if (cardNumberInput) {
                    cardNumberInput.value = protocol.unique_id;
                }
                
                // Update category and subcategory dropdowns
                const categorySelect = document.getElementById('category');
                if (categorySelect) {
                    categorySelect.value = protocol.category;
                    await this.updateSubCategories(protocol.category);
                }
                
                const subCategorySelect = document.getElementById('subCategory');
                if (subCategorySelect) {
                    subCategorySelect.value = protocol.unique_id;
                }
                
                // Display protocol info
                this.displayProtocolInfo(protocol.unique_id);
            }
        } catch (error) {
            console.error('Error searching protocols:', error);
            IncidentManager._showAlert('error', 'Error searching protocols');
        }
    }

    /**
     * View pre-arrival instructions PDF for the selected protocol
     */
    viewPreArrivalPDF() {
        if (!this.currentProtocol) {
            IncidentManager._showAlert('error', 'No protocol selected');
            return;
        }
        
        // Display PDF viewer
        const pdfViewer = document.getElementById('pdfViewer');
        if (pdfViewer) {
            pdfViewer.style.display = 'block';
            
            // Here you would add code to load the PDF for the current protocol
            // For example: pdfViewer.querySelector('iframe').src = `/api/ampds/protocol/${this.currentProtocol.unique_id}/pdf`;
        }
    }

    /**
     * Apply the selected protocol to the incident
     */
    applyProtocol() {
        if (!this.currentProtocol) {
            IncidentManager._showAlert('error', 'No protocol selected');
            return;
        }
        
        // Set the protocol in the incident form
        const ampdsCodeInput = document.getElementById('ampdsCode');
        if (ampdsCodeInput) {
            ampdsCodeInput.value = this.currentProtocol.unique_id;
        }
        
        const protocolNameInput = document.getElementById('protocolName');
        if (protocolNameInput) {
            protocolNameInput.value = this.currentProtocol.subcategory;
        }
        
        const priorityInput = document.getElementById('priority');
        if (priorityInput) {
            priorityInput.value = this.currentProtocol.priority;
        }
        
        // Add log entry
        IncidentManager._addLogEntry(`AMPDS Protocol ${this.currentProtocol.unique_id} (${this.currentProtocol.subcategory}) applied`, 'info');
        
        // Add to recent protocols
        this.addToRecent(this.currentProtocol);
        
        // Close the modal
        IncidentManager.medicalProtocolModal.hide();
        
        // Show success message
        IncidentManager._showAlert('success', 'Protocol applied successfully');
    }

    /**
     * Show recent protocols
     */
    showRecent() {
        // Implementation for displaying recent protocols
        console.log('Recent protocols:', this.recent);
    }

    /**
     * Show favorite protocols
     */
    showFavorites() {
        // Implementation for displaying favorite protocols
        console.log('Favorite protocols:', this.favorites);
    }

    /**
     * Toggle favorite status for current protocol
     */
    toggleFavorite() {
        if (!this.currentProtocol) return;
        
        const index = this.favorites.findIndex(p => p.unique_id === this.currentProtocol.unique_id);
        
        if (index === -1) {
            // Add to favorites
            this.favorites.push(this.currentProtocol);
            IncidentManager._showAlert('success', 'Added to favorites');
        } else {
            // Remove from favorites
            this.favorites.splice(index, 1);
            IncidentManager._showAlert('success', 'Removed from favorites');
        }
        
        // Save favorites to localStorage
        localStorage.setItem('ampds_favorites', JSON.stringify(this.favorites));
    }

    /**
     * Add protocol to recent list
     * @param {Object} protocol - Protocol to add to recent list
     */
    addToRecent(protocol) {
        // Remove if already exists
        const index = this.recent.findIndex(p => p.unique_id === protocol.unique_id);
        if (index !== -1) {
            this.recent.splice(index, 1);
        }
        
        // Add to beginning of recent list
        this.recent.unshift(protocol);
        
        // Keep only the last 10 items
        if (this.recent.length > 10) {
            this.recent.pop();
        }
        
        // Save to localStorage
        localStorage.setItem('ampds_recent', JSON.stringify(this.recent));
    }

    /**
     * Load admin dashboard
     */
    async loadAdminDashboard() {
        // Implementation for loading admin dashboard
    }
}

// Update the IncidentManager with AMPDS functionality
document.addEventListener('DOMContentLoaded', () => {
    // Create and initialize AMPDS manager if not already done
    if (!IncidentManager.ampdsManager) {
        IncidentManager.ampdsManager = new AmpdsManager();
        IncidentManager.ampdsManager.init();
    }
});
