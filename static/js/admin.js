// Admin functionality manager
class AdminManager {
    static async editUser(userId) {
        try {
            const response = await fetch(`/api/users/${userId}`);
            if (!response.ok) throw new Error('Failed to fetch user data');
            
            const userData = await response.json();
            
            // Populate form
            document.getElementById('userId').value = userData.id;
            document.getElementById('username').value = userData.username;
            document.getElementById('email').value = userData.email || '';
            document.getElementById('role').value = userData.role;
            
            // Set permissions
            const permissions = userData.permissions || [];
            document.querySelectorAll('input[name="permissions"]').forEach(checkbox => {
                checkbox.checked = permissions.includes(checkbox.value);
            });
            
            // Show modal
            const modal = new bootstrap.Modal(document.getElementById('userModal'));
            modal.show();
        } catch (error) {
            showAlert('danger', `Error editing user: ${error.message}`);
        }
    }
    
    static confirmDeleteUser(userId) {
        document.getElementById('confirmDeleteUserId').value = userId;
        const modal = new bootstrap.Modal(document.getElementById('confirmDeleteModal'));
        modal.show();
    }
    
    static async deleteUser() {
        const userId = document.getElementById('confirmDeleteUserId').value;
        try {
            const response = await fetch(`/api/users/${userId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) throw new Error('Failed to delete user');
            
            // Close modal and reload page
            bootstrap.Modal.getInstance(document.getElementById('confirmDeleteModal')).hide();
            location.reload();
        } catch (error) {
            showAlert('danger', `Error deleting user: ${error.message}`);
        }
    }
    
    static async saveUser() {
        try {
            const formData = new FormData(document.getElementById('userForm'));
            const userId = formData.get('id');
            
            // Convert form data to JSON
            const data = {
                username: formData.get('username'),
                email: formData.get('email'),
                role: formData.get('role'),
                permissions: Array.from(formData.getAll('permissions'))
            };
            
            // Add password only if it's provided (for new users or password changes)
            const password = formData.get('password');
            if (password) data.password = password;
            
            const response = await fetch(`/api/users${userId ? `/${userId}` : ''}`, {
                method: userId ? 'PUT' : 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });
            
            if (!response.ok) throw new Error('Failed to save user');
            
            // Close modal and reload page
            bootstrap.Modal.getInstance(document.getElementById('userModal')).hide();
            location.reload();
        } catch (error) {
            showAlert('danger', `Error saving user: ${error.message}`);
        }
    }
}
