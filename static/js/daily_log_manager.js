class DailyLogManager {
    static state = {
        currentLog: null,
        autoSaveInterval: null,
        systemEvents: [],
        entryTypes: ['GENERAL', 'INCIDENT', 'FOLLOW_UP', 'CALL', 'EVENT', 'COMMUNICATION', 'RESOURCE', 'ADMIN', 'OTHER']
    };
    
    static init() {
        this.initializeEventListeners();
        this.loadCurrentLog();
        this.startAutoSave();
        
        // If we're on the system events page, load system events
        if (document.getElementById('systemEvents')) {
            this.loadSystemEvents();
        }
        
        // Setup filter form if it exists
        if (document.getElementById('logFilterForm')) {
            this.setupFilters();
        }
    }
    
    static initializeEventListeners() {
        // Quick entry form
        const quickEntryForm = document.getElementById('quickEntryForm');
        if (quickEntryForm) {
            quickEntryForm.setAttribute('data-custom-submit', 'true');
            quickEntryForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.addLogEntry();
            });
        }
        
        // Log entry input
        const logEntry = document.getElementById('logEntry');
        if (logEntry) {
            logEntry.addEventListener('keypress', (event) => {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    this.addLogEntry();
                }
            });
        }
        
        // Save and exit button
        const saveExitBtn = document.getElementById('saveExitBtn');
        if (saveExitBtn) {
            saveExitBtn.addEventListener('click', () => this.saveLog(true));
        }
        
        // Save button
        const saveBtn = document.getElementById('saveBtn');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveLog(false));
        }
        
        // PDF button
        const pdfBtn = document.getElementById('pdfBtn');
        if (pdfBtn) {
            pdfBtn.addEventListener('click', () => this.generatePDF());
        }
        
        // Setup entry type dropdown
        const logTypeSelect = document.getElementById('logType');
        if (logTypeSelect && logTypeSelect.options.length === 0) {
            this.state.entryTypes.forEach(type => {
                const option = document.createElement('option');
                option.value = type;
                option.textContent = type.replace('_', ' ');
                logTypeSelect.appendChild(option);
            });
        }
    }
    
    static async loadCurrentLog() {
        try {
            const response = await fetch('/api/daily_log/current', {
                headers: {
                    'Content-Type': 'application/json'
                }
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
    
    static async addLogEntry() {
        try {
            const text = document.getElementById('logEntry').value.trim();
            const type = document.getElementById('logType').value;
            
            if (!text) return;
            
            const response = await fetch('/api/daily_log/entry', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: text,
                    type: type,
                    log_id: this.state.currentLog?.id
                })
            });
            
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.message || 'Failed to add log entry');
            }
            
            // Add entry to display
            this.addEntryToDisplay({
                id: data.entry.id,
                timestamp: new Date(),
                type: type,
                text: text,
                user_name: document.querySelector('meta[name="username"]')?.content,
                user_id: document.querySelector('meta[name="user_id"]')?.content
            });
            
            // Clear input
            document.getElementById('logEntry').value = '';
            
        } catch (error) {
            console.error('Error adding log entry:', error);
            showAlert('error', error.message);
        }
    }
    
    static async updateLogEntry(entryId, text, type) {
        try {
            const response = await fetch(`/api/daily_log/entry/${entryId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: text,
                    type: type
                })
            });
            
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.message || 'Failed to update log entry');
            }
            
            // Update the entry in display
            const entryElement = document.querySelector(`.log-entry[data-id="${entryId}"]`);
            if (entryElement) {
                entryElement.querySelector('.log-type').textContent = type;
                entryElement.querySelector('.log-type').className = `log-type type-${type}`;
                entryElement.querySelector('.log-text').textContent = text;
            }
            
            showAlert('success', 'Entry updated successfully');
            
        } catch (error) {
            console.error('Error updating log entry:', error);
            showAlert('error', error.message);
        }
    }
    
    static async deleteLogEntry(entryId) {
        try {
            if (!confirm('Are you sure you want to delete this entry?')) {
                return;
            }
            
            const response = await fetch(`/api/daily_log/entry/${entryId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.message || 'Failed to delete log entry');
            }
            
            // Remove the entry from display
            const entryElement = document.querySelector(`.log-entry[data-id="${entryId}"]`);
            if (entryElement) {
                entryElement.remove();
            }
            
            showAlert('success', 'Entry deleted successfully');
            
        } catch (error) {
            console.error('Error deleting log entry:', error);
            showAlert('error', error.message);
        }
    }
    
    static async saveLog(andExit = false) {
        try {
            const response = await fetch(`/api/daily_log/${this.state.currentLog.id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    notes: document.getElementById('logNotes')?.value || this.state.currentLog.notes
                })
            });
            
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.message || 'Failed to save log');
            }
            
            if (andExit) {
                window.location.href = '/daily_logs';
            } else {
                showAlert('success', 'Log saved successfully');
            }
            
        } catch (error) {
            console.error('Error saving log:', error);
            showAlert('error', error.message);
        }
    }
    
    static async generatePDF() {
        try {
            window.location.href = `/api/daily_log/${this.state.currentLog.id}/pdf`;
        } catch (error) {
            console.error('Error generating PDF:', error);
            showAlert('error', error.message);
        }
    }
    
    static startAutoSave() {
        // Auto-save every 5 minutes
        this.state.autoSaveInterval = setInterval(() => this.saveLog(), 300000);
    }
    
    static stopAutoSave() {
        if (this.state.autoSaveInterval) {
            clearInterval(this.state.autoSaveInterval);
            this.state.autoSaveInterval = null;
        }
    }
    
    static addEntryToDisplay(entry) {
        const container = document.getElementById('logEntries');
        if (!container) return;
        
        const entryDiv = document.createElement('div');
        entryDiv.className = 'log-entry';
        entryDiv.setAttribute('data-id', entry.id);
        
        // Determine if the current user is the entry author
        const isCurrentUser = entry.user_id === document.querySelector('meta[name="user_id"]')?.content;
        const isAdmin = document.querySelector('meta[name="is_admin"]')?.content === 'true';
        const canEdit = isCurrentUser || isAdmin;
        
        // Create entry content
        entryDiv.innerHTML = `
            <span class="log-timestamp">${entry.timestamp.toLocaleTimeString()}</span>
            <span class="log-type type-${entry.type}">${entry.type}</span>
            <span class="log-text">${entry.text}</span>
            <span class="log-user">${entry.user_name}</span>
            ${canEdit ? `
            <div class="log-actions">
                <button class="btn-edit btn-sm btn-outline-primary"><i class="fas fa-edit"></i></button>
                <button class="btn-delete btn-sm btn-outline-danger"><i class="fas fa-trash"></i></button>
            </div>
            ` : ''}
        `;
        
        // Add entry actions if user can edit
        if (canEdit) {
            // Add edit button event
            entryDiv.querySelector('.btn-edit').addEventListener('click', () => {
                this.showEditEntryModal(entry.id, entry.text, entry.type);
            });
            
            // Add delete button event
            entryDiv.querySelector('.btn-delete').addEventListener('click', () => {
                this.deleteLogEntry(entry.id);
            });
        }
        
        // Add highlight class if entry has highlight flag
        if (entry.text_highlight) {
            entryDiv.classList.add('highlighted');
        }
        
        container.insertBefore(entryDiv, container.firstChild);
        container.scrollTop = 0;
    }
    
    static showEditEntryModal(entryId, text, type) {
        // Create or get modal element
        let modal = document.getElementById('editEntryModal');
        
        if (!modal) {
            // Create modal if it doesn't exist
            modal = document.createElement('div');
            modal.id = 'editEntryModal';
            modal.className = 'modal fade';
            modal.setAttribute('tabindex', '-1');
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-labelledby', 'editEntryModalLabel');
            modal.setAttribute('aria-hidden', 'true');
            
            modal.innerHTML = `
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="editEntryModalLabel">Edit Log Entry</h5>
                            <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                                <span aria-hidden="true">&times;</span>
                            </button>
                        </div>
                        <div class="modal-body">
                            <form id="editEntryForm">
                                <div class="form-group">
                                    <label for="editEntryType">Entry Type</label>
                                    <select class="form-control" id="editEntryType" required></select>
                                </div>
                                <div class="form-group">
                                    <label for="editEntryText">Entry Text</label>
                                    <textarea class="form-control" id="editEntryText" rows="3" required></textarea>
                                </div>
                                <input type="hidden" id="editEntryId">
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-primary" id="saveEditBtn">Save Changes</button>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            // Fill entry type dropdown
            const editEntryType = document.getElementById('editEntryType');
            this.state.entryTypes.forEach(typeOption => {
                const option = document.createElement('option');
                option.value = typeOption;
                option.textContent = typeOption.replace('_', ' ');
                editEntryType.appendChild(option);
            });
            
            // Add save button event
            document.getElementById('saveEditBtn').addEventListener('click', () => {
                const id = document.getElementById('editEntryId').value;
                const text = document.getElementById('editEntryText').value;
                const type = document.getElementById('editEntryType').value;
                
                this.updateLogEntry(id, text, type);
                $('#editEntryModal').modal('hide');
            });
        }
        
        // Set form values
        document.getElementById('editEntryId').value = entryId;
        document.getElementById('editEntryText').value = text;
        document.getElementById('editEntryType').value = type;
        
        // Show modal
        $('#editEntryModal').modal('show');
    }
    
    static updateLogDisplay() {
        const container = document.getElementById('logEntries');
        if (!container || !this.state.currentLog) return;
        
        // Update header
        const header = document.querySelector('h4');
        if (header) {
            header.textContent = `Daily Log - ${this.state.currentLog.log_number}`;
        }
        
        // Update notes field if exists
        const notesField = document.getElementById('logNotes');
        if (notesField) {
            notesField.value = this.state.currentLog.notes || '';
        }
        
        // Clear container
        container.innerHTML = '';
        
        // Add entries
        if (this.state.currentLog.entries && this.state.currentLog.entries.length > 0) {
            this.state.currentLog.entries.forEach(entry => {
                // Convert the timestamp string to Date object
                const timestamp = entry.timestamp ? new Date(entry.timestamp) : new Date();
                this.addEntryToDisplay({
                    ...entry,
                    timestamp: timestamp
                });
            });
        } else {
            container.innerHTML = '<div class="text-center p-3 text-muted">No log entries yet.</div>';
        }
    }
    
    static async loadSystemEvents(limit = 50, eventType = null) {
        try {
            let url = `/api/daily_logs/system-events?limit=${limit}`;
            if (eventType) {
                url += `&event_type=${eventType}`;
            }
            
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.message || 'Failed to load system events');
            }
            
            this.state.systemEvents = data.events;
            
            // Update event type filter if it exists
            const typeFilter = document.getElementById('eventTypeFilter');
            if (typeFilter && data.types && typeFilter.options.length <= 1) {
                // Add event types to filter
                data.types.forEach(type => {
                    const option = document.createElement('option');
                    option.value = type;
                    option.textContent = type;
                    typeFilter.appendChild(option);
                });
                
                // Add filter change event
                typeFilter.addEventListener('change', (e) => {
                    this.loadSystemEvents(limit, e.target.value === 'ALL' ? null : e.target.value);
                });
            }
            
            this.updateSystemEventsDisplay();
            
        } catch (error) {
            console.error('Error loading system events:', error);
            showAlert('error', error.message);
        }
    }
    
    static updateSystemEventsDisplay() {
        const container = document.getElementById('systemEvents');
        if (!container) return;
        
        // Clear container
        container.innerHTML = '';
        
        if (this.state.systemEvents.length === 0) {
            container.innerHTML = '<div class="text-center p-3 text-muted">No system events found.</div>';
            return;
        }
        
        // Create table for system events
        const table = document.createElement('table');
        table.className = 'table table-striped table-hover';
        
        table.innerHTML = `
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Type</th>
                    <th>Message</th>
                    <th>User</th>
                </tr>
            </thead>
            <tbody></tbody>
        `;
        
        const tbody = table.querySelector('tbody');
        
        // Add events to table
        this.state.systemEvents.forEach(event => {
            const row = document.createElement('tr');
            row.className = `event-type-${event.type.toLowerCase()}`;
            
            // Format timestamp
            const timestamp = event.timestamp ? new Date(event.timestamp) : new Date();
            const formattedTime = `${timestamp.toLocaleDateString()} ${timestamp.toLocaleTimeString()}`;
            
            row.innerHTML = `
                <td>${formattedTime}</td>
                <td><span class="badge badge-${this.getTypeColor(event.type)}">${event.type}</span></td>
                <td>${event.text}</td>
                <td>${event.user_name || 'System'}</td>
            `;
            
            tbody.appendChild(row);
        });
        
        container.appendChild(table);
    }
    
    static getTypeColor(type) {
        const typeColors = {
            'SYSTEM': 'secondary',
            'INCIDENT': 'primary',
            'USER': 'info',
            'RESOURCE': 'success',
            'ERROR': 'danger',
            'SECURITY': 'warning',
            'MAINTENANCE': 'dark'
        };
        
        return typeColors[type] || 'secondary';
    }
    
    static async setupFilters() {
        const filterForm = document.getElementById('logFilterForm');
        if (!filterForm) return;
        
        // Set date input defaults
        const today = new Date();
        const startDate = document.getElementById('startDate');
        const endDate = document.getElementById('endDate');
        
        if (startDate) {
            const thirtyDaysAgo = new Date();
            thirtyDaysAgo.setDate(today.getDate() - 30);
            startDate.value = thirtyDaysAgo.toISOString().split('T')[0];
        }
        
        if (endDate) {
            endDate.value = today.toISOString().split('T')[0];
        }
        
        // Setup shift options
        const shiftSelect = document.getElementById('shift');
        if (shiftSelect) {
            ['All Shifts', 'morning', 'day', 'evening', 'night'].forEach(shift => {
                const option = document.createElement('option');
                option.value = shift === 'All Shifts' ? '' : shift;
                option.textContent = shift.charAt(0).toUpperCase() + shift.slice(1);
                shiftSelect.appendChild(option);
            });
        }
        
        // Setup entry type options
        const entryTypeSelect = document.getElementById('entryType');
        if (entryTypeSelect) {
            ['All Types', ...this.state.entryTypes].forEach(type => {
                const option = document.createElement('option');
                option.value = type === 'All Types' ? '' : type;
                option.textContent = type.replace('_', ' ');
                entryTypeSelect.appendChild(option);
            });
        }
        
        // Add submit event to form
        filterForm.addEventListener('submit', (event) => {
            event.preventDefault();
            this.searchLogs();
        });
    }
    
    static async searchLogs() {
        try {
            const searchTerm = document.getElementById('searchTerm')?.value || '';
            const startDate = document.getElementById('startDate')?.value || '';
            const endDate = document.getElementById('endDate')?.value || '';
            const shift = document.getElementById('shift')?.value || '';
            const entryType = document.getElementById('entryType')?.value || '';
            const searchEntries = document.getElementById('searchEntries')?.checked || true;
            
            // Build query URL
            let url = '/api/daily_logs/search?';
            const params = new URLSearchParams();
            
            if (searchTerm) params.append('q', searchTerm);
            if (startDate) params.append('start_date', startDate);
            if (endDate) params.append('end_date', endDate);
            if (shift) params.append('shift', shift);
            if (entryType) params.append('entry_type', entryType);
            params.append('search_entries', searchEntries);
            params.append('page', 1);
            params.append('per_page', 10);
            
            url += params.toString();
            
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.message || 'Failed to search logs');
            }
            
            this.displaySearchResults(data);
            
        } catch (error) {
            console.error('Error searching logs:', error);
            showAlert('error', error.message);
        }
    }
    
    static displaySearchResults(data) {
        const resultsContainer = document.getElementById('searchResults');
        if (!resultsContainer) return;
        
        // Clear container
        resultsContainer.innerHTML = '';
        
        if (!data.logs || data.logs.length === 0) {
            resultsContainer.innerHTML = '<div class="alert alert-info">No logs found matching your search criteria.</div>';
            return;
        }
        
        // Create results header
        const header = document.createElement('h5');
        header.textContent = `Found ${data.total} logs matching your search criteria`;
        resultsContainer.appendChild(header);
        
        // Create logs container
        const logsContainer = document.createElement('div');
        logsContainer.className = 'logs-container';
        
        // Add logs to container
        data.logs.forEach(log => {
            const logCard = document.createElement('div');
            logCard.className = 'card mb-3';
            
            let entriesHtml = '';
            if (log.entries && log.entries.length > 0) {
                entriesHtml = '<div class="log-entries mt-3">';
                // Show top 5 entries only for preview
                const previewEntries = log.entries.slice(0, 5);
                previewEntries.forEach(entry => {
                    const timestamp = entry.timestamp ? new Date(entry.timestamp) : new Date();
                    const highlightClass = entry.text_highlight ? 'highlighted' : '';
                    
                    entriesHtml += `
                        <div class="log-entry-preview ${highlightClass}">
                            <span class="log-timestamp">${timestamp.toLocaleTimeString()}</span>
                            <span class="log-type type-${entry.type}">${entry.type}</span>
                            <span class="log-text">${entry.text}</span>
                        </div>
                    `;
                });
                
                if (log.entries.length > 5) {
                    entriesHtml += `<div class="text-center"><small>${log.entries.length - 5} more entries...</small></div>`;
                }
                
                entriesHtml += '</div>';
            }
            
            const notesHtml = log.notes ? `
                <div class="log-notes mt-2 ${log.notes_highlight ? 'highlighted' : ''}">
                    <strong>Notes:</strong> ${log.notes}
                </div>
            ` : '';
            
            logCard.innerHTML = `
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h6 class="mb-0">${log.log_number || `Log #${log.id}`}</h6>
                    <div>
                        <span class="badge badge-info">${log.shift.toUpperCase()}</span>
                        <span class="badge badge-secondary">${log.date}</span>
                    </div>
                </div>
                <div class="card-body">
                    <p><strong>User:</strong> ${log.user}</p>
                    ${notesHtml}
                    ${entriesHtml}
                    <div class="mt-3 text-right">
                        <a href="/daily_log/${log.id}" class="btn btn-sm btn-primary">View Full Log</a>
                    </div>
                </div>
            `;
            
            logsContainer.appendChild(logCard);
        });
        
        resultsContainer.appendChild(logsContainer);
        
        // Add pagination if needed
        if (data.pages > 1) {
            const pagination = document.createElement('nav');
            pagination.setAttribute('aria-label', 'Search results pagination');
            
            let paginationHtml = '<ul class="pagination justify-content-center">';
            
            // Previous button
            paginationHtml += `
                <li class="page-item ${data.current_page === 1 ? 'disabled' : ''}">
                    <a class="page-link" href="#" data-page="${data.current_page - 1}">Previous</a>
                </li>
            `;
            
            // Page numbers
            for (let i = 1; i <= data.pages; i++) {
                paginationHtml += `
                    <li class="page-item ${data.current_page === i ? 'active' : ''}">
                        <a class="page-link" href="#" data-page="${i}">${i}</a>
                    </li>
                `;
            }
            
            // Next button
            paginationHtml += `
                <li class="page-item ${data.current_page === data.pages ? 'disabled' : ''}">
                    <a class="page-link" href="#" data-page="${data.current_page + 1}">Next</a>
                </li>
            `;
            
            paginationHtml += '</ul>';
            pagination.innerHTML = paginationHtml;
            
            // Add page click events
            pagination.querySelectorAll('.page-link').forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const page = parseInt(e.target.getAttribute('data-page'));
                    if (page < 1 || page > data.pages) return;
                    
                    // Update page parameter and search again
                    const url = new URL(window.location.href);
                    url.searchParams.set('page', page);
                    // TODO: Implement pagination search
                });
            });
            
            resultsContainer.appendChild(pagination);
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    DailyLogManager.init();
});
