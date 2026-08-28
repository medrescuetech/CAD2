document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const newLogForm = document.getElementById('newLogForm');
    const logTypeSelect = document.getElementById('logType');
    const logMessageInput = document.getElementById('logMessage');
    const saveNewLogBtn = document.getElementById('saveNewLogBtn');
    const logsTableBody = document.querySelector('table tbody');
    
    // Initialize log type select with data from server
    async function initializeLogTypes() {
        try {
            const response = await fetch('/api/log_types');
            if (!response.ok) throw new Error('Failed to fetch log types');
            
            const logTypes = await response.json();
            logTypeSelect.innerHTML = logTypes.map(type => 
                `<option value="${type.value}">${type.value}</option>`
            ).join('');
        } catch (error) {
            console.error('Error loading log types:', error);
            showToast('error', 'Failed to load log types');
        }
    }
    
    // Save new log entry
    async function saveNewLog() {
        if (!newLogForm.checkValidity()) {
            newLogForm.reportValidity();
            return;
        }
        
        try {
            const response = await fetch('/api/logs', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    type: logTypeSelect.value,
                    message: logMessageInput.value
                })
            });
            
            if (!response.ok) throw new Error('Failed to create log');
            
            const result = await response.json();
            if (result.success) {
                showToast('success', 'Log entry created successfully');
                refreshLogs();
                $('#newLogModal').modal('hide');
                newLogForm.reset();
            } else {
                throw new Error(result.message || 'Failed to create log');
            }
        } catch (error) {
            console.error('Error saving log:', error);
            showToast('error', error.message);
        }
    }
    
    // Refresh logs table
    async function refreshLogs() {
        try {
            const response = await fetch('/api/logs');
            if (!response.ok) throw new Error('Failed to fetch logs');
            
            const logs = await response.json();
            logsTableBody.innerHTML = logs.map(log => `
                <tr>
                    <td>${new Date(log.date).toLocaleDateString()}</td>
                    <td>${log.log_number}</td>
                    <td>${log.entry_type}</td>
                    <td>${log.message}</td>
                    <td>${log.user.username}</td>
                    <td>${new Date(log.created_at).toLocaleTimeString()}</td>
                    <td>
                        <div class="btn-group">
                            <button class="btn btn-sm btn-info view-log" data-log-id="${log.id}">
                                <i class="fas fa-eye"></i>
                            </button>
                            ${log.can_edit ? `
                                <button class="btn btn-sm btn-warning edit-log" data-log-id="${log.id}">
                                    <i class="fas fa-edit"></i>
                                </button>
                            ` : ''}
                            ${log.can_delete ? `
                                <button class="btn btn-sm btn-danger delete-log" data-log-id="${log.id}">
                                    <i class="fas fa-trash"></i>
                                </button>
                            ` : ''}
                        </div>
                    </td>
                </tr>
            `).join('');
        } catch (error) {
            console.error('Error refreshing logs:', error);
            showToast('error', 'Failed to refresh logs');
        }
    }
    
    // Event listeners
    saveNewLogBtn.addEventListener('click', saveNewLog);
    
    // Initialize
    initializeLogTypes();
    refreshLogs();
    
    // Auto-refresh every minute
    setInterval(refreshLogs, 60000);
});

document.getElementById('logDate').addEventListener('change', async function() {
    const date = this.value;
    try {
        const response = await fetch(`/api/logs?date=${date}`);
        const data = await response.json();
        if (data.success) {
            updateLogDisplay(data.logs);
        }
    } catch (error) {
        console.error('Error fetching logs:', error);
    }
});

function updateLogDisplay(logs) {
    const logContainer = document.getElementById('logEntries');
    logContainer.innerHTML = logs.map(log => `
        <div class="log-entry">
            <div class="log-header">
                <span class="timestamp">${new Date(log.created_at).toLocaleString()}</span>
                <span class="username">${log.created_by}</span>
            </div>
            <div class="log-message">
                ${log.incident_number ? `[${log.incident_number}] ` : ''}${log.message}
            </div>
        </div>
    `).join('');
}
