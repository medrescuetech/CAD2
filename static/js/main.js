// Main JavaScript for CAD System

// Initialize core functionality
document.addEventListener('DOMContentLoaded', function() {
    // Initialize WebSocket connection
    window.webSocketManager.connect();
    
    // Initialize app configuration
    try {
        const configMeta = document.querySelector('meta[name="app-config"]');
        if (configMeta) {
            window.APP_CONFIG = JSON.parse(configMeta.content);
        }
    } catch (error) {
        console.error('Failed to initialize app configuration:', error);
    }

    // Skip certain initializations on auth pages
    if (window.location.pathname.includes('/auth/')) {
        return;
    }

    // Track page loads
    Logger.info('Page loaded', {
        path: window.location.pathname,
        title: document.title
    });

    // Track all button clicks
    document.addEventListener('click', function(event) {
        const button = event.target.closest('button');
        if (button) {
            Logger.info('Button clicked', {
                buttonId: button.id || 'unnamed-button',
                buttonText: button.textContent.trim(),
                buttonType: button.type || 'button'
            });
        }
    });

    // Handle link clicks with loading state
    document.addEventListener('click', function(event) {
        const link = event.target.closest('a');
        if (!link) return;

        // Skip if it's a dropdown toggle or has a data-bs-toggle attribute
        if (link.classList.contains('dropdown-toggle') || link.hasAttribute('data-bs-toggle')) {
            return;
        }

        // Skip if it's an external link
        if (link.getAttribute('target') === '_blank' || link.host !== window.location.host) {
            return;
        }

        // Skip if it's a JavaScript link
        if (link.href.startsWith('javascript:')) {
            return;
        }

        // Skip if it's marked as no-loading
        if (link.hasAttribute('data-no-loading')) {
            return;
        }

        // Show loading state
        const loadingIndicator = document.getElementById('loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.classList.add('loading');
            document.body.classList.add('page-loading');
        }

        Logger.info('Link clicked', {
            linkHref: link.href,
            linkText: link.textContent.trim()
        });
    });

    // Track form submissions with loading state
    document.addEventListener('submit', function(event) {
        // Only handle regular form submissions
        if (event.target.hasAttribute('data-custom-submit')) {
            return;
        }
        
        const form = event.target;
        const loadingIndicator = document.getElementById('loading-indicator');
        
        if (loadingIndicator) {
            loadingIndicator.classList.add('loading');
            document.body.classList.add('page-loading');
        }
        
        Logger.info('Form submitted', {
            formId: form.id || 'unnamed-form',
            formAction: form.action,
            formMethod: form.method
        });
    });

    // Handle page visibility changes
    document.addEventListener('visibilitychange', function() {
        const loadingIndicator = document.getElementById('loading-indicator');
        if (document.visibilityState === 'hidden' && loadingIndicator) {
            loadingIndicator.classList.remove('loading');
            document.body.classList.remove('page-loading');
        }
    });

    // Handle page unload
    window.addEventListener('beforeunload', function() {
        const loadingIndicator = document.getElementById('loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.classList.remove('loading');
            document.body.classList.remove('page-loading');
        }
    });

    // Track AJAX errors
    window.addEventListener('error', function(event) {
        if (event.target instanceof HTMLElement) {
            if (event.target.tagName === 'IMG' || event.target.tagName === 'SCRIPT' || event.target.tagName === 'LINK') {
                Logger.error('Resource load error', {
                    element: event.target.tagName,
                    source: event.target.src || event.target.href
                });
            }
        }
    }, true);

    // Track JavaScript errors
    window.onerror = function(message, source, lineno, colno, error) {
        Logger.error('JavaScript error', {
            message: message,
            source: source,
            line: lineno,
            column: colno,
            stack: error ? error.stack : null
        });
        return false;
    };

    // Track unhandled promise rejections
    window.addEventListener('unhandledrejection', function(event) {
        Logger.error('Unhandled Promise rejection', {
            reason: event.reason,
            stack: event.reason.stack
        });
    });

    // Handle daily log creation
    const createDailyLogBtn = document.getElementById('createDailyLogBtn');
    if (createDailyLogBtn) {
        createDailyLogBtn.addEventListener('click', function() {
            fetch('/daily_log/new', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => {
                if (response.status === 403) {
                    Logger.permissionDenied('Permission denied creating new log');
                    throw new Error('Permission denied');
                }
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    Logger.info('New log created successfully', { log_id: data.log_id });
                    Utils.showToast('New log created successfully', 'success');
                    window.location.href = '/daily_log/' + data.log_id;
                } else {
                    throw new Error(data.message || 'Error creating new log');
                }
            })
            .catch(error => {
                Logger.error('Failed to create new log', { error: error.message });
                Utils.showToast('Error creating new log: ' + error.message, 'danger');
            });
        });
    }

    // Update timestamps to local time
    function updateTimestamps() {
        try {
            document.querySelectorAll('[data-timestamp]').forEach(element => {
                const timestamp = element.getAttribute('data-timestamp');
                if (timestamp) {
                    element.textContent = Utils.formatTimestamp(timestamp);
                }
            });
            Logger.info('Timestamps updated successfully');
        } catch (error) {
            Logger.error('Error updating timestamps', { error: error.message });
        }
    }

    // Setup permission-based UI elements
    function setupPermissionBasedUI() {
        try {
            // Hide/show elements based on permissions
            document.querySelectorAll('[data-requires-permission]').forEach(element => {
                const requiredPermission = element.dataset.requiresPermission;
                if (!UserPermissions.hasPermission(requiredPermission)) {
                    element.style.display = 'none';
                }
            });

            // Handle admin-only elements
            document.querySelectorAll('[data-requires-admin]').forEach(element => {
                if (!UserPermissions.isAdmin()) {
                    element.style.display = 'none';
                }
            });

            // Handle elements requiring multiple permissions
            document.querySelectorAll('[data-requires-all-permissions]').forEach(element => {
                const permissions = element.dataset.requiresAllPermissions.split(',');
                if (!UserPermissions.hasAllPermissions(...permissions)) {
                    element.style.display = 'none';
                }
            });

            // Handle elements requiring any of multiple permissions
            document.querySelectorAll('[data-requires-any-permission]').forEach(element => {
                const permissions = element.dataset.requiresAnyPermission.split(',');
                if (!UserPermissions.hasAnyPermission(...permissions)) {
                    element.style.display = 'none';
                }
            });

            Logger.info('Permission-based UI setup complete');
        } catch (error) {
            Logger.error('Error setting up permission-based UI', { error: error.message });
        }
    }

    // Daily Log Functions
    function createNewLog() {
        try {
            if (!UserPermissions.canManageDailyLog()) {
                Logger.permissionDenied('Attempted to create new log without permission');
                Utils.showToast('Permission denied', 'error');
                return;
            }

            fetch('/daily_log/new', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => {
                if (response.status === 403) {
                    Logger.permissionDenied('Permission denied creating new log');
                    throw new Error('Permission denied');
                }
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    Logger.info('New log created successfully', { log_id: data.log_id });
                    Utils.showToast('New log created successfully', 'success');
                    window.location.href = '/daily_log/' + data.log_id;
                } else {
                    throw new Error(data.message || 'Error creating new log');
                }
            })
            .catch(error => {
                Logger.error('Failed to create new log', { error: error.message });
                Utils.showToast('Error creating new log: ' + error.message, 'danger');
            });
        } catch (error) {
            Logger.error('Error in createNewLog', { error: error.message });
            Utils.showToast('Error creating new log', 'danger');
        }
    }

    // Show unit manager
    function showUnitManager() {
        try {
            if (!UserPermissions.canManageUnits()) {
                Logger.permissionDenied('Attempted to access unit manager without permission');
                Utils.showToast('Permission denied', 'error');
                return;
            }
            window.location.href = '/manage_units';
        } catch (error) {
            Logger.error('Error showing unit manager', { error: error.message });
            Utils.showToast('Error accessing unit manager', 'danger');
        }
    }

    // Show new incident form
    function showNewIncident() {
        try {
            if (!UserPermissions.canCreateIncidents()) {
                Logger.permissionDenied('Attempted to create new incident without permission');
                Utils.showToast('Permission denied', 'error');
                return;
            }
            window.location.href = '/incident';
        } catch (error) {
            Logger.error('Error in showNewIncident', { error: error.message });
            Utils.showToast('Error opening new incident form', 'danger');
        }
    }

    // Show daily log
    function showDailyLog() {
        try {
            if (!UserPermissions.canViewDailyLog()) {
                Logger.permissionDenied('Attempted to view daily log without permission');
                Utils.showToast('Permission denied', 'error');
                return;
            }
            window.location.href = '/daily_log';
        } catch (error) {
            Logger.error('Error in showDailyLog', { error: error.message });
            Utils.showToast('Error opening daily log', 'danger');
        }
    }

    // Make functions globally available
    window.showUnitManager = showUnitManager;
    window.createNewLog = createNewLog;
});

// Setup error handling
function setupErrorHandling() {
    window.onerror = function(msg, url, line, col, error) {
        ErrorLogger.logError({
            message: msg,
            source: url,
            line: line,
            column: col,
            error: error
        });
        return false;
    };
}
