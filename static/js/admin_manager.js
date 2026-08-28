class AdminManager {
    static state = {
        users: [],
        settings: {},
        roles: [],
        locations: [],
        apiKeys: []
    };
    
    static init() {
        this.initializeEventListeners();
        this.loadUsers();
        this.loadSettings();
        this.loadRoles();
        this.loadLocations();
        this.loadApiKeys();
    }
    
    static initializeEventListeners() {
        // User form
        const userForm = document.getElementById('userForm');
        if (userForm) {
            userForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.saveUser();
            });
        }

        // Settings form
        const settingsForm = document.getElementById('settingsForm');
        if (settingsForm) {
            settingsForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.saveSettings();
            });
        }

        // SMTP form
        const smtpForm = document.getElementById('smtpForm');
        if (smtpForm) {
            smtpForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.saveSmtpSettings();
            });
        }

        // Maps settings form
        const mapsForm = document.getElementById('mapsForm');
        if (mapsForm) {
            mapsForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.saveMapsSettings();
            });
        }

        // Role form
        const roleForm = document.getElementById('roleForm');
        if (roleForm) {
            roleForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.saveRole();
            });
        }

        // Location form
        const locationForm = document.getElementById('locationForm');
        if (locationForm) {
            locationForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.saveLocation();
            });
        }

        // API Key form
        const apiKeyForm = document.getElementById('apiKeyForm');
        if (apiKeyForm) {
            apiKeyForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.saveApiKey();
            });
        }

        // AMPDS form
        const ampdsForm = document.getElementById('ampdsForm');
        if (ampdsForm) {
            ampdsForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.saveAmpdsSettings();
            });
        }

        // Confirm delete buttons
        document.querySelectorAll('[data-confirm-delete]').forEach(btn => {
            btn.addEventListener('click', () => {
                const type = btn.getAttribute('data-confirm-delete');
                const id = btn.getAttribute('data-id');
                if (id) {
                    this.confirmDelete(type, id);
                }
            });
        });

        // Delete confirmation button
        const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
        if (confirmDeleteBtn) {
            confirmDeleteBtn.addEventListener('click', () => {
                const type = this.state.deleteType;
                const id = this.state.deleteId;
                if (type && id) {
                    const modal = bootstrap.Modal.getInstance(document.getElementById('confirmDeleteModal'));
                    modal.hide();
                    this.handleDelete(type, id);
                }
            });
        }
    }
    
    // User Management Functions
    static async loadUsers() {
        try {
            const response = await fetch('/admin/users');
            if (!response.ok) throw new Error('Failed to load users');
            
            const data = await response.json();
            this.state.users = data.users;
            this.refreshUserTable();
            
        } catch (error) {
            console.error('Error loading users:', error);
            this._showAlert('error', 'Failed to load users');
        }
    }
    
    static async saveUser() {
        const form = document.getElementById('userForm');
        if (!form || !form.checkValidity()) {
            form.reportValidity();
            return;
        }
        
        try {
            const formData = new FormData(form);
            const userData = {
                username: formData.get('username'),
                email: formData.get('email'),
                role: formData.get('role'),
                is_active: formData.get('is_active') === 'on',
                permissions: Array.from(formData.getAll('permissions'))
            };

            // Only include password if it's provided
            const password = formData.get('password');
            if (password) {
                userData.password = password;
            }

            const userId = form.getAttribute('data-user-id');
            const url = userId ? `/admin/users/${userId}` : '/admin/users';
            const method = userId ? 'PUT' : 'POST';

            const response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(userData)
            });

            if (!response.ok) throw new Error('Failed to save user');
            
            const modal = bootstrap.Modal.getInstance(document.getElementById('userModal'));
            modal.hide();
            
            this._showAlert('success', 'User saved successfully');
            this.loadUsers();
            
        } catch (error) {
            console.error('Error saving user:', error);
            this._showAlert('error', 'Failed to save user');
        }
    }
    
    static async deleteUser(userId) {
        try {
            const response = await fetch(`/admin/users/${userId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) throw new Error('Failed to delete user');
            
            this._showAlert('success', 'User deleted successfully');
            this.loadUsers();
            
        } catch (error) {
            console.error('Error deleting user:', error);
            this._showAlert('error', 'Failed to delete user');
        }
    }
    
    static editUser(userId) {
        const user = this.state.users.find(u => u.id === userId);
        if (!user) return;
        
        const form = document.getElementById('userForm');
        if (!form) return;
        
        form.setAttribute('data-user-id', user.id);
        document.querySelector('#userModal .modal-title').textContent = 'Edit User';
        
        // Populate form fields
        form.elements['username'].value = user.username;
        form.elements['email'].value = user.email;
        form.elements['password'].value = '';
        form.elements['role'].value = user.role;
        form.elements['is_active'].checked = user.is_active;
        
        // Set permissions
        const permCheckboxes = form.querySelectorAll('input[name="permissions"]');
        permCheckboxes.forEach(cb => {
            cb.checked = user.permissions.includes(cb.value);
        });
        
        // Trigger role change to update permission states
        const event = new Event('change');
        form.elements['role'].dispatchEvent(event);
        
        const modal = new bootstrap.Modal(document.getElementById('userModal'));
        modal.show();
    }
    
    static confirmDeleteUser(userId) {
        this.state.deleteUserId = userId;
        const modal = new bootstrap.Modal(document.getElementById('confirmDeleteModal'));
        modal.show();
    }
    
    // Settings Management Functions
    static async loadSettings() {
        try {
            const response = await fetch('/admin/settings/get/v2');
            if (!response.ok) throw new Error('Failed to load settings');
            
            const data = await response.json();
            this.state.settings = data.settings;
            this.refreshSettingsForm();
            
        } catch (error) {
            console.error('Error loading settings:', error);
            this._showAlert('error', 'Failed to load settings');
        }
    }
    
    static async saveSettings() {
        const form = document.getElementById('settingsForm');
        if (!form || !form.checkValidity()) {
            form.reportValidity();
            return;
        }
        
        try {
            const formData = new FormData(form);
            const settings = {};
            for (const [key, value] of formData.entries()) {
                settings[key] = value;
            }

            const response = await fetch('/admin/settings/update/v2', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            });

            if (!response.ok) throw new Error('Failed to save settings');
            
            this._showAlert('success', 'Settings saved successfully');
            this.loadSettings();
            
        } catch (error) {
            console.error('Error saving settings:', error);
            this._showAlert('error', 'Failed to save settings');
        }
    }
    
    // SMTP Settings Functions
    static async saveSmtpSettings() {
        const form = document.getElementById('smtpForm');
        if (!form || !form.checkValidity()) {
            form.reportValidity();
            return;
        }
        
        try {
            const formData = new FormData(form);
            const settings = {
                host: formData.get('smtp_host'),
                port: formData.get('smtp_port'),
                username: formData.get('smtp_username'),
                password: formData.get('smtp_password'),
                use_tls: formData.get('smtp_use_tls') === 'on',
                from_address: formData.get('smtp_from_address')
            };

            const response = await fetch('/admin/settings/smtp/v2', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            });

            if (!response.ok) throw new Error('Failed to save SMTP settings');
            
            this._showAlert('success', 'SMTP settings saved successfully');
            
        } catch (error) {
            console.error('Error saving SMTP settings:', error);
            this._showAlert('error', 'Failed to save SMTP settings');
        }
    }
    
    // Maps Settings Functions
    static async saveMapsSettings() {
        const form = document.getElementById('mapsForm');
        if (!form || !form.checkValidity()) {
            form.reportValidity();
            return;
        }
        
        try {
            const formData = new FormData(form);
            const settings = {
                provider: formData.get('map_provider'),
                api_key: formData.get('map_api_key'),
                default_center: formData.get('default_center'),
                default_zoom: formData.get('default_zoom')
            };

            const response = await fetch('/admin/settings/maps/v2', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            });

            if (!response.ok) throw new Error('Failed to save maps settings');
            
            this._showAlert('success', 'Maps settings saved successfully');
            
        } catch (error) {
            console.error('Error saving maps settings:', error);
            this._showAlert('error', 'Failed to save maps settings');
        }
    }
    
    // Role Management Functions
    static async loadRoles() {
        try {
            const response = await fetch('/admin/roles');
            if (!response.ok) throw new Error('Failed to load roles');
            
            const data = await response.json();
            this.state.roles = data.roles;
            this.refreshRoleTable();
            
        } catch (error) {
            console.error('Error loading roles:', error);
            this._showAlert('error', 'Failed to load roles');
        }
    }
    
    static async saveRole() {
        const form = document.getElementById('roleForm');
        if (!form || !form.checkValidity()) {
            form.reportValidity();
            return;
        }
        
        try {
            const formData = new FormData(form);
            const roleData = {
                name: formData.get('name'),
                description: formData.get('description'),
                permissions: Array.from(formData.getAll('permissions'))
            };

            const roleId = form.getAttribute('data-role-id');
            const url = roleId ? `/admin/roles/${roleId}` : '/admin/roles';
            const method = roleId ? 'PUT' : 'POST';

            const response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(roleData)
            });

            if (!response.ok) throw new Error('Failed to save role');
            
            const modal = bootstrap.Modal.getInstance(document.getElementById('roleModal'));
            modal.hide();
            
            this._showAlert('success', 'Role saved successfully');
            this.loadRoles();
            
        } catch (error) {
            console.error('Error saving role:', error);
            this._showAlert('error', 'Failed to save role');
        }
    }
    
    // Location Management Functions
    static async loadLocations() {
        try {
            const response = await fetch('/admin/locations');
            if (!response.ok) throw new Error('Failed to load locations');
            
            const data = await response.json();
            this.state.locations = data.locations;
            this.refreshLocationTable();
            
        } catch (error) {
            console.error('Error loading locations:', error);
            this._showAlert('error', 'Failed to load locations');
        }
    }
    
    static async saveLocation() {
        const form = document.getElementById('locationForm');
        if (!form || !form.checkValidity()) {
            form.reportValidity();
            return;
        }
        
        try {
            const formData = new FormData(form);
            const locationData = {
                name: formData.get('name'),
                address: formData.get('address'),
                latitude: formData.get('latitude'),
                longitude: formData.get('longitude'),
                type: formData.get('type')
            };

            const locationId = form.getAttribute('data-location-id');
            const url = locationId ? `/admin/locations/${locationId}` : '/admin/locations';
            const method = locationId ? 'PUT' : 'POST';

            const response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(locationData)
            });

            if (!response.ok) throw new Error('Failed to save location');
            
            const modal = bootstrap.Modal.getInstance(document.getElementById('locationModal'));
            modal.hide();
            
            this._showAlert('success', 'Location saved successfully');
            this.loadLocations();
            
        } catch (error) {
            console.error('Error saving location:', error);
            this._showAlert('error', 'Failed to save location');
        }
    }
    
    // API Key Management Functions
    static async loadApiKeys() {
        try {
            const response = await fetch('/admin/api-keys');
            if (!response.ok) throw new Error('Failed to load API keys');
            
            const data = await response.json();
            this.state.apiKeys = data.apiKeys;
            this.refreshApiKeyTable();
            
        } catch (error) {
            console.error('Error loading API keys:', error);
            this._showAlert('error', 'Failed to load API keys');
        }
    }
    
    static async saveApiKey() {
        const form = document.getElementById('apiKeyForm');
        if (!form || !form.checkValidity()) {
            form.reportValidity();
            return;
        }
        
        try {
            const formData = new FormData(form);
            const apiKeyData = {
                name: formData.get('name'),
                description: formData.get('description'),
                permissions: Array.from(formData.getAll('permissions')),
                expires_at: formData.get('expires_at')
            };

            const response = await fetch('/admin/api-keys', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(apiKeyData)
            });

            if (!response.ok) throw new Error('Failed to create API key');
            
            const modal = bootstrap.Modal.getInstance(document.getElementById('apiKeyModal'));
            modal.hide();
            
            this._showAlert('success', 'API key created successfully');
            this.loadApiKeys();
            
        } catch (error) {
            console.error('Error creating API key:', error);
            this._showAlert('error', 'Failed to create API key');
        }
    }
    
    // AMPDS Settings Functions
    static async saveAmpdsSettings() {
        const form = document.getElementById('ampdsForm');
        if (!form || !form.checkValidity()) {
            form.reportValidity();
            return;
        }
        
        try {
            const formData = new FormData(form);
            const settings = {
                enabled: formData.get('ampds_enabled') === 'on',
                api_key: formData.get('ampds_api_key'),
                endpoint: formData.get('ampds_endpoint'),
                version: formData.get('ampds_version')
            };

            const response = await fetch('/admin/settings/ampds/v2', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            });

            if (!response.ok) throw new Error('Failed to save AMPDS settings');
            
            this._showAlert('success', 'AMPDS settings saved successfully');
            
        } catch (error) {
            console.error('Error saving AMPDS settings:', error);
            this._showAlert('error', 'Failed to save AMPDS settings');
        }
    }
    
    // Delete Functions
    static async handleDelete(type, id) {
        const typeMap = {
            user: { url: `/admin/users/${id}`, reload: () => this.loadUsers() },
            role: { url: `/admin/roles/${id}`, reload: () => this.loadRoles() },
            location: { url: `/admin/locations/${id}`, reload: () => this.loadLocations() },
            apiKey: { url: `/admin/api-keys/${id}`, reload: () => this.loadApiKeys() }
        };
        
        const config = typeMap[type];
        if (!config) return;
        
        try {
            const response = await fetch(config.url, {
                method: 'DELETE'
            });
            
            if (!response.ok) throw new Error(`Failed to delete ${type}`);
            
            this._showAlert('success', `${type} deleted successfully`);
            config.reload();
            
        } catch (error) {
            console.error(`Error deleting ${type}:`, error);
            this._showAlert('error', `Failed to delete ${type}`);
        }
    }
    
    static confirmDelete(type, id) {
        this.state.deleteType = type;
        this.state.deleteId = id;
        const modal = new bootstrap.Modal(document.getElementById('confirmDeleteModal'));
        modal.show();
    }
    
    // Table Refresh Functions
    static refreshUserTable() {
        const tbody = document.querySelector('table tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        this.state.users.forEach(user => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${user.username}</td>
                <td>${user.email}</td>
                <td>${user.role}</td>
                <td>
                    <span class="badge bg-${user.is_active ? 'success' : 'danger'}">
                        ${user.is_active ? 'Active' : 'Inactive'}
                    </span>
                </td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-primary" onclick="AdminManager.editUser('${user.id}')" title="Edit User">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="AdminManager.confirmDelete('user', '${user.id}')" title="Delete User">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    static refreshRoleTable() {
        const tbody = document.querySelector('table tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        this.state.roles.forEach(role => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${role.name}</td>
                <td>${role.description}</td>
                <td>
                    ${role.permissions.map(perm => `<span class="badge bg-primary">${perm}</span>`).join(' ')}
                </td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-primary" onclick="AdminManager.editRole('${role.id}')" title="Edit Role">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="AdminManager.confirmDelete('role', '${role.id}')" title="Delete Role">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    static refreshLocationTable() {
        const tbody = document.querySelector('table tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        this.state.locations.forEach(location => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${location.name}</td>
                <td>${location.address}</td>
                <td>${location.type}</td>
                <td>${location.latitude}</td>
                <td>${location.longitude}</td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-primary" onclick="AdminManager.editLocation('${location.id}')" title="Edit Location">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="AdminManager.confirmDelete('location', '${location.id}')" title="Delete Location">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    static refreshApiKeyTable() {
        const tbody = document.querySelector('table tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        this.state.apiKeys.forEach(key => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${key.name}</td>
                <td>${key.description}</td>
                <td><code>...${key.key.slice(-8)}</code></td>
                <td>${key.created_at}</td>
                <td>${key.expires_at || 'Never'}</td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-warning" onclick="AdminManager.toggleApiKey('${key.id}')" title="Toggle API Key">
                            ${key.active ? 'Deactivate' : 'Activate'}
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="AdminManager.confirmDelete('apiKey', '${key.id}')" title="Delete API Key">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    static refreshSettingsForm() {
        const form = document.getElementById('settingsForm');
        if (!form) return;
        
        Object.entries(this.state.settings).forEach(([key, value]) => {
            const field = form.elements[key];
            if (field) {
                if (field.type === 'checkbox') {
                    field.checked = value === true || value === 'true';
                } else {
                    field.value = value;
                }
            }
        });
    }
    
    // Utility Functions
    static _showAlert(type, message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const container = document.querySelector('.container-fluid');
        if (container) {
            container.insertBefore(alertDiv, container.firstChild);
            
            // Auto-dismiss after 5 seconds
            setTimeout(() => {
                alertDiv.remove();
            }, 5000);
        }
    }
    
    static async changePassword(form) {
        const formData = new FormData(form);
        try {
            const response = await fetch('/auth/change-password', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            const data = await response.json();
            
            if (data.success) {
                this._showAlert('success', 'Password changed successfully');
                form.reset();
            } else {
                this._showAlert('error', data.message || 'Failed to change password');
            }
        } catch (error) {
            console.error('Error changing password:', error);
            this._showAlert('error', 'An error occurred while changing password');
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    AdminManager.init();
});
