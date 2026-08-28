// User management functions

// Save new or updated user
async function saveUser() {
    try {
        const form = document.getElementById('addUserForm');
        const userId = form.dataset.userId;
        const data = {
            username: form.username.value,
            email: form.email.value,
            role: form.role.value
        };

        // Add password for new users or if password field exists and is not empty
        if (form.password && form.password.value) {
            data.password = form.password.value;
        }

        let url = '/admin/api/users';
        let method = 'POST';

        // If updating existing user
        if (userId) {
            url += `/${userId}`;
            method = 'PUT';
        }

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();
        if (result.success) {
            showAlert('success', result.message);
            // Close modal and refresh page
            const modal = bootstrap.Modal.getInstance(document.getElementById('addUserModal'));
            modal.hide();
            location.reload();
        } else {
            showAlert('danger', result.message);
        }
    } catch (error) {
        console.error('Error saving user:', error);
        showAlert('danger', 'An error occurred while saving the user');
    }
}

// Delete user
async function deleteUser(userId) {
    try {
        if (!confirm('Are you sure you want to delete this user?')) {
            return;
        }

        const response = await fetch(`/admin/api/users/${userId}`, {
            method: 'DELETE'
        });

        const result = await response.json();
        if (result.success) {
            showAlert('success', result.message);
            location.reload();
        } else {
            showAlert('danger', result.message);
        }
    } catch (error) {
        console.error('Error deleting user:', error);
        showAlert('danger', 'An error occurred while deleting the user');
    }
}

// Edit user
async function editUser(userId) {
    try {
        // Get user data
        const response = await fetch(`/admin/api/users/${userId}`);
        const result = await response.json();
        if (!result.success) {
            showAlert('danger', result.message);
            return;
        }

        // Fill form
        const form = document.getElementById('addUserForm');
        form.dataset.userId = userId;
        form.username.value = result.user.username;
        form.email.value = result.user.email;
        form.role.value = result.user.role;

        // Remove password field for editing
        const passwordGroup = form.querySelector('.password-group');
        if (passwordGroup) {
            passwordGroup.style.display = 'none';
        }

        // Update modal title
        document.getElementById('addUserModalLabel').textContent = 'Edit User';

        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('addUserModal'));
        modal.show();
    } catch (error) {
        console.error('Error editing user:', error);
        showAlert('danger', 'An error occurred while loading user data');
    }
}

// Reset form when modal is closed
document.getElementById('addUserModal').addEventListener('hidden.bs.modal', function () {
    const form = document.getElementById('addUserForm');
    form.reset();
    delete form.dataset.userId;
    document.getElementById('addUserModalLabel').textContent = 'Add New User';
    const passwordGroup = form.querySelector('.password-group');
    if (passwordGroup) {
        passwordGroup.style.display = 'block';
    }
});
