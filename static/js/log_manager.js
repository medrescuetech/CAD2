class LogManager {
    static state = {
        logs: [],
        currentLog: null
    };
    
    static init() {
        // Only initialize if we're on a page that needs logging functionality
        if (window.location.pathname.includes('/auth/')) {
            return; // Skip initialization on auth pages
        }
        this.initializeEventListeners();
        this.loadCurrentLog();
    }
    
    static initializeEventListeners() {
        // Quick note form
        const quickNoteForm = document.getElementById('quickNoteForm');
        if (quickNoteForm) {
            quickNoteForm.setAttribute('data-custom-submit', 'true');
            quickNoteForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.addQuickNote();
            });
        }
        
        // Status update form
        const updateStatusForm = document.getElementById('updateStatusForm');
        if (updateStatusForm) {
            updateStatusForm.setAttribute('data-custom-submit', 'true');
            updateStatusForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.updateStatus();
            });
        }
        
        // Unit status form
        const unitStatusForm = document.getElementById('unitStatusForm');
        if (unitStatusForm) {
            unitStatusForm.setAttribute('data-custom-submit', 'true');
            unitStatusForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.updateUnitStatus();
            });
        }
        
        // Unit assignment form
        const unitAssignmentForm = document.getElementById('unitAssignmentForm');
        if (unitAssignmentForm) {
            unitAssignmentForm.setAttribute('data-custom-submit', 'true');
            unitAssignmentForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.assignUnit();
            });
        }
        
        // Protocol form
        const protocolForm = document.getElementById('protocolForm');
        if (protocolForm) {
            protocolForm.setAttribute('data-custom-submit', 'true');
            protocolForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.updateProtocol();
            });
        }
    }
    
    static async loadCurrentLog() {
        try {
            const response = await fetch('/api/logs/current', {
                method: 'GET'
            });
            
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.message || 'Failed to load current log');
            }
            
            this.state.currentLog = data.log;
            this.updateLogDisplay();
            
        } catch (error) {
            console.error('Error loading current log:', error);
            showAlert('error', error.message);
        }
    }
    
    static async addQuickNote() {
        try {
            const form = document.getElementById('quickNoteForm');
            if (!form) throw new Error('Quick note form not found');
            
            await Utils.handleFormSubmit(form, {
                url: '/api/logs/entries',
                method: 'POST',
                processData: (formData) => ({
                    log_id: this.state.currentLog?.id,
                    entry_type: 'quick_note',
                    content: formData.get('note'),
                    timestamp: new Date().toISOString()
                }),
                onSuccess: (data) => {
                    form.reset();
                    this.loadCurrentLog(); // Refresh log display
                }
            });
            
        } catch (error) {
            console.error('Error adding quick note:', error);
            showAlert('error', error.message);
        }
    }
    
    static async updateStatus() {
        try {
            const form = document.getElementById('updateStatusForm');
            if (!form) throw new Error('Status update form not found');
            
            await Utils.handleFormSubmit(form, {
                url: `/api/incidents/${form.getAttribute('data-incident-id')}/status`,
                method: 'PUT',
                processData: (formData) => ({
                    status: formData.get('status'),
                    note: formData.get('note')
                }),
                onSuccess: (data) => {
                    showAlert('success', 'Status updated successfully');
                    form.reset();
                    $('#statusModal').modal('hide'); // Hide modal if using Bootstrap
                }
            });
            
        } catch (error) {
            console.error('Error updating status:', error);
            showAlert('error', error.message);
        }
    }
    
    static async updateUnitStatus() {
        try {
            const form = document.getElementById('unitStatusForm');
            if (!form) throw new Error('Unit status form not found');
            
            await Utils.handleFormSubmit(form, {
                url: `/api/units/${form.getAttribute('data-unit-id')}/status`,
                method: 'PUT',
                processData: (formData) => ({
                    status: formData.get('status'),
                    note: formData.get('note'),
                    incident_id: form.getAttribute('data-incident-id')
                }),
                onSuccess: (data) => {
                    showAlert('success', 'Unit status updated successfully');
                    form.reset();
                    $('#unitStatusModal').modal('hide'); // Hide modal if using Bootstrap
                }
            });
            
        } catch (error) {
            console.error('Error updating unit status:', error);
            showAlert('error', error.message);
        }
    }
    
    static async assignUnit() {
        try {
            const form = document.getElementById('unitAssignmentForm');
            if (!form) throw new Error('Unit assignment form not found');
            
            await Utils.handleFormSubmit(form, {
                url: `/api/incidents/${form.getAttribute('data-incident-id')}/units`,
                method: 'POST',
                processData: (formData) => ({
                    unit_id: formData.get('unit_id'),
                    role: formData.get('role'),
                    note: formData.get('note')
                }),
                onSuccess: (data) => {
                    showAlert('success', 'Unit assigned successfully');
                    form.reset();
                    $('#assignUnitModal').modal('hide'); // Hide modal if using Bootstrap
                }
            });
            
        } catch (error) {
            console.error('Error assigning unit:', error);
            showAlert('error', error.message);
        }
    }
    
    static async updateProtocol() {
        try {
            const form = document.getElementById('protocolForm');
            if (!form) throw new Error('Protocol form not found');
            
            await Utils.handleFormSubmit(form, {
                url: `/api/incidents/${form.getAttribute('data-incident-id')}/protocol`,
                method: 'PUT',
                processData: (formData) => ({
                    protocol: formData.get('protocol'),
                    code: formData.get('code'),
                    note: formData.get('note')
                }),
                onSuccess: (data) => {
                    showAlert('success', 'Protocol updated successfully');
                    form.reset();
                    $('#protocolModal').modal('hide'); // Hide modal if using Bootstrap
                }
            });
            
        } catch (error) {
            console.error('Error updating protocol:', error);
            showAlert('error', error.message);
        }
    }
    
    static updateLogDisplay() {
        const logContainer = document.getElementById('logEntries');
        if (!logContainer || !this.state.currentLog) return;
        
        // Update log header
        const logHeader = document.getElementById('logHeader');
        if (logHeader) {
            logHeader.textContent = `Daily Log - ${new Date(this.state.currentLog.date).toLocaleDateString()}`;
        }
        
        // Update entries
        logContainer.innerHTML = '';
        this.state.currentLog.entries.forEach(entry => {
            const entryDiv = document.createElement('div');
            entryDiv.className = `log-entry log-entry-${entry.entry_type}`;
            
            entryDiv.innerHTML = `
                <div class="log-entry-header">
                    <span class="log-entry-time">${new Date(entry.timestamp).toLocaleTimeString()}</span>
                    <span class="log-entry-type">${entry.entry_type}</span>
                </div>
                <div class="log-entry-content">${entry.content}</div>
            `;
            
            logContainer.appendChild(entryDiv);
        });
        
        // Scroll to bottom
        logContainer.scrollTop = logContainer.scrollHeight;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    LogManager.init();
});
