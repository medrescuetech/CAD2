document.addEventListener('DOMContentLoaded', function() {
    const smtpForm = document.getElementById('smtpForm');
    const testButton = document.getElementById('testConnection');

    // Load SMTP settings
    fetch('/api/smtp/settings', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Logger.info('SMTP settings loaded successfully');
            Utils.showToast('Settings loaded successfully', 'success');
        } else {
            Logger.error('Error loading SMTP settings', { error: data.error });
            Utils.showToast(data.error || 'Error loading settings', 'danger');
        }
    })
    .catch(error => {
        Logger.error('Error loading SMTP settings', { error: error.message });
        Utils.showToast('Error loading settings', 'danger');
    });

    // Handle form submission
    smtpForm.addEventListener('submit', function(event) {
        event.preventDefault();
        
        const formData = new FormData(smtpForm);
        const data = {};
        formData.forEach((value, key) => data[key] = value);

        Logger.info('Saving SMTP settings');

        fetch('/api/smtp/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                Logger.info('SMTP settings saved successfully');
                Utils.showToast('Settings saved successfully', 'success');
            } else {
                Logger.error('Error saving SMTP settings', { error: data.error });
                Utils.showToast(data.error || 'Error saving settings', 'danger');
            }
        })
        .catch(error => {
            Logger.error('Error saving SMTP settings', { error: error.message });
            Utils.showToast('Error saving settings', 'danger');
        });
    });

    // Test SMTP connection
    testButton.addEventListener('click', function() {
        const testEmail = document.getElementById('testEmail').value;
        
        if (!testEmail) {
            Utils.showToast('Please enter a test recipient email address', 'warning');
            return;
        }
        
        Logger.info('Testing SMTP connection');
        testButton.disabled = true;
        testButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Testing...';
        
        fetch('/api/smtp/test', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ recipient: testEmail })
        })
        .then(response => response.json())
        .then(data => {
            testButton.disabled = false;
            testButton.innerHTML = 'Test Connection';
            
            if (data.success) {
                Logger.info('SMTP connection test successful');
                Utils.showToast('Test email sent successfully to ' + testEmail, 'success');
            } else {
                Logger.error('SMTP connection test failed', { error: data.error });
                Utils.showToast(data.error || 'Connection test failed', 'danger');
            }
        })
        .catch(error => {
            testButton.disabled = false;
            testButton.innerHTML = 'Test Connection';
            
            Logger.error('Error testing SMTP connection', { error: error.message });
            Utils.showToast('Error testing connection', 'danger');
        });
    });
}); 