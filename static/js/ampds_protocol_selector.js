/**
 * AMPDS Protocol Selector for Incidents
 * 
 * This module handles the selection of AMPDS protocols within the incident form
 * by allowing users to either:
 * 1. Select by category and subcategory
 * 2. Directly enter a card number
 */
class AmpdsProtocolSelector {
    constructor() {
        this.categories = [];
        this.subcategories = {};
        this.selectedProtocol = null;
        this.modal = null;
        this.incidentId = null;
    }

    /**
     * Initialize the protocol selector
     */
    init() {
        // Store reference to the modal
        this.modal = new bootstrap.Modal(document.getElementById('ampdsProtocolSelectionModal'));
        
        // Get incident ID if we're editing an existing incident
        const incidentDataEl = document.getElementById('incidentData');
        if (incidentDataEl && incidentDataEl.textContent) {
            try {
                const incidentData = JSON.parse(incidentDataEl.textContent);
                this.incidentId = incidentData.id;
                
                // If incident has AMPDS code, show it in the badge
                if (incidentData.ampds_code) {
                    this.updateSelectedProtocolBadge(incidentData.ampds_code);
                }
            } catch (e) {
                console.error('Error parsing incident data:', e);
            }
        }
        
        // Initialize event listeners
        this._initEventListeners();
        
        // Load categories on init
        this._loadCategories();
    }

