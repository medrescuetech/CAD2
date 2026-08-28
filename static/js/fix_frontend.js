/**
 * Frontend Fix and Test Script
 * 
 * This script identifies and fixes issues with the template functions
 * in the existing frontend without creating a new system.
 */

// Check for missing functions and add them if they don't exist
document.addEventListener('DOMContentLoaded', function() {
    console.log('Running frontend diagnostics...');
    
    // Fix 1: Check if showAlert function exists, if not create it
    if (typeof window.showAlert !== 'function') {
        console.error('Missing showAlert function detected - adding implementation');
        
        // Implement the missing showAlert function
        window.showAlert = function(type, message, timeout = 5000) {
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
        };
        
        console.log('✅ Added showAlert function');
    } else {
        console.log('✅ showAlert function already exists');
    }
    
    // Fix 2: Check if Alerts object exists, if not create it
    if (typeof window.Alerts !== 'object') {
        console.error('Missing Alerts object detected - adding implementation');
        
        // Create an Alerts object with shorthand methods
        window.Alerts = {
            success: (message, timeout) => window.showAlert('success', message, timeout),
            info: (message, timeout) => window.showAlert('info', message, timeout),
            warning: (message, timeout) => window.showAlert('warning', message, timeout),
            error: (message, timeout) => window.showAlert('error', message, timeout),
            confirm: (message) => window.showAlert('primary', message, 0)
        };
        
        console.log('✅ Added Alerts object');
    } else {
        console.log('✅ Alerts object already exists');
    }
    
    // Fix 3: Check if APP_CONFIG is initialized
    if (!window.APP_CONFIG) {
        console.error('Missing APP_CONFIG detected - initializing from meta tag');
        
        try {
            const configMeta = document.querySelector('meta[name="app-config"]');
            if (configMeta) {
                window.APP_CONFIG = JSON.parse(configMeta.content);
                console.log('✅ Initialized APP_CONFIG from meta tag');
            } else {
                console.error('Could not find app-config meta tag');
                // Create a minimal fallback config
                window.APP_CONFIG = {
                    environment: 'development',
                    debug: true,
                    testing: true,
                    permissions: []
                };
                console.log('✅ Created fallback APP_CONFIG');
            }
        } catch (error) {
            console.error('Failed to initialize APP_CONFIG:', error);
        }
    } else {
        console.log('✅ APP_CONFIG already initialized');
    }
    
    // Check if all critical components are available
    const diagnostics = {
        'jQuery': typeof jQuery !== 'undefined',
        'Bootstrap': typeof bootstrap !== 'undefined',
        'showAlert': typeof window.showAlert === 'function',
        'Alerts': typeof window.Alerts === 'object',
        'APP_CONFIG': typeof window.APP_CONFIG === 'object',
        'errorHandler': typeof window.errorHandler === 'object'
    };
    
    console.log('===== FRONTEND DIAGNOSTICS =====');
    for (const [component, available] of Object.entries(diagnostics)) {
        console.log(`${available ? '✅' : '❌'} ${component}: ${available ? 'Available' : 'Missing'}`);
    }
    
    // Create a diagnostic alert if we're in dev/test mode
    if (window.APP_CONFIG && (window.APP_CONFIG.debug || window.APP_CONFIG.testing)) {
        // Test the alert system with different alert types
        setTimeout(() => {
            if (typeof window.showAlert === 'function') {
                window.showAlert('success', 'Frontend diagnostic complete - showAlert function is working', 3000);
            }
        }, 1000);
    }
});
