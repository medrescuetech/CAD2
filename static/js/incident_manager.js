class IncidentManager {
    constructor(formId) {
        this.form = document.getElementById(formId);
        this.locationInput = document.getElementById('location');
        this.locationIdInput = document.getElementById('location_id');
        this.latitudeInput = document.getElementById('latitude');
        this.longitudeInput = document.getElementById('longitude');
        this.statusSelect = document.getElementById('status');
        this.liveLogContainer = document.getElementById('liveLog');
        
        this.state = {
            incident: null,
            units: [],
            liveLog: [],
            locationSearchTimeout: null,
            locationSuggestions: [],
            map: null,
            marker: null,
            ampdsModal: null,
            medicalProtocolModal: null,
            protocolData: null
        };
        
        this.setupEventListeners();
        this.initializeData();
    }
    
    async initializeData() {
        // Initialize modals
        this.state.ampdsModal = new bootstrap.Modal(document.getElementById('ampdsModal'));
        this.state.medicalProtocolModal = new bootstrap.Modal(document.getElementById('medicalProtocolModal'));
        
        // Load incident data if editing
        const incidentDataElem = document.getElementById('incidentData');
        if (incidentDataElem && incidentDataElem.textContent && incidentDataElem.textContent.trim() !== '{}') {
            try {
                this.state.incident = JSON.parse(incidentDataElem.textContent);
                this.populateForm(this.state.incident);
                // Refresh assigned units if editing an incident
                this.refreshAssignedUnits();
            } catch (error) {
                console.error('Error parsing incident data:', error);
                this._showAlert('error', 'Error loading incident data');
            }
        } else {
            // New incident - get case number from backend and set datetime
            const now = new Date();
            const createdAtField = document.getElementById('createdAt');
            if (createdAtField) createdAtField.value = now.toLocaleString();
            
            // Get case number from backend
            try {
                const response = await fetch('/api/incidents/next-case-number');
                const data = await response.json();
                if (data.success) {
                    const caseNumberField = document.getElementById('caseNumber');
                    if (caseNumberField) caseNumberField.value = data.caseNumber;
                    
                    // Auto-create and save the new incident with initial data
                    await this.createInitialIncident();
                } else {
                    console.error('Error getting case number:', data.message);
                    this._showAlert('error', 'Error getting case number');
                }
            } catch (error) {
                console.error('Error getting case number:', error);
                this._showAlert('error', 'Error getting case number');
            }
            
            if (this.liveLogContainer) {
                this._addLogEntry('New incident created', 'status');
            }
        }
        
        // Initialize additional components as needed
        this.initializeQuickNotePresets();
        this.initializePickupPoints();
        this.loadMedicalProtocols();
        
        // Add event handlers for medical protocols
        document.getElementById('medicalCategory').addEventListener('change', this.handleCategoryChange.bind(this));
        document.getElementById('medicalSubcategory').addEventListener('change', this.handleSubcategoryChange.bind(this));
        document.getElementById('medicalCardNumber').addEventListener('input', debounce(this.handleCardNumberSearch.bind(this), 500));
    }
    
    async createInitialIncident() {
        try {
            // Collect initial form data
            const formData = new FormData(this.form);
            const data = Object.fromEntries(formData.entries());
            
            // Set API endpoint and method
            const method = 'POST';
            const url = '/api/incidents';
            
            console.log(`[DB_OPERATION] Creating new incident to ${url} with method ${method}`);
            
            // Submit form data as JSON
            const response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: JSON.stringify(data)
            });
            
            // Handle response
            if (!response.ok) {
                const errorData = await response.json();
                console.error(`[DB_OPERATION] Failed to create incident: ${errorData.message || 'Unknown error'}`);
                throw new Error(errorData.message || 'Failed to create incident');
            }
            
            const result = await response.json();
            console.log(`[DB_OPERATION] Incident created successfully`, result);
            
            // Update incident ID in form
            this.form.dataset.incidentId = result.incident.id;
            
            // Add to log
            this._addLogEntry(`Incident created successfully`, 'success');
            
            // Show success message
            this._showAlert('success', 'Incident created successfully');
            
        } catch (error) {
            console.error('[DB_OPERATION] Error creating incident:', error);
            this._showAlert('danger', 'Failed to create incident: ' + error.message);
        }
    }
    
    setupEventListeners() {
        // Handle form submission
        this.form.addEventListener('submit', this.handleSubmit.bind(this));
        
        // Handle status changes
        if (this.statusSelect) {
            this.statusSelect.addEventListener('change', this.handleStatusChange.bind(this));
        }
        
        // Handle location selection
        if (this.locationInput) {
            this.locationInput.addEventListener('input', debounce(this.searchLocation.bind(this), 300));
        }
        
        // Setup auto-save for fields
        this.setupAutoSave();
        
        // Quick note submission
        const quickNoteForm = document.getElementById('quickNoteForm');
        if (quickNoteForm) {
            quickNoteForm.addEventListener('submit', this.handleQuickNoteSubmit.bind(this));
        }
        
        // Unit status modal submission
        const unitStatusForm = document.getElementById('unitStatusForm');
        if (unitStatusForm) {
            unitStatusForm.addEventListener('submit', this.handleUnitStatusSubmit.bind(this));
        }
        
        // Dispatch unit button
        const dispatchUnitBtn = document.getElementById('dispatchUnit');
        if (dispatchUnitBtn) {
            dispatchUnitBtn.addEventListener('click', this.handleDispatchUnit.bind(this));
        }
        
        // Close incident button
        const closeIncidentBtn = document.getElementById('closeIncident');
        if (closeIncidentBtn) {
            closeIncidentBtn.addEventListener('click', this.handleCloseIncident.bind(this));
        }
        
        // PDF Report button
        const pdfBtn = document.getElementById('pdfReport');
        if (pdfBtn) {
            pdfBtn.addEventListener('click', this.handlePdfReport.bind(this));
        }
    }
    
    setupAutoSave() {
        // Auto-save on field blur
        const fields = this.form.querySelectorAll('input, select, textarea');
        fields.forEach(field => {
            // Skip read-only fields or those that shouldn't trigger auto-save
            if (field.readOnly || field.id === 'caseNumber' || field.id === 'createdAt') {
                return;
            }
            
            // Set proper event listener based on field type
            if (field.tagName === 'SELECT' || field.type === 'checkbox' || field.type === 'radio') {
                field.addEventListener('change', this.autoSave.bind(this));
            } else {
                // For text inputs, textareas, etc.
                field.addEventListener('blur', this.autoSave.bind(this));
                
                // Also add input event with debounce for real-time saving
                field.addEventListener('input', debounce(this.autoSave.bind(this), 1000));
            }
        });
        
        // Log that auto-save is active
        console.log('[AUTO_SAVE] Auto-save functionality enabled for incident form');
    }
    
    async autoSave(e) {
        // Don't auto-save if no incident ID exists yet
        if (!this.form.dataset.incidentId) {
            console.log('[AUTO_SAVE] No incident ID yet, skipping auto-save');
            return;
        }
        
        const fieldName = e.target.name;
        const fieldValue = e.target.value;
        const fieldType = e.target.type;
        
        console.log(`[AUTO_SAVE] Auto-saving field ${fieldName} with value ${fieldValue}`);
        
        try {
            // Prepare the update data
            const updateData = {};
            updateData[fieldName] = fieldType === 'checkbox' ? e.target.checked : fieldValue;
            
            // Set API endpoint
            const url = `/api/incidents/${this.form.dataset.incidentId}`;
            
            // Submit only the changed field
            const response = await fetch(url, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: JSON.stringify(updateData)
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                console.error(`[AUTO_SAVE] Failed to save ${fieldName}: ${errorData.message || 'Unknown error'}`);
                // Show a non-intrusive indicator that save failed
                this._showAutoSaveStatus(false);
                return;
            }
            
            // Auto-save successful
            console.log(`[AUTO_SAVE] Field ${fieldName} saved successfully`);
            this._showAutoSaveStatus(true);
            
            // If it's the status field, update UI accordingly
            if (fieldName === 'status') {
                this.updateStatusBadge(fieldValue);
            }
            
        } catch (error) {
            console.error('[AUTO_SAVE] Error during auto-save:', error);
            this._showAutoSaveStatus(false);
        }
    }
    
    _showAutoSaveStatus(success) {
        // Create or get the auto-save status indicator
        let statusIndicator = document.getElementById('autoSaveStatus');
        if (!statusIndicator) {
            statusIndicator = document.createElement('div');
            statusIndicator.id = 'autoSaveStatus';
            statusIndicator.style.position = 'fixed';
            statusIndicator.style.bottom = '10px';
            statusIndicator.style.right = '10px';
            statusIndicator.style.padding = '5px 10px';
            statusIndicator.style.borderRadius = '3px';
            statusIndicator.style.fontSize = '0.8rem';
            statusIndicator.style.zIndex = '1000';
            statusIndicator.style.transition = 'opacity 0.5s';
            document.body.appendChild(statusIndicator);
        }
        
        // Set status message and style
        if (success) {
            statusIndicator.textContent = 'Changes saved';
            statusIndicator.style.backgroundColor = 'rgba(40, 167, 69, 0.8)';
            statusIndicator.style.color = 'white';
        } else {
            statusIndicator.textContent = 'Save failed!';
            statusIndicator.style.backgroundColor = 'rgba(220, 53, 69, 0.8)';
            statusIndicator.style.color = 'white';
        }
        
        // Show the indicator
        statusIndicator.style.opacity = '1';
        
        // Hide after 2 seconds
        setTimeout(() => {
            statusIndicator.style.opacity = '0';
        }, 2000);
    }
    
    updateStatusBadge(status) {
        const statusBadge = document.getElementById('statusBadge');
        if (!statusBadge) return;
        
        // Remove any existing status classes
        statusBadge.className = 'badge';
        
        // Add the new status class
        statusBadge.classList.add(`status-${status}`);
        
        // Update the text
        statusBadge.textContent = status;
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        console.log('Form submitted');
        
        try {
            // Collect form data
            const formData = new FormData(this.form);
            const data = Object.fromEntries(formData.entries());
            
            // Determine if creating or updating
            const isEditing = this.form.dataset.incidentId;
            
            // Set API endpoint and method
            const method = isEditing ? 'PUT' : 'POST';
            const url = isEditing 
                ? `/api/incidents/${this.form.dataset.incidentId}`
                : '/api/incidents';
            
            console.log(`[DB_OPERATION] Submitting incident form to ${url} with method ${method}`);
            
            // Submit form data as JSON
            const response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: JSON.stringify(data)
            });
            
            // Handle response
            if (!response.ok) {
                const errorData = await response.json();
                console.error(`[DB_OPERATION] Failed to save incident: ${errorData.message || 'Unknown error'}`);
                throw new Error(errorData.message || 'Failed to save incident');
            }
            
            const result = await response.json();
            console.log(`[DB_OPERATION] Incident ${isEditing ? 'updated' : 'created'} successfully`, result);
            
            // Handle success
            if (!isEditing) {
                // New incident created, redirect to edit page
                console.log(`[DB_OPERATION] Redirecting to edit page for new incident ID: ${result.incident.id}`);
                window.location.href = `/incident/${result.incident.id}`;
            } else {
                // Show success message
                this._showAlert('success', 'Changes saved successfully');
            }
            
        } catch (error) {
            console.error('[DB_OPERATION] Error saving incident:', error);
            this._showAlert('danger', 'Failed to save changes: ' + error.message);
        }
    }
    
    async autoSave() {
        if (!this.form.dataset.incidentId) return;
        
        try {
            const formData = new FormData(this.form);
            const data = Object.fromEntries(formData.entries());
            const incidentId = this.form.dataset.incidentId;
            
            console.log(`[DB_OPERATION] Auto-saving incident ID: ${incidentId}`);
            
            const response = await fetch(`/api/incidents/${incidentId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: JSON.stringify(data)
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                console.error(`[DB_OPERATION] Failed to auto-save incident: ${errorData.message || 'Unknown error'}`);
                throw new Error(errorData.message || 'Failed to auto-save incident');
            }
            
            // Success (show subtle indication)
            console.log(`[DB_OPERATION] Auto-saved incident ID: ${incidentId} successfully`);
            
        } catch (error) {
            console.error('[DB_OPERATION] Error auto-saving incident:', error);
            // Don't show alert for auto-save failures to avoid disrupting the user
        }
    }
    
    _showAlert(type, message) {
        // Use the global showAlert function from base.html
        window.showAlert(type, message);
    }
    
    async addLogEntry(message, type = 'info') {
        if (!this.form.dataset.incidentId) {
            console.error('[LOG] Cannot add log entry - no incident ID');
            return;
        }
        
        try {
            console.log(`[LOG] Adding log entry: ${message} (${type})`);
            
            const response = await fetch(`/api/incidents/${this.form.dataset.incidentId}/logs`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: JSON.stringify({
                    message: message,
                    type: type
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                console.error(`[LOG] Failed to add log entry: ${errorData.message || 'Unknown error'}`);
                throw new Error(errorData.message || 'Failed to add log entry');
            }
            
            const data = await response.json();
            
            // Display the new log entry
            this._addLogEntry(message, type);
            
            return data.log;
        } catch (error) {
            console.error('[LOG] Error adding log entry:', error);
            this._showAlert('error', `Error adding log entry: ${error.message}`);
            return null;
        }
    }
    
    _addLogEntry(message, type = 'info') {
        if (!this.liveLogContainer) return;
        
        // Create log entry object
        const entry = {
            timestamp: new Date().toLocaleTimeString(),
            message: message,
            type: type
        };
        
        // Create HTML element
        const div = document.createElement('div');
        div.className = `log-entry log-${type}`;
        div.innerHTML = `
            <span class="log-timestamp">${entry.timestamp}</span>
            <span class="log-message">${entry.message}</span>
        `;
        
        // Add to container
        this.liveLogContainer.appendChild(div);
        
        // Scroll to bottom
        this.liveLogContainer.scrollTop = this.liveLogContainer.scrollHeight;
    }
    
    initializeQuickNotePresets() {
        const presetsContainer = document.getElementById('quickNotePresets');
        if (!presetsContainer) return;
        
        // Common presets for incident management
        const presets = [
            { text: 'Unit dispatched', type: 'status' },
            { text: 'Unit arrived on scene', type: 'status' },
            { text: 'Patient assessment started', type: 'note' },
            { text: 'Treatment administered', type: 'note' },
            { text: 'Patient transported', type: 'status' },
            { text: 'Weather conditions affecting response', type: 'warning' },
            { text: 'Additional resources requested', type: 'warning' },
            { text: 'Medical control contacted', type: 'note' },
            { text: 'Multiple casualties reported', type: 'warning' },
            { text: 'Scene secured', type: 'status' }
        ];
        
        // Clear existing presets
        presetsContainer.innerHTML = '';
        
        // Add presets to container
        presets.forEach(preset => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `quick-note-preset quick-note-${preset.type}`;
            button.textContent = preset.text;
            button.addEventListener('click', () => {
                // Add the preset text to the note input
                const noteInput = document.getElementById('quickNoteText');
                if (noteInput) {
                    noteInput.value = preset.text;
                }
                
                // Set the note type
                const noteType = document.getElementById('quickNoteType');
                if (noteType) {
                    noteType.value = preset.type;
                }
            });
            
            presetsContainer.appendChild(button);
        });
    }
    
    showMedicalAssessment() {
        const modal = document.getElementById('medicalAssessmentModal');
        if (modal) {
            const bsModal = new bootstrap.Modal(modal);
            bsModal.show();
        }
    }

    async saveMedicalAssessment() {
        if (!this.state.incident?.id) {
            this._showAlert('error', 'No active incident');
            return;
        }

        const form = document.getElementById('medicalAssessmentForm');
        if (!form) return;

        const formData = new FormData(form);
        const assessment = {
            timestamp: new Date().toISOString(),
            chief_complaint: formData.get('chief_complaint'),
            assessment_type: formData.get('assessment_type'),
            vitals: {
                blood_pressure: formData.get('blood_pressure'),
                heart_rate: formData.get('heart_rate'),
                respiratory_rate: formData.get('respiratory_rate'),
                spo2: formData.get('spo2')
            },
            gcs: {
                eyes: parseInt(formData.get('gcs_eyes')),
                verbal: parseInt(formData.get('gcs_verbal')),
                motor: parseInt(formData.get('gcs_motor')),
                total: parseInt(formData.get('gcs_eyes')) + 
                       parseInt(formData.get('gcs_verbal')) + 
                       parseInt(formData.get('gcs_motor'))
            },
            notes: formData.get('notes')
        };

        try {
            console.log(`[DB_OPERATION] Saving medical assessment for incident ID: ${this.state.incident.id}`);
            const response = await fetch(`/incidents/${this.state.incident.id}/medical`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(assessment)
            });

            const data = await response.json();
            if (!response.ok) {
                console.error(`[DB_OPERATION] Failed to save medical assessment: ${data.message || 'Unknown error'}`);
                throw new Error(data.message || 'Failed to save medical assessment');
            }

            // Add assessment to the table
            const table = document.getElementById('medicalAssessmentsTable');
            if (table) {
                const tbody = table.querySelector('tbody');
                const row = tbody.insertRow(-1);
                row.innerHTML = `
                    <td>${new Date(assessment.timestamp).toLocaleString()}</td>
                    <td>${assessment.assessment_type}</td>
                    <td>
                        <strong>Chief Complaint:</strong> ${assessment.chief_complaint}<br>
                        <strong>Vitals:</strong> BP: ${assessment.vitals.blood_pressure}, 
                        HR: ${assessment.vitals.heart_rate}, 
                        RR: ${assessment.vitals.respiratory_rate}, 
                        SpO2: ${assessment.vitals.spo2}%<br>
                        <strong>GCS:</strong> ${assessment.gcs.total} (E${assessment.gcs.eyes}V${assessment.gcs.verbal}M${assessment.gcs.motor})
                    </td>
                    <td>
                        <button class="btn btn-sm btn-info" onclick="IncidentManager.viewMedicalAssessment('${assessment.timestamp}')">
                            <i class="fas fa-eye"></i>
                        </button>
                    </td>
                `;
            }

            // Show medical assessment card if hidden
            const card = document.getElementById('medicalAssessmentCard');
            if (card) {
                card.style.display = 'block';
            }

            // Close the modal
            const modal = document.getElementById('medicalAssessmentModal');
            if (modal) {
                const bsModal = bootstrap.Modal.getInstance(modal);
                if (bsModal) bsModal.hide();
            }

            // Reset form
            form.reset();

            this._addLogEntry(`Medical assessment added: ${assessment.assessment_type} - ${assessment.chief_complaint}`, 'note');
            this._showAlert('success', 'Medical assessment saved successfully');

        } catch (error) {
            console.error('[DB_OPERATION] Error saving medical assessment:', error);
            this._showAlert('error', error.message);
        }
    }

    viewMedicalAssessment() {
        // Implement viewing of existing medical assessment
        console.log('View medical assessment:');
    }

    addQuickNote() {
        const noteInput = document.getElementById('quickNoteInput');
        const noteType = document.getElementById('quickNoteType');
        
        if (!noteInput || !noteType) {
            console.error('Quick note elements not found');
            return;
        }
        
        const note = noteInput.value.trim();
        const type = noteType.value;
        
        if (!note) {
            this._showAlert('error', 'Please enter a note');
            return;
        }
        
        // Add to live log
        this._addLogEntry(note, type);
        
        // Clear input
        noteInput.value = '';
        
        // Save to incident if we have an ID
        if (this.state.incident?.id) {
            this.saveLogEntry(note, type).catch(error => {
                console.error('[DB_OPERATION] Error saving log entry:', error);
                this._showAlert('error', 'Failed to save log entry');
            });
        }
    }
    
    async saveLogEntry(message, type) {
        if (!this.state.incident || !this.state.incident.id) {
            console.warn('[DB_OPERATION] Cannot save log entry: No active incident');
            return;
        }
        
        try {
            console.log(`[DB_OPERATION] Saving log entry to incident ID: ${this.state.incident.id}, Type: ${type}`);
            const response = await fetch(`/incidents/${this.state.incident.id}/log`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: JSON.stringify({
                    message,
                    type
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                console.error(`[DB_OPERATION] Failed to save log entry: ${errorData.message || 'Unknown error'}`);
                throw new Error(errorData.message || 'Failed to save log entry');
            }
            
            const result = await response.json();
            console.log('[DB_OPERATION] Log entry saved successfully', result);
            
            // Add to live log
            this._addLogEntry(message, type);
            
            // Clear input if this was from quick note
            const quickNoteInput = document.getElementById('quickNoteInput');
            if (quickNoteInput) quickNoteInput.value = '';
            
        } catch (error) {
            console.error('[DB_OPERATION] Error saving log entry:', error);
            this._showAlert('error', 'Failed to save log entry');
        }
    }
    
    _setFormValue(name, value) {
        const element = document.querySelector(`[name="${name}"]`);
        if (element) {
            if (element.type === 'checkbox') {
                element.checked = value;
            } else {
                element.value = value || '';
            }
        }
    }

    showDispatchGrid() {
        const modal = new bootstrap.Modal(document.getElementById('dispatchGridModal'));
        const iframe = document.getElementById('dispatchGridFrame');
        iframe.src = `/admin/settings/dispatch-grid/v2?t=${Date.now()}`; // Add timestamp to prevent caching
        modal.show();
    }

    generatePDF() {
        if (!this.state.incident || !this.state.incident.id) {
            this._showAlert('error', 'No incident data available');
            return;
        }
        
        // Open PDF in new tab
        window.open(`/api/incidents/${this.state.incident.id}/pdf`, '_blank');
    }

    async showAMPDSDialog() {
        try {
            // Show the modal
            this.state.ampdsModal.show();
            
            // Initialize protocol data
            await this.loadProtocolData();
            
            // Initialize event listeners
            this._initializeMedicalProtocolListeners();
            
        } catch (error) {
            console.error('Error showing medical protocol:', error);
            this._showAlert('error', 'Failed to show medical protocol');
        }
    }
    
    async loadProtocolData() {
        try {
            // Load protocol data from the server
            const response = await fetch('/api/medical/protocols');
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || 'Failed to load protocol data');
            }
            
            // Store protocol data
            this.state.protocolData = data;
            
            // Populate category dropdown
            this._populateCategories();
                
        } catch (error) {
            console.error('Error loading protocol data:', error);
            this._showAlert('error', 'Failed to load protocol data');
        }
    }
    
    _initializeMedicalProtocolListeners() {
        // Handle card number input
        document.getElementById('cardNumber').addEventListener('input', (e) => {
            const cardNumber = e.target.value;
            const protocol = this.state.protocolData.find(p => p.cardNumber === cardNumber);
            
            if (protocol) {
                document.getElementById('category').value = protocol.category;
                this._populateSubCategories(protocol.category);
                document.getElementById('subCategory').value = protocol.subCategory;
                this._updateProtocolInfo(protocol);
            }
        });

        // Handle category change
        document.getElementById('category').addEventListener('change', (e) => {
            const selectedCategory = e.target.value;
            if (selectedCategory) {
                this._populateSubCategories(selectedCategory);
            }
        });

        // Handle sub-category change
        document.getElementById('subCategory').addEventListener('change', (e) => {
            const category = document.getElementById('category').value;
            const subCategory = e.target.value;
            
            if (category && subCategory) {
                const protocol = this.state.protocolData.find(
                    p => p.category === category && p.subCategory === subCategory
                );
                if (protocol) {
                    this._updateProtocolInfo(protocol);
                }
            }
        });

        // Quick search functionality
        document.getElementById('quickSearch').addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            if (query.length < 2) return;

            const matches = this.state.protocolData.filter(p => 
                p.cardNumber.toLowerCase().includes(query) ||
                p.category.toLowerCase().includes(query) ||
                p.subCategory.toLowerCase().includes(query)
            );

            if (matches.length > 0) {
                const protocol = matches[0];
                document.getElementById('cardNumber').value = protocol.cardNumber;
                document.getElementById('category').value = protocol.category;
                this._populateSubCategories(protocol.category);
                document.getElementById('subCategory').value = protocol.subCategory;
                this._updateProtocolInfo(protocol);
            }
        });
    }
    
    _populateCategories() {
        const categorySelect = document.getElementById('category');
        const categories = [...new Set(this.state.protocolData.map(p => p.category))];
        
        categorySelect.innerHTML = '<option value="">Select Category</option>';
        categories.forEach(cat => {
            categorySelect.innerHTML += `<option value="${cat}">${cat}</option>`;
        });
    }
    
    _populateSubCategories(category) {
        const subCategorySelect = document.getElementById('subCategory');
        const subCategories = this.state.protocolData
            .filter(p => p.category === category)
            .map(p => p.subCategory);
        
        subCategorySelect.innerHTML = '<option value="">Select Sub-Category</option>';
        subCategories.forEach(sub => {
            subCategorySelect.innerHTML += `<option value="${sub}">${sub}</option>`;
        });
        subCategorySelect.disabled = false;
    }
    
    _updateProtocolInfo(protocol) {
        const protocolInfo = document.getElementById('protocolInfo');
        const priorityLevel = document.getElementById('priorityLevel');
        const dispatchAdvice = document.getElementById('dispatchAdvice');
        const specialInstructions = document.getElementById('specialInstructions');
        const keyQuestions = document.getElementById('keyQuestions');
        
        protocolInfo.style.display = 'block';
        priorityLevel.textContent = protocol.priority;
        priorityLevel.className = `badge bg-${this._getPriorityClass(protocol.priority)}`;
        
        dispatchAdvice.textContent = protocol.dispatchAdvice || 'No dispatch advice available.';
        specialInstructions.textContent = protocol.specialInstructions || 'No special instructions available.';
        
        keyQuestions.innerHTML = protocol.keyQuestions ?
            protocol.keyQuestions.map(q => `<li>${q}</li>`).join('') :
            '<li>No key questions available.</li>';
    }
    
    async applyProtocol() {
        try {
            const cardNumber = document.getElementById('cardNumber').value;
            const category = document.getElementById('category').value;
            const subCategory = document.getElementById('subCategory').value;
            
            if (!cardNumber || !category || !subCategory) {
                this._showAlert('warning', 'Please select all protocol fields');
                return;
            }
            
            const protocol = this.state.protocolData.find(
                p => p.cardNumber === cardNumber &&
                     p.category === category &&
                     p.subCategory === subCategory
            );
            
            if (!protocol) {
                throw new Error('Protocol not found');
            }
            
            // Update incident form with protocol data
            this._setFormValue('medical_data.chief_complaint', protocol.category);
            this._setFormValue('medical_data.priority', protocol.priority);
            
            // Add to incident log
            this._addLogEntry(`Protocol ${cardNumber} applied: ${category} - ${subCategory}`, 'status');
            
            // Close the modal
            this.state.medicalProtocolModal.hide();
            
            // Show success message
            this._showAlert('success', 'Protocol applied successfully');
            
        } catch (error) {
            console.error('Error applying protocol:', error);
            this._showAlert('error', 'Failed to apply protocol');
        }
    }

    async toggleFavorite() {
        const cardNumber = document.getElementById('cardNumber').value;
        if (!cardNumber) {
            this._showAlert('warning', 'Please select a protocol first');
            return;
        }

        try {
            console.log(`[DB_OPERATION] Toggling favorite for protocol ${cardNumber}`);
            const response = await fetch(`/api/medical/protocols/${cardNumber}/favorite`, {
                method: 'POST'
            });
            const data = await response.json();
            
            if (!response.ok) {
                console.error(`[DB_OPERATION] Failed to toggle favorite: ${data.message || 'Unknown error'}`);
                throw new Error(data.message || 'Failed to toggle favorite');
            }
            
            this._showAlert('success', data.favorite ? 'Added to favorites' : 'Removed from favorites');
            
        } catch (error) {
            console.error('Error toggling favorite:', error);
            this._showAlert('error', 'Failed to toggle favorite');
        }
    }

    async showRecent() {
        try {
            console.log('[DB_OPERATION] Loading recent protocols');
            const response = await fetch('/api/medical/protocols/recent');
            const data = await response.json();
            
            if (!response.ok) {
                console.error(`[DB_OPERATION] Failed to load recent protocols: ${data.message || 'Unknown error'}`);
                throw new Error(data.message || 'Failed to load recent protocols');
            }
            
            // TODO: Show recent protocols in a dropdown or list
            
        } catch (error) {
            console.error('Error loading recent protocols:', error);
            this._showAlert('error', 'Failed to load recent protocols');
        }
    }
    
    async showFavorites() {
        try {
            console.log('[DB_OPERATION] Loading favorite protocols');
            const response = await fetch('/api/medical/protocols/favorites');
            const data = await response.json();
            
            if (!response.ok) {
                console.error(`[DB_OPERATION] Failed to load favorite protocols: ${data.message || 'Unknown error'}`);
                throw new Error(data.message || 'Failed to load favorite protocols');
            }
            
            // TODO: Show favorite protocols in a dropdown or list
            
        } catch (error) {
            console.error('Error loading favorite protocols:', error);
            this._showAlert('error', 'Failed to load favorite protocols');
        }
    }

    async viewPreArrivalPDF() {
        const cardNumber = document.getElementById('cardNumber').value;
        if (!cardNumber) {
            this._showAlert('warning', 'Please select a protocol first');
            return;
        }

        // Open PDF in new tab
        window.open(`/api/medical/protocols/${cardNumber}/pdf`, '_blank');
    }

    async showMedicalProtocolDialog() {
        try {
            // Show the medical protocol modal
            this.state.medicalProtocolModal.show();
            
            // Initialize protocol data
            await this.loadProtocolData();
            
            // Initialize event listeners
            this._initializeMedicalProtocolListeners();
            
        } catch (error) {
            console.error('Error showing medical protocol:', error);
            this._showAlert('error', 'Failed to show medical protocol');
        }
    }

    _getPriorityClass(priority) {
        switch (priority.toUpperCase()) {
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

    async loadMedicalProtocols() {
        try {
            console.log('[DB_OPERATION] Loading medical protocols');
            const response = await fetch('/api/medical/protocols/categories');
            if (!response.ok) throw new Error('Failed to load protocols');
            
            const categories = await response.json();
            
            // Populate category dropdown
            const categorySelect = document.getElementById('medicalCategory');
            categorySelect.innerHTML = '<option value="">Select Category</option>';
            categories.forEach(cat => {
                categorySelect.innerHTML += `<option value="${cat.category}">${cat.category}</option>`;
            });
            
            // Store categories data for later use
            window.medicalCategories = categories;
            
            return categories;
        } catch (error) {
            console.error('Error loading medical protocols:', error);
            this._showAlert('error', 'Failed to load medical protocols');
        }
    }
    
    async handleCategoryChange() {
        const categorySelect = document.getElementById('medicalCategory');
        const subcategorySelect = document.getElementById('medicalSubcategory');
        const selectedCategory = categorySelect.value;
        
        // Clear subcategory dropdown
        subcategorySelect.innerHTML = '<option value="">Select Subcategory</option>';
        
        if (!selectedCategory) return;
        
        // Find category data
        const categoryData = window.medicalCategories.find(c => c.category === selectedCategory);
        if (!categoryData) return;
        
        // Populate subcategories
        categoryData.subcategories.forEach(sub => {
            subcategorySelect.innerHTML += `<option value="${sub.card_number}">${sub.name}</option>`;
        });
    }
    
    async handleSubcategoryChange() {
        const subcategorySelect = document.getElementById('medicalSubcategory');
        const cardNumber = subcategorySelect.value;
        
        if (!cardNumber) {
            this.clearProtocolDetails();
            return;
        }
        
        await this.loadProtocolByCard(cardNumber);
    }
    
    async handleCardNumberSearch() {
        const cardInput = document.getElementById('medicalCardNumber');
        const cardNumber = cardInput.value.trim();
        
        if (!cardNumber) {
            this.clearProtocolDetails();
            return;
        }
        
        await this.loadProtocolByCard(cardNumber);
    }
    
    async loadProtocolByCard(cardNumber) {
        try {
            console.log(`[DB_OPERATION] Loading protocol by card number ${cardNumber}`);
            const response = await fetch(`/api/medical/protocols/search/${cardNumber}`);
            if (!response.ok) throw new Error('Protocol not found');
            
            const protocol = await response.json();
            
            // Update form fields
            document.getElementById('medicalCategory').value = protocol.category;
            await this.handleCategoryChange();  // Populate subcategories
            document.getElementById('medicalSubcategory').value = cardNumber;
            
            // Update protocol details
            document.getElementById('protocolPriority').textContent = protocol.priority;
            document.getElementById('protocolDispatchAdvice').textContent = protocol.dispatch_advice;
            
            // Store PDF path for later use
            if (protocol.pre_arrival_pdf) {
                document.getElementById('preArrivalPdfLink').dataset.pdfPath = protocol.pre_arrival_pdf;
            }
            
            // Show protocol details section
            document.getElementById('protocolDetails').style.display = 'block';
            
        } catch (error) {
            console.error('Error loading protocol:', error);
            this._showAlert('error', 'Protocol not found');
            this.clearProtocolDetails();
        }
    }
    
    clearProtocolDetails() {
        document.getElementById('protocolPriority').textContent = '';
        document.getElementById('protocolDispatchAdvice').textContent = '';
        document.getElementById('preArrivalPdfLink').dataset.pdfPath = '';
        document.getElementById('pdfViewer').style.display = 'none';
        document.getElementById('protocolDetails').style.display = 'none';
    }

    async viewPreArrivalPDF() {
        const pdfLink = document.getElementById('preArrivalPdfLink');
        const pdfPath = pdfLink.dataset.pdfPath;
        
        if (!pdfPath) {
            this._showAlert('error', 'No PDF available for this protocol');
            return;
        }
        
        const pdfViewer = document.getElementById('pdfViewer');
        const pdfFrame = document.getElementById('pdfFrame');
        
        try {
            // Load PDF in iframe
            pdfFrame.src = `/api/medical/protocols/${pdfPath}/pdf`;
            pdfViewer.style.display = 'block';
            
            // Scroll PDF viewer into view
            pdfViewer.scrollIntoView({ behavior: 'smooth' });
        } catch (error) {
            console.error('Error loading PDF:', error);
            this._showAlert('error', 'Failed to load PDF');
        }
    }
    
    togglePDFFullscreen() {
        const pdfViewer = document.getElementById('pdfViewer');
        
        if (!document.fullscreenElement) {
            pdfViewer.requestFullscreen().catch(err => {
                console.error('Error attempting to enable fullscreen:', error);
            });
        } else {
            document.exitFullscreen();
        }
    }
    
    closePDFViewer() {
        const pdfViewer = document.getElementById('pdfViewer');
        const pdfFrame = document.getElementById('pdfFrame');
        
        pdfViewer.style.display = 'none';
        pdfFrame.src = '';  // Clear the iframe
    }
    
    async searchLocation(e) {
        const searchTerm = e.target.value.trim();
        
        if (searchTerm.length < 3) {
            this._hideLocationSuggestions();
            return;
        }
        
        try {
            console.log(`[LOCATION] Searching for location: ${searchTerm}`);
            const response = await fetch(`/api/locations/search?term=${encodeURIComponent(searchTerm)}`);
            
            if (!response.ok) {
                throw new Error('Failed to search locations');
            }
            
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to search locations');
            }
            
            // Store the suggestions for later use
            this.state.locationSuggestions = data.locations || [];
            
            // Show suggestions
            this._showLocationSuggestions();
            
        } catch (error) {
            console.error('[LOCATION] Error searching locations:', error);
            this._showAlert('error', `Error searching locations: ${error.message}`);
        }
    }
    
    _showLocationSuggestions() {
        const container = document.getElementById('locationSuggestions');
        if (!container) return;
        
        // Clear existing suggestions
        container.innerHTML = '';
        
        // No suggestions found
        if (this.state.locationSuggestions.length === 0) {
            container.innerHTML = '<div class="dropdown-item text-muted">No locations found</div>';
            container.classList.add('show');
            return;
        }
        
        // Add each suggestion
        this.state.locationSuggestions.forEach(location => {
            const item = document.createElement('a');
            item.className = 'dropdown-item';
            item.href = '#';
            item.textContent = location.name;
            item.dataset.id = location.id;
            item.dataset.lat = location.latitude;
            item.dataset.lng = location.longitude;
            
            item.addEventListener('click', (e) => {
                e.preventDefault();
                this._selectLocation(location);
            });
            
            container.appendChild(item);
        });
        
        // Show the dropdown
        container.classList.add('show');
    }
    
    _hideLocationSuggestions() {
        const container = document.getElementById('locationSuggestions');
        if (container) {
            container.classList.remove('show');
        }
    }
    
    _selectLocation(location) {
        // Set form values
        this.locationInput.value = location.name;
        this.locationIdInput.value = location.id;
        this.latitudeInput.value = location.latitude;
        this.longitudeInput.value = location.longitude;
        
        // Update map if it exists
        if (this.state.map) {
            this.state.map.setView([location.latitude, location.longitude], 15);
            if (this.state.marker) {
                this.state.marker.setLatLng([location.latitude, location.longitude]);
            } else {
                this.state.marker = L.marker([location.latitude, location.longitude]).addTo(this.state.map);
            }
        }
        
        // Hide suggestions
        this._hideLocationSuggestions();
        
        // Log selection
        this._addLogEntry(`Location set to: ${location.name}`, 'info');
        
        // Trigger auto-save
        this.autoSave({ target: this.locationInput });
    }
    
    async handleStatusChange(e) {
        const statusValue = e.target.value;
        console.log(`[INCIDENT] Status changed to: ${statusValue}`);
        
        try {
            if (!this.form.dataset.incidentId) {
                console.error('[INCIDENT] Cannot update status - no incident ID');
                return;
            }
            
            // Update the status badge immediately for better UX
            this.updateStatusBadge(statusValue);
            
            // Log the status change
            this._addLogEntry(`Status changed to ${statusValue}`, 'status');
            
            // Update through API
            const response = await fetch(`/api/incidents/${this.form.dataset.incidentId}/status`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: JSON.stringify({ status: statusValue })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                console.error(`[INCIDENT] Failed to update status: ${errorData.message || 'Unknown error'}`);
                this._showAlert('error', `Failed to update status: ${errorData.message || 'Unknown error'}`);
                return;
            }
            
            console.log('[INCIDENT] Status updated successfully');
            this._showAlert('success', 'Status updated successfully');
        } catch (error) {
            console.error('[INCIDENT] Error updating status:', error);
            this._showAlert('error', `Error updating status: ${error.message}`);
        }
    }
    
    async refreshAssignedUnits() {
        if (!this.form.dataset.incidentId) {
            console.log('[UNITS] No incident ID, cannot refresh units');
            return;
        }
        
        try {
            console.log(`[UNITS] Refreshing assigned units for incident ${this.form.dataset.incidentId}`);
            
            const response = await fetch(`/api/incidents/${this.form.dataset.incidentId}/units`);
            if (!response.ok) {
                throw new Error('Failed to fetch assigned units');
            }
            
            const data = await response.json();
            this.updateAssignedUnitsList(data.units || []);
            
        } catch (error) {
            console.error('[UNITS] Error refreshing assigned units:', error);
            this._showAlert('error', 'Error loading assigned units');
        }
    }
    
    updateAssignedUnitsList(units) {
        const unitsList = document.getElementById('assignedUnitsList');
        if (!unitsList) return;
        
        // Clear existing list
        unitsList.innerHTML = '';
        
        // No units assigned
        if (units.length === 0) {
            unitsList.innerHTML = '<li class="list-group-item text-muted">No units assigned</li>';
            return;
        }
        
        // Add each unit to the list
        units.forEach(unit => {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center';
            
            const statusBadge = document.createElement('span');
            statusBadge.className = `badge status-${unit.status}`;
            statusBadge.textContent = unit.status;
            
            const unitInfo = document.createElement('div');
            unitInfo.innerHTML = `
                <strong>${unit.name}</strong> - ${unit.type}<br>
                <small>Assigned: ${new Date(unit.assigned_time).toLocaleString()}</small>
            `;
            
            const buttonGroup = document.createElement('div');
            buttonGroup.className = 'btn-group btn-group-sm';
            
            // Status update button
            const statusBtn = document.createElement('button');
            statusBtn.type = 'button';
            statusBtn.className = 'btn btn-outline-primary';
            statusBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
            statusBtn.title = 'Update Status';
            statusBtn.addEventListener('click', () => this.showUnitStatusModal(unit.id));
            
            // Clear unit button
            const clearBtn = document.createElement('button');
            clearBtn.type = 'button';
            clearBtn.className = 'btn btn-outline-danger';
            clearBtn.innerHTML = '<i class="fas fa-times"></i>';
            clearBtn.title = 'Clear Unit';
            clearBtn.addEventListener('click', () => this.clearUnit(unit.id));
            
            buttonGroup.appendChild(statusBtn);
            buttonGroup.appendChild(clearBtn);
            
            li.appendChild(unitInfo);
            li.appendChild(statusBadge);
            li.appendChild(buttonGroup);
            
            unitsList.appendChild(li);
        });
    }
    
    showUnitStatusModal(unitId) {
        const modal = document.getElementById('unitStatusModal');
        if (!modal) return;
        
        // Set unit ID in the modal
        modal.dataset.unitId = unitId;
        
        // Show the modal
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
    }
    
    async updateUnitStatus(unitId, status) {
        if (!this.form.dataset.incidentId || !unitId || !status) {
            console.error('[UNITS] Missing required parameters for updating unit status');
            return;
        }
        
        try {
            console.log(`[UNITS] Updating unit ${unitId} status to ${status}`);
            
            const response = await fetch(`/api/units/${unitId}/status`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: JSON.stringify({
                    status: status,
                    incident_id: this.form.dataset.incidentId
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || 'Failed to update unit status');
            }
            
            // Success - refresh the units list
            this.refreshAssignedUnits();
            
            // Add log entry
            this.addLogEntry(`Unit ${unitId} status changed to ${status}`, 'status');
            
            // Close the modal
            const modal = document.getElementById('unitStatusModal');
            if (modal) {
                const modalInstance = bootstrap.Modal.getInstance(modal);
                if (modalInstance) modalInstance.hide();
            }
            
            this._showAlert('success', 'Unit status updated successfully');
            
        } catch (error) {
            console.error('[UNITS] Error updating unit status:', error);
            this._showAlert('error', `Error updating unit status: ${error.message}`);
        }
    }
    
    async clearUnit(unitId) {
        if (!this.form.dataset.incidentId || !unitId) {
            console.error('[UNITS] Missing required parameters for clearing unit');
            return;
        }
        
        if (!confirm('Are you sure you want to clear this unit from the incident?')) {
            return;
        }
        
        try {
            console.log(`[UNITS] Clearing unit ${unitId} from incident ${this.form.dataset.incidentId}`);
            
            const response = await fetch(`/api/incidents/${this.form.dataset.incidentId}/units/${unitId}`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || 'Failed to clear unit');
            }
            
            // Success - refresh the units list
            this.refreshAssignedUnits();
            
            // Add log entry
            this.addLogEntry(`Unit ${unitId} cleared from incident`, 'status');
            
            this._showAlert('success', 'Unit cleared successfully');
            
        } catch (error) {
            console.error('[UNITS] Error clearing unit:', error);
            this._showAlert('error', `Error clearing unit: ${error.message}`);
        }
    }
    
    async saveIncident(exitAfterSave = false) {
        try {
            // Collect form data
            const formData = new FormData(this.form);
            const data = Object.fromEntries(formData.entries());
            
            // Determine if creating or updating
            const isEditing = this.form.dataset.incidentId;
            const incidentId = isEditing ? this.form.dataset.incidentId : null;
            
            // Set API endpoint and method
            const method = isEditing ? 'PUT' : 'POST';
            const url = isEditing 
                ? `/api/incidents/${incidentId}`
                : '/api/incidents';
            
            console.log(`[DB_OPERATION] Saving incident to ${url} with method ${method}`);
            
            // Submit form data as JSON
            const response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: JSON.stringify(data)
            });
            
            // Handle response
            if (!response.ok) {
                const errorData = await response.json();
                console.error(`[DB_OPERATION] Failed to save incident: ${errorData.message || 'Unknown error'}`);
                throw new Error(errorData.message || 'Failed to save incident');
            }
            
            const result = await response.json();
            console.log(`[DB_OPERATION] Incident ${isEditing ? 'updated' : 'created'} successfully`, result);
            
            // Add to log
            this._addLogEntry(`Incident ${isEditing ? 'updated' : 'created'} successfully`, 'success');
            
            // Show success message
            this._showAlert('success', 'Incident saved successfully');
            
            // Redirect if new incident
            if (!isEditing && result.incident && result.incident.id) {
                console.log(`[DB_OPERATION] Redirecting to edit page for new incident ID: ${result.incident.id}`);
                window.location.href = `/incident/${result.incident.id}`;
                return;
            }
            
            // Redirect to list if requested
            if (exitAfterSave) {
                console.log('[DB_OPERATION] Exiting to incident list as requested');
                window.location.href = '/incidents';
            }
            
        } catch (error) {
            console.error('[DB_OPERATION] Error saving incident:', error);
            this._showAlert('danger', 'Failed to save incident: ' + error.message);
        }
    }
    
    async assignUnit(unitId) {
        try {
            console.log(`[DB_OPERATION] Assigning unit ID: ${unitId} to incident ID: ${this.state.incident.id}`);
            const response = await fetch(`/api/incidents/${this.state.incident.id}/assign-unit`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    unit_id: unitId
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                console.error(`[DB_OPERATION] Failed to assign unit: ${errorData.message || 'Unknown error'}`);
                throw new Error(errorData.message || 'Failed to assign unit');
            }
            
            const result = await response.json();
            console.log(`[DB_OPERATION] Unit ID: ${unitId} assigned successfully to incident ID: ${this.state.incident.id}`, result);
            
            // Refresh assigned units
            await this.refreshAssignedUnits();
            
            // Add log entry
            this._addLogEntry(`Unit ${unitId} assigned to incident`, 'status');
            
            // Show success message
            this._showAlert('success', 'Unit assigned successfully');
            
        } catch (error) {
            console.error('[DB_OPERATION] Error assigning unit:', error);
            this._showAlert('error', 'Failed to assign unit');
        }
    }
    
    async unassignUnit(unitId) {
        try {
            console.log(`[DB_OPERATION] Unassigning unit ID: ${unitId} from incident ID: ${this.state.incident.id}`);
            const response = await fetch(`/api/incidents/${this.state.incident.id}/unassign-unit`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    unit_id: unitId
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                console.error(`[DB_OPERATION] Failed to unassign unit: ${errorData.message || 'Unknown error'}`);
                throw new Error(errorData.message || 'Failed to unassign unit');
            }
            
            const result = await response.json();
            console.log(`[DB_OPERATION] Unit ID: ${unitId} unassigned successfully from incident ID: ${this.state.incident.id}`, result);
            
            // Refresh assigned units
            await this.refreshAssignedUnits();
            
            // Add log entry
            this._addLogEntry(`Unit ${unitId} unassigned from incident`, 'status');
            
            // Show success message
            this._showAlert('success', 'Unit unassigned successfully');
            
        } catch (error) {
            console.error('[DB_OPERATION] Error unassigning unit:', error);
            this._showAlert('error', 'Failed to unassign unit');
        }
    }
    
    populateForm(incident) {
        const form = document.getElementById('incidentForm');
        if (!form || !incident) return;
        
        // Map API fields to form fields
        const fieldMap = {
            'location': 'location',
            'problem': 'problem_description',
            'type': 'type',
            'priority': 'priority',
            'caller': 'caller',
            'callback_number': 'callback_number',
            'pickup_point': 'pickup_point'
        };
        
        // Populate each field
        Object.entries(fieldMap).forEach(([apiField, formField]) => {
            const field = form.elements[formField];
            if (field && incident[apiField] !== undefined) {
                field.value = incident[apiField];
                field.setAttribute('data-old-value', incident[apiField]);
            }
        });
        
        // Update status badge
        const statusBadge = document.getElementById('statusBadge');
        if (statusBadge) {
            statusBadge.textContent = incident.status;
            statusBadge.className = `badge status-${incident.status}`;
        }
        
        // Show medical assessment card if incident has medical assessments
        const medicalCard = document.getElementById('medicalAssessmentCard');
        if (medicalCard && incident.medical_assessments?.length > 0) {
            medicalCard.style.display = 'block';
            
            // Populate medical assessments table
            const table = document.getElementById('medicalAssessmentsTable');
            if (table) {
                const tbody = table.querySelector('tbody');
                tbody.innerHTML = incident.medical_assessments.map(assessment => `
                    <td>${new Date(assessment.timestamp).toLocaleString()}</td>
                    <td>${assessment.assessment_type}</td>
                    <td>
                        <strong>Chief Complaint:</strong> ${assessment.chief_complaint}<br>
                        <strong>Vitals:</strong> BP: ${assessment.vitals.blood_pressure}, 
                        HR: ${assessment.vitals.heart_rate}, 
                        RR: ${assessment.vitals.respiratory_rate}, 
                        SpO2: ${assessment.vitals.spo2}%<br>
                        <strong>GCS:</strong> ${assessment.gcs.total} (E${assessment.gcs.eyes}V${assessment.gcs.verbal}M${assessment.gcs.motor})
                    </td>
                    <td>
                        <button class="btn btn-sm btn-info" onclick="IncidentManager.viewMedicalAssessment('${assessment.timestamp}')">
                            <i class="fas fa-eye"></i>
                        </button>
                    </td>
                `).join('');
            }
        }
        
        // Show and populate medical dialog if it's a medical emergency
        const medicalDialog = document.getElementById('medicalDialogSection');
        if (medicalDialog && incident.type === 'MEDICAL_EMERGENCY' && incident.medical_data) {
            medicalDialog.style.display = 'block';
            
            // Populate medical data fields
            const medicalData = incident.medical_data;
            this._setFormValue('medical_data.chief_complaint', medicalData.chief_complaint);
            this._setFormValue('medical_data.age', medicalData.age);
            this._setFormValue('medical_data.gender', medicalData.gender);
            this._setFormValue('medical_data.vitals.blood_pressure', medicalData.vitals?.blood_pressure);
            this._setFormValue('medical_data.vitals.heart_rate', medicalData.vitals?.heart_rate);
            this._setFormValue('medical_data.vitals.respiratory_rate', medicalData.vitals?.respiratory_rate);
            this._setFormValue('medical_data.vitals.spo2', medicalData.vitals?.spo2);
            this._setFormValue('medical_data.consciousness', medicalData.consciousness);
            this._setFormValue('medical_data.history', medicalData.history);
            this._setFormValue('medical_data.medications', medicalData.medications);
            this._setFormValue('medical_data.allergies', medicalData.allergies);
        }
        
        // Populate pickup point if set
        const pickupPointSelect = document.getElementById('pickupPoint');
        if (pickupPointSelect && incident.pickup_point) {
            pickupPointSelect.value = incident.pickup_point;
            
            // Show pickup point details
            const selectedOption = pickupPointSelect.options[pickupPointSelect.selectedIndex];
            const detailsDiv = document.querySelector('.pickup-point-details');
            const addressSpan = document.querySelector('.pickup-point-address');
            
            if (selectedOption && detailsDiv && addressSpan) {
                addressSpan.textContent = selectedOption.getAttribute('data-address');
                detailsDiv.style.display = 'block';
            }
        }
    }
}

// Initialize incident manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new IncidentManager('incidentForm');
});

IncidentManager.prototype.handleQuickNoteSubmit = function(e) {
    e.preventDefault();
    
    const form = e.target;
    const message = form.elements.quickNoteText.value.trim();
    const type = form.elements.quickNoteType.value;
    
    if (!message) {
        this._showAlert('warning', 'Please enter a message for the note');
        return;
    }
    
    // Add log entry through the API
    this.addLogEntry(message, type)
        .then(() => {
            // Clear the form
            form.reset();
            
            // Focus back on the text input
            form.elements.quickNoteText.focus();
        })
        .catch(error => {
            console.error('Error adding quick note:', error);
        });
}

IncidentManager.prototype.handleUnitStatusSubmit = function(e) {
    e.preventDefault();
    
    const form = e.target;
    const status = form.elements.unitStatus.value;
    const modal = document.getElementById('unitStatusModal');
    
    if (!modal || !modal.dataset.unitId) {
        this._showAlert('error', 'No unit selected');
        return;
    }
    
    if (!status) {
        this._showAlert('warning', 'Please select a status');
        return;
    }
    
    // Update unit status
    this.updateUnitStatus(modal.dataset.unitId, status);
}

IncidentManager.prototype.handleDispatchUnit = function() {
    // Get the unit select element
    const unitSelect = document.getElementById('unitSelect');
    if (!unitSelect || !unitSelect.value) {
        this._showAlert('warning', 'Please select a unit to dispatch');
        return;
    }
    
    // Assign the unit to this incident
    this.assignUnit(unitSelect.value);
}

IncidentManager.prototype.handleCloseIncident = function() {
    if (!confirm('Are you sure you want to close this incident? This action cannot be undone.')) {
        return;
    }
    
    // Change status to closed
    if (this.statusSelect) {
        this.statusSelect.value = 'CLOSED';
        this.handleStatusChange({ target: this.statusSelect });
    }
}

IncidentManager.prototype.handlePdfReport = function() {
    if (!this.form.dataset.incidentId) {
        this._showAlert('error', 'Cannot generate report - no incident ID');
        return;
    }
    
    // Generate and download PDF report
    window.open(`/api/incidents/${this.form.dataset.incidentId}/report`, '_blank');
}