    /**
     * Initialize event listeners for protocol selection
     */
    _initEventListeners() {
        // Category selection changes
        const categorySelect = document.getElementById('ampdsCategory');
        if (categorySelect) {
            categorySelect.addEventListener('change', () => {
                this._handleCategoryChange(categorySelect.value);
            });
        }
        
        // Subcategory selection changes
        const subcategorySelect = document.getElementById('ampdsSubCategory');
        if (subcategorySelect) {
            subcategorySelect.addEventListener('change', () => {
                this._handleSubcategoryChange(subcategorySelect.value);
            });
        }
        
        // Card number search
        const searchCardBtn = document.getElementById('searchCardBtn');
        if (searchCardBtn) {
            searchCardBtn.addEventListener('click', () => {
                const cardNumber = document.getElementById('ampdsCardNumber').value.trim();
                if (cardNumber) {
                    this._searchProtocolByCardNumber(cardNumber);
                }
            });
            
            // Allow pressing Enter in the card number input
            const cardNumberInput = document.getElementById('ampdsCardNumber');
            if (cardNumberInput) {
                cardNumberInput.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        searchCardBtn.click();
                    }
                });
            }
        }
        
        // Protocol selection button
        const selectBtn = document.getElementById('selectAmpdsProtocolBtn');
        if (selectBtn) {
            selectBtn.addEventListener('click', () => {
                this._selectCurrentProtocol();
            });
        }
        
        // When modal is shown
        const modalEl = document.getElementById('ampdsProtocolSelectionModal');
        if (modalEl) {
            modalEl.addEventListener('shown.bs.modal', () => {
                // Try to load protocol suggestions based on incident type
                const incidentTypeSelect = document.getElementById('incidentType');
                if (incidentTypeSelect && incidentTypeSelect.value) {
                    this._loadProtocolSuggestions(incidentTypeSelect.value);
                }
            });
        }
    }

    /**
     * Load all AMPDS categories
     */
    async _loadCategories() {
        try {
            const response = await fetch('/api/ampds/categories');
            const data = await response.json();
            
            if (data.categories) {
                this.categories = data.categories;
                
                // Populate category dropdown
                const categorySelect = document.getElementById('ampdsCategory');
                if (categorySelect) {
                    // Clear existing options
                    categorySelect.innerHTML = '<option value="">Select Category</option>';
                    
                    // Add each category as an option
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
            this._showError('Unable to load protocol categories. Please try again.');
        }
    }

    /**
     * Handle category selection change
     * @param {string} category - Selected category
     */
    async _handleCategoryChange(category) {
        const subcategorySelect = document.getElementById('ampdsSubCategory');
        
        // Reset subcategory dropdown
        if (subcategorySelect) {
            subcategorySelect.innerHTML = '<option value="">Select Sub-Category</option>';
            subcategorySelect.disabled = !category;
        }
        
        // Hide protocol details
        document.getElementById('protocolDetails').style.display = 'none';
        
        if (!category) return;
        
        try {
            // Load subcategories for the selected category
            const response = await fetch(`/api/ampds/protocols?category=${encodeURIComponent(category)}`);
            const data = await response.json();
            
            if (data.protocols && data.protocols.length > 0) {
                // Store subcategories for this category
                this.subcategories[category] = data.protocols;
                
                // Populate subcategory dropdown
                data.protocols.forEach(protocol => {
                    const option = document.createElement('option');
                    option.value = protocol.unique_id;
                    option.textContent = `${protocol.unique_id}: ${protocol.subcategory}`;
                    option.dataset.protocol = JSON.stringify(protocol);
                    subcategorySelect.appendChild(option);
                });
                
                // Enable subcategory select
                subcategorySelect.disabled = false;
            } else {
                this._showError(`No subcategories found for ${category}`);
            }
        } catch (error) {
            console.error(`Error loading subcategories for ${category}:`, error);
            this._showError('Unable to load protocol subcategories. Please try again.');
        }
    }

    /**
     * Handle subcategory selection change
     * @param {string} uniqueId - Selected protocol unique ID
     */
    async _handleSubcategoryChange(uniqueId) {
        if (!uniqueId) {
            document.getElementById('protocolDetails').style.display = 'none';
            return;
        }
        
        try {
            // Update the card number input to match the selected protocol
            document.getElementById('ampdsCardNumber').value = uniqueId;
            
            // Get protocol details
            await this._loadProtocolDetails(uniqueId);
        } catch (error) {
            console.error(`Error handling subcategory change for ${uniqueId}:`, error);
        }
    }

    /**
     * Search for a protocol by card number
     * @param {string} cardNumber - Card number to search for
     */
    async _searchProtocolByCardNumber(cardNumber) {
        try {
            // Load protocol details for the entered card number
            await this._loadProtocolDetails(cardNumber);
            
            // If a protocol was found, update the category and subcategory selects
            if (this.selectedProtocol) {
                // Set the category
                const categorySelect = document.getElementById('ampdsCategory');
                if (categorySelect) {
                    categorySelect.value = this.selectedProtocol.category;
                    
                    // Load subcategories for this category
                    await this._handleCategoryChange(this.selectedProtocol.category);
                    
                    // Set the subcategory
                    const subcategorySelect = document.getElementById('ampdsSubCategory');
                    if (subcategorySelect) {
                        subcategorySelect.value = this.selectedProtocol.unique_id;
                    }
                }
            }
        } catch (error) {
            console.error(`Error searching for protocol with card number ${cardNumber}:`, error);
            this._showError('Unable to find protocol with the specified card number.');
        }
    }

    /**
     * Load protocol details by unique ID
     * @param {string} uniqueId - Protocol unique ID
     */
    async _loadProtocolDetails(uniqueId) {
        try {
            const response = await fetch(`/api/ampds/protocols/${encodeURIComponent(uniqueId)}`);
            const data = await response.json();
            
            if (data.protocol) {
                // Store the selected protocol
                this.selectedProtocol = data.protocol;
                
                // Update protocol details display
                document.getElementById('protocolCode').textContent = data.protocol.unique_id;
                document.getElementById('protocolCategory').textContent = data.protocol.category;
                document.getElementById('protocolCardNumber').textContent = data.protocol.card_number || data.protocol.unique_id;
                
                const priorityEl = document.getElementById('protocolPriority');
                priorityEl.textContent = data.protocol.priority;
                priorityEl.className = `badge bg-${this._getPriorityColor(data.protocol.priority)}`;
                
                document.getElementById('protocolAdvice').textContent = 
                    data.protocol.dispatch_advice || 'No specific dispatch advice available for this protocol.';
                
                // Show protocol details
                document.getElementById('protocolDetails').style.display = 'block';
                
                // Enable select button
                document.getElementById('selectAmpdsProtocolBtn').disabled = false;
                
                return true;
            } else {
                this._showError(`Protocol not found with ID: ${uniqueId}`);
                return false;
            }
        } catch (error) {
            console.error(`Error loading protocol details for ${uniqueId}:`, error);
            this._showError('Unable to load protocol details. Please try again.');
            return false;
        }
    }

    /**
     * Load protocol suggestions based on incident type
     * @param {string} incidentType - Type of incident
     */
    async _loadProtocolSuggestions(incidentType) {
        try {
            const response = await fetch(`/api/ampds/suggest_by_type?type=${encodeURIComponent(incidentType)}`);
            const data = await response.json();
            
            if (data.protocols && data.protocols.length > 0) {
                console.log(`Loaded ${data.protocols.length} suggested protocols for ${incidentType}`);
                // We have suggested protocols, but we won't auto-select them
                // Just log them for now - this could be enhanced to display suggestions in the UI
            }
        } catch (error) {
            console.error(`Error loading protocol suggestions for ${incidentType}:`, error);
        }
    }

    /**
     * Select the current protocol and apply it to the incident
     */
    _selectCurrentProtocol() {
        if (!this.selectedProtocol) {
            this._showError('Please select a protocol first.');
            return;
        }
        
        // Update the hidden field with the selected protocol ID
        const protocolIdInput = document.getElementById('ampdsProtocolId');
        if (protocolIdInput) {
            protocolIdInput.value = this.selectedProtocol.unique_id;
        }
        
        // Update the protocol badge
        this.updateSelectedProtocolBadge(this.selectedProtocol.unique_id);
        
        // Add a log entry if we have an incident ID (editing an existing incident)
        if (this.incidentId) {
            // Log the protocol selection in the incident log
            this._addProtocolLogEntry(this.selectedProtocol);
        }
        
        // Close the modal
        this.modal.hide();
        
        // Show success message
        this._showSuccess(`AMPDS Protocol ${this.selectedProtocol.unique_id} selected.`);
    }

    /**
     * Add a log entry for the selected protocol
     * @param {Object} protocol - Selected protocol
     */
    _addProtocolLogEntry(protocol) {
        // Check if we have the incident manager available
        if (typeof addLogEntry === 'function') {
            const message = `AMPDS Protocol ${protocol.unique_id} (${protocol.subcategory}) selected. Priority: ${protocol.priority}`;
            addLogEntry(this.incidentId, message, 'status');
        }
    }

    /**
     * Update the protocol badge in the incident form
     * @param {string} protocolId - Selected protocol ID
     */
    updateSelectedProtocolBadge(protocolId) {
        const badgeEl = document.getElementById('selectedProtocolBadge');
        if (badgeEl) {
            badgeEl.textContent = protocolId;
            badgeEl.style.display = protocolId ? 'inline-block' : 'none';
        }
    }

    /**
     * Get the appropriate Bootstrap color class for a priority
     * @param {string} priority - Protocol priority
     * @returns {string} Bootstrap color class
     */
    _getPriorityColor(priority) {
        switch (priority) {
            case 'HIGH':
                return 'danger';
            case 'MEDIUM':
                return 'warning';
            case 'LOW':
                return 'success';
            default:
                return 'secondary';
        }
    }

    /**
     * Show an error message
     * @param {string} message - Error message
     */
    _showError(message) {
        if (typeof showAlert === 'function') {
            showAlert('danger', message);
        } else {
            alert(message);
        }
    }

    /**
     * Show a success message
     * @param {string} message - Success message
     */
    _showSuccess(message) {
        if (typeof showAlert === 'function') {
            showAlert('success', message);
        } else {
            alert(message);
        }
    }
}

// Initialize AMPDS Protocol Selector when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.ampdsProtocolSelector = new AmpdsProtocolSelector();
    window.ampdsProtocolSelector.init();
});
