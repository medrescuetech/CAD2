// Utility functions for CAD System

const Utils = {
    // Format timestamp to local time
    formatTimestamp(timestamp) {
        return new Date(timestamp).toLocaleString();
    },

    // Show toast notification
    showToast(message, type = 'info') {
        showAlert(type, message);
    },
    
    // Handle form submission
    async handleFormSubmit(form, options = {}) {
        const formData = new FormData(form);
        const data = options.processData ? options.processData(formData) : Object.fromEntries(formData.entries());
        
        try {
            const response = await fetch(options.url || form.action, {
                method: options.method || form.method || 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(options.headers || {})
                },
                body: JSON.stringify(data)
            });
            
            const responseData = await response.json();
            
            if (!response.ok) {
                throw new Error(responseData.message || 'Form submission failed');
            }
            
            if (options.onSuccess) {
                options.onSuccess(responseData);
            }
            
            return responseData;
            
        } catch (error) {
            if (window.errorHandler) {
                window.errorHandler.handleError('Form Submission Error', {
                    message: error.message,
                    form: form.id || form.name || 'unnamed-form',
                    error: error
                });
            }
            if (options.onError) {
                options.onError(error);
            }
            throw error;
        }
    }
};

// User Permissions management
const UserPermissions = {
    // Get permissions from meta tag
    getPermissions() {
        try {
            const configMeta = document.querySelector('meta[name="app-config"]');
            if (configMeta) {
                const config = JSON.parse(configMeta.content);
                return config.permissions || [];
            }
        } catch (error) {
            console.error('Failed to get permissions:', error);
            Logger.error('Failed to get permissions', { error: error.message });
        }
        return [];
    },

    // Check if user has specific permission
    hasPermission(permission) {
        const permissions = this.getPermissions();
        return permissions.includes(permission);
    },

    // Check if user has all permissions
    hasAllPermissions(...permissions) {
        return permissions.every(permission => this.hasPermission(permission));
    },

    // Check if user has any of the permissions
    hasAnyPermission(...permissions) {
        return permissions.some(permission => this.hasPermission(permission));
    },

    // Check if user is admin
    isAdmin() {
        return this.hasPermission('ADMIN');
    }
};

// Error logging utility
const Logger = {
    info(message, data = {}) {
        console.info(message, data);
    },

    error(message, data = {}) {
        if (window.errorHandler) {
            window.errorHandler.handleError('Logger Error', {
                message: message,
                ...data
            });
        } else {
            console.error(message, data);
        }
    },

    permissionDenied(message) {
        this.error('Permission Denied', { message });
        showAlert('error', message || 'You do not have permission to perform this action');
    }
};

// Initialize utilities
document.addEventListener('DOMContentLoaded', function() {
    try {
        const configMeta = document.querySelector('meta[name="app-config"]');
        if (configMeta) {
            window.APP_CONFIG = JSON.parse(configMeta.content);
        }
    } catch (error) {
        console.error('Failed to initialize utilities:', error);
    }
});
