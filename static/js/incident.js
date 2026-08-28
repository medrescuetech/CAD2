// Incident Management Module
const IncidentManager = {
    // Configuration
    config: {
        autoSaveInterval: 30000, // 30 seconds
        maxRetries: 3,
        retryDelay: 5000,
        keyBindings: {
            'Alt+C': '#callerName',
            'Alt+B': '#callbackNumber',
            'Alt+L': '#location',
            'Alt+P': '#pickupPoint',
            'Alt+D': '#description',
            'Alt+N': '#quickNote',
            'Ctrl+S': function() { this.saveIncident(false); },
            'Ctrl+Enter': function() { this.saveIncident(true); },
            'Ctrl+P': function() { this.generatePDF(); },
            'Escape': function() { this.closeModal(); }
        }
    },

    // State management
    state: {
        currentIncident: null,
        isDirty: false,
        lastSaved: null,
        autoSaveTimer: null,
        isSubmitting: false,
        initialized: false,
        significantChanges: new Set([
            'status',
            'priority',
            'problem',
            'location',
            'assigned_units'
        ])
    },

    // Initialize incident management
    init() {
        if (this.state.initialized) return this;
        
        try {
            this._initFormHandlers();
            this._initKeyBindings();
            this._setupAutoSave();
            
            // Generate case number for new incidents
            if (!document.getElementById('caseNumber').value) {
                this._generateCaseNumber();
            }
            
            // Set current timestamp for new incidents
            if (!document.getElementById('createdAt').value) {
                const now = new Date();
                document.getElementById('createdAt').value = now.toLocaleString();
            }
            
            this.state.initialized = true;
        } catch (error) {
            console.error('Error initializing IncidentManager:', error);
            this._showAlert('Failed to initialize incident manager', 'danger');
        }
        return this;
    },

    // Generate a new case number
    async _generateCaseNumber() {
        try {
            const response = await fetch('/api/incidents/next-case-number');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const data = await response.json();
            if (data.success) {
                document.getElementById('caseNumber').value = data.case_number;
            } else {
                throw new Error(data.message || 'Failed to generate case number');
            }
        } catch (error) {
            console.error('Error generating case number:', error);
            this._showAlert('Failed to generate case number', 'danger');
        }
    },

    // Save the incident
    async saveIncident(andExit = false) {
        if (this.state.isSubmitting) return;
        
        // Show loading state
        const submitButton = document.querySelector('#saveButton');
        const originalText = submitButton.innerHTML;
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving...';
        
        this.state.isSubmitting = true;
        this._clearFormErrors();

        try {
            const form = document.getElementById('incidentForm');
            const validationResult = this._validateForm(form);
            
            if (!validationResult.isValid) {
                this._showValidationErrors(validationResult.errors);
                return;
            }

            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());
            
            // Add case number and timestamp for new incidents
            if (!data.case_number) {
                data.case_number = document.getElementById('caseNumber').value;
            }
            if (!data.created_at) {
                data.created_at = new Date().toISOString();
            }

            const url = this.state.currentIncident ? 
                `/api/incidents/${this.state.currentIncident.id}` : 
                '/api/incidents';
            
            const response = await fetch(url, {
                method: this.state.currentIncident ? 'PUT' : 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || 'Failed to save incident');
            }

            const result = await response.json();
            if (result.success) {
            this.state.currentIncident = result.incident;
            this.state.isDirty = false;
            this.state.lastSaved = new Date();
            
            this._addLogEntry(
                this.state.currentIncident ? 'Incident updated' : 'Incident created',
                'success'
            );
            
            if (andExit) {
                window.close();
            } else {
                this._showAlert('Incident saved successfully', 'success');
            }

            // Update dashboard/monitor views
            this._notifyUpdate();
            } else {
                throw new Error(result.message || 'Failed to save incident');
            }
        } catch (error) {
            console.error('Error saving incident:', error);
            this._showAlert('Failed to save incident: ' + error.message, 'danger');
        } finally {
            this.state.isSubmitting = false;
            submitButton.disabled = false;
            submitButton.innerHTML = originalText;
        }
    },

    // Validate form
    _validateForm(form) {
        const errors = [];
        const requiredFields = form.querySelectorAll('[required]');
        
        requiredFields.forEach(field => {
            if (!field.value.trim()) {
                errors.push({
                    field: field.name,
                    message: `${field.getAttribute('data-label') || field.name} is required`
                });
            }
        });

        // Validate phone numbers
        const phoneFields = form.querySelectorAll('[type="tel"]');
        const phoneRegex = /^\+?[\d\s-()]{10,}$/;
        
        phoneFields.forEach(field => {
            if (field.value && !phoneRegex.test(field.value)) {
                errors.push({
                    field: field.name,
                    message: 'Please enter a valid phone number'
                });
            }
        });

        return {
            isValid: errors.length === 0,
            errors
        };
    },

    // Show validation errors
    _showValidationErrors(errors) {
        errors.forEach(error => {
            const field = document.querySelector(`[name="${error.field}"]`);
                if (field) {
                field.classList.add('is-invalid');
                
                // Create or update error message
                let errorDiv = field.nextElementSibling;
                if (!errorDiv || !errorDiv.classList.contains('invalid-feedback')) {
                    errorDiv = document.createElement('div');
                    errorDiv.className = 'invalid-feedback';
                    field.parentNode.insertBefore(errorDiv, field.nextSibling);
                }
                errorDiv.textContent = error.message;
            }
        });
    },

    // Clear form errors
    _clearFormErrors() {
        const form = document.getElementById('incidentForm');
        if (!form) return;

        // Remove validation classes
        form.querySelectorAll('.is-invalid').forEach(field => {
            field.classList.remove('is-invalid');
        });

        // Remove error messages
        form.querySelectorAll('.invalid-feedback').forEach(errorDiv => {
            errorDiv.remove();
        });
    },

    // Add a log entry
    _addLogEntry(message, type = 'info') {
        const liveLog = document.getElementById('liveLog');
        if (!liveLog) return;

        const entry = document.createElement('div');
        entry.className = 'log-entry';
        
        const timestamp = document.createElement('span');
        timestamp.className = 'log-timestamp';
        timestamp.textContent = new Date().toLocaleTimeString();
        
        const messageSpan = document.createElement('span');
        messageSpan.className = `log-message log-${type}`;
        messageSpan.textContent = message;
        
        entry.appendChild(timestamp);
        entry.appendChild(messageSpan);
        
        liveLog.insertBefore(entry, liveLog.firstChild);
        
        // Remove "No log entries yet" message if it exists
        const noEntries = liveLog.querySelector('.text-muted');
        if (noEntries) {
            noEntries.remove();
        }
    },

    // Show an alert message
    _showAlert(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const container = document.querySelector('.container-fluid');
        container.insertBefore(alertDiv, container.firstChild);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alertDiv.classList.remove('show');
            setTimeout(() => alertDiv.remove(), 150);
        }, 5000);
    }
};