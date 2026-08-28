// API key management functions

async function generateApiKey() {
    try {
        const form = document.getElementById('addApiKeyForm');
        const description = form.keyDescription.value;
        
        // Get selected permissions
        const permissions = [];
        form.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
            permissions.push(parseInt(checkbox.value));
        });
        
        const response = await fetch('/api_keys/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                description,
                permissions
            })
        });
        
        const result = await response.json();
        if (result.success) {
            // Close add modal
            const addModal = bootstrap.Modal.getInstance(document.getElementById('addApiKeyModal'));
            addModal.hide();
            
            // Show key in display modal
            document.getElementById('apiKeyDisplay').textContent = result.key;
            const displayModal = new bootstrap.Modal(document.getElementById('displayApiKeyModal'));
            displayModal.show();
            
            // Refresh page after modal is closed
            document.getElementById('displayApiKeyModal').addEventListener('hidden.bs.modal', () => {
                location.reload();
            });
        } else {
            showAlert('danger', result.message);
        }
    } catch (error) {
        console.error('Error generating API key:', error);
        showAlert('danger', 'An error occurred while generating the API key');
    }
}

async function toggleApiKey(keyId, activate) {
    try {
        const response = await fetch(`/api_keys/${keyId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                active: activate
            })
        });
        
        const result = await response.json();
        if (result.success) {
            location.reload();
        } else {
            showAlert('danger', result.message);
        }
    } catch (error) {
        console.error('Error toggling API key:', error);
        showAlert('danger', 'An error occurred while updating the API key');
    }
}

async function deleteApiKey(keyId) {
    try {
        if (!confirm('Are you sure you want to delete this API key? This action cannot be undone.')) {
            return;
        }
        
        const response = await fetch(`/api_keys/${keyId}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        if (result.success) {
            location.reload();
        } else {
            showAlert('danger', result.message);
        }
    } catch (error) {
        console.error('Error deleting API key:', error);
        showAlert('danger', 'An error occurred while deleting the API key');
    }
}

function copyApiKey() {
    const keyElement = document.getElementById('apiKeyDisplay');
    const key = keyElement.textContent;
    
    navigator.clipboard.writeText(key).then(() => {
        showAlert('success', 'API key copied to clipboard');
    }).catch(error => {
        console.error('Error copying API key:', error);
        showAlert('danger', 'Failed to copy API key to clipboard');
    });
}
