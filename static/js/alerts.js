// Alert system for CAD System

/**
 * Display an alert/notification to the user
 * @param {string} type - Alert type (success, info, warning, error, danger)
 * @param {string} message - Message to display
 * @param {number} timeout - Auto-dismiss timeout in ms (0 for no auto-dismiss)
 */
function showAlert(type, message, timeout = 5000) {
    console.log(`Alert: ${type} - ${message}`);
    
    // Map "error" type to Bootstrap's "danger"
    if (type === 'error') type = 'danger';
    
    const alertContainer = document.getElementById('alert-container');
    if (!alertContainer) {
        console.error('Alert container not found');
        return;
    }
    
    // Create alert element
    const alertElement = document.createElement('div');
    alertElement.className = `alert alert-${type} alert-dismissible fade show`;
    alertElement.role = 'alert';
    alertElement.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Add to container
    alertContainer.appendChild(alertElement);
    
    // Create Bootstrap alert instance if Bootstrap is loaded
    if (window.bootstrap && window.bootstrap.Alert) {
        const bsAlert = new bootstrap.Alert(alertElement);
        
        // Auto-dismiss after timeout
        if (timeout > 0) {
            setTimeout(() => {
                try {
                    bsAlert.close();
                } catch (e) {
                    console.error('Error closing alert:', e);
                    alertElement.remove();
                }
            }, timeout);
        }
    } else {
        console.warn('Bootstrap Alert not available, using fallback');
        // Fallback for auto-dismiss
        if (timeout > 0) {
            setTimeout(() => {
                alertElement.remove();
            }, timeout);
        }
    }
    
    // Return the alert element for potential additional customization
    return alertElement;
}

// Shorthand functions for different alert types
const Alerts = {
    success: (message, timeout) => showAlert('success', message, timeout),
    info: (message, timeout) => showAlert('info', message, timeout),
    warning: (message, timeout) => showAlert('warning', message, timeout),
    error: (message, timeout) => showAlert('error', message, timeout),
    // Show a notification that requires acknowledgment
    confirm: (message) => showAlert('primary', message, 0)
};

// Make showAlert available globally
window.showAlert = showAlert;
window.Alerts = Alerts;
