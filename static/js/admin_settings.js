document.addEventListener('DOMContentLoaded', function() {
    // Check admin access first
    if (!UserPermissions.isAdmin()) {
        Logger.permissionDenied('Attempted to access admin settings without permission');
        window.location.href = '/';
        return;
    }

    // Handle settings form submission
    const settingsForm = document.getElementById('settings-form');
    if (settingsForm) {
        settingsForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            if (!UserPermissions.isAdmin()) {
                Logger.permissionDenied('Attempted to submit admin settings without permission');
                showAlert('error', 'Permission denied');
                return;
            }
            
            const formData = new FormData(this);
            const data = {};
            for (let [key, value] of formData.entries()) {
                // Handle checkboxes
                if (this.elements[key].type === 'checkbox') {
                    data[key] = this.elements[key].checked;
                } else {
                    // Try to parse JSON values
                    try {
                        data[key] = JSON.parse(value);
                    } catch {
                        data[key] = value;
                    }
                }
            }
            
            try {
                const response = await fetch(this.action, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });
                
                if (response.ok) {
                    Logger.info('Admin settings saved successfully');
                    showAlert('success', 'Settings saved successfully');
                    location.reload();
                } else {
                    const error = await response.json();
                    Logger.error('Error saving admin settings', { error: error.message });
                    showAlert('error', `Error saving settings: ${error.message}`);
                }
            } catch (error) {
                Logger.error('Error saving admin settings', { error: error.message });
                showAlert('error', `Error saving settings: ${error.message}`);
            }
        });
    }
});

function showAlert(type, message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show`;
    alertDiv.role = 'alert';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    const container = document.querySelector('.container');
    container.insertBefore(alertDiv, container.firstChild);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}
