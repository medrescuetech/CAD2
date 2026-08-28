// User Permissions Management
const UserPermissions = {
    init() {
        try {
            // Get permissions from APP_CONFIG
            if (!window.APP_CONFIG || !window.APP_CONFIG.permissions) {
                Logger.error('Permissions configuration not found');
                return;
            }
            
            this.permissions = window.APP_CONFIG.permissions;
            this.currentUser = window.APP_CONFIG.currentUser;
            
            // Initialize permission-based UI
            this.setupPermissionBasedUI();
            
            Logger.info('User permissions initialized');
        } catch (error) {
            Logger.error('Failed to initialize user permissions', { error: error.message });
        }
    },

    hasPermission(permission) {
        try {
            if (!this.currentUser) return false;
            if (!this.permissions[permission]) return false;
            
            // If user has admin permission, they have all permissions
            if ((this.currentUser.permissions & this.permissions.ADMIN) === this.permissions.ADMIN) {
                return true;
            }
            
            // Check specific permission
            return (this.currentUser.permissions & this.permissions[permission]) === this.permissions[permission];
        } catch (error) {
            Logger.error('Error checking permission', { error: error.message, permission });
            return false;
        }
    },

    hasAllPermissions(...permissions) {
        try {
            return permissions.every(permission => this.hasPermission(permission));
        } catch (error) {
            Logger.error('Error checking multiple permissions', { error: error.message, permissions });
            return false;
        }
    },

    hasAnyPermission(...permissions) {
        try {
            return permissions.some(permission => this.hasPermission(permission));
        } catch (error) {
            Logger.error('Error checking any permissions', { error: error.message, permissions });
            return false;
        }
    },

    isAdmin() {
        return this.hasPermission('ADMIN');
    },

    setupPermissionBasedUI() {
        try {
            // Hide/show elements based on permissions
            document.querySelectorAll('[data-requires-permission]').forEach(element => {
                const requiredPermission = element.dataset.requiresPermission;
                if (!this.hasPermission(requiredPermission)) {
                    element.style.display = 'none';
                }
            });

            // Handle admin-only elements
            document.querySelectorAll('[data-requires-admin]').forEach(element => {
                if (!this.isAdmin()) {
                    element.style.display = 'none';
                }
            });

            // Handle elements requiring multiple permissions
            document.querySelectorAll('[data-requires-all-permissions]').forEach(element => {
                const permissions = element.dataset.requiresAllPermissions.split(',');
                if (!this.hasAllPermissions(...permissions)) {
                    element.style.display = 'none';
                }
            });

            // Handle elements requiring any of multiple permissions
            document.querySelectorAll('[data-requires-any-permission]').forEach(element => {
                const permissions = element.dataset.requiresAnyPermission.split(',');
                if (!this.hasAnyPermission(...permissions)) {
                    element.style.display = 'none';
                }
            });

            Logger.info('Permission-based UI setup complete');
        } catch (error) {
            Logger.error('Error setting up permission-based UI', { error: error.message });
        }
    },

    // Common permission checks
    canViewIncidents() {
        return this.hasPermission('VIEW_INCIDENTS');
    },

    canManageIncidents() {
        return this.hasPermission('MANAGE_INCIDENTS');
    },

    canCreateIncidents() {
        return this.hasPermission('CREATE_INCIDENTS');
    },

    canCloseIncident() {
        return this.hasPermission('CLOSE_INCIDENT');
    },

    canViewUnits() {
        return this.hasPermission('VIEW_UNITS');
    },

    canManageUnits() {
        return this.hasPermission('MANAGE_UNITS');
    },

    canViewDailyLog() {
        return this.hasPermission('VIEW_DAILY_LOG');
    },

    canManageDailyLog() {
        return this.hasPermission('MANAGE_DAILY_LOG');
    },

    canViewLog() {
        return this.hasPermission('VIEW_LOG');
    },

    canCreateLog() {
        return this.hasPermission('CREATE_LOG');
    },

    canEditLog() {
        return this.hasPermission('EDIT_LOG');
    },

    canGenerateReports() {
        return this.hasPermission('GENERATE_REPORTS');
    },

    // Role management permissions
    canViewRoles() {
        return this.hasPermission('VIEW_USERS');
    },

    canManageRoles() {
        return this.hasPermission('MANAGE_ROLES');
    },

    canAssignRoles() {
        return this.hasPermission('MANAGE_ROLES');
    }
};

// Initialize permissions when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    UserPermissions.init();
}); 