document.getElementById('save-user-button').addEventListener('click', async function() {
    const form = document.getElementById('add-user-form');
    const formData = new FormData(form);
    
    try {
        const response = await fetch('/api/users', {
            method: 'POST',
            body: JSON.stringify(Object.fromEntries(formData)),
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const result = await response.json();
        if (result.success) {
            location.reload(); // Reload the page to see the new user
        } else {
            alert(result.message);
        }
    } catch (error) {
        console.error('Error adding user:', error);
        alert('Failed to add user');
    }
}); 