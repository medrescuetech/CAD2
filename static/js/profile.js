// Profile management JavaScript

// Initialize profile page
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners and initialize components here
});

// Add WebSocket integration
const socket = io();

// Add error handling
const handleError = (error) => {
    console.error(error);
    showAlert('danger', error.message || 'An error occurred');
    throw error;
};

// Add loading states
const setLoading = (isLoading) => {
    document.body.classList.toggle('loading', isLoading);
};

// Add success/error messages
const showAlert = (type, message) => {
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    document.body.appendChild(alert);
    setTimeout(() => alert.remove(), 3000);
};

// Add form validation
const validateForm = (form) => {
    const inputs = form.querySelectorAll('input');
    let isValid = true;
    inputs.forEach(input => {
        if (!input.checkValidity()) {
            isValid = false;
            input.classList.add('is-invalid');
        } else {
            input.classList.remove('is-invalid');
        }
    });
    return isValid;
};

// Add dark mode support
const toggleDarkMode = () => {
    document.body.classList.toggle('dark-mode');
};

// Add accessibility improvements
const improveAccessibility = () => {
    const buttons = document.querySelectorAll('button');
    buttons.forEach(button => {
        button.setAttribute('aria-label', button.textContent);
    });
};

// Add activity log
const loadActivityLog = () => {
    fetch('/api/activity-log')
        .then(response => response.json())
        .then(data => {
            const logContainer = document.getElementById('activity-log');
            logContainer.innerHTML = data.logs.map(log => `
                <div class="log-entry">
                    <div class="log-timestamp">
                        ${new Date(log.created_at).toLocaleString()}
                    </div>
                    <div class="log-message">
                        ${log.message}
                    </div>
                </div>
            `).join('');
        })
        .catch(handleError);
};

// Add API key management
const manageApiKeys = () => {
    fetch('/api/api-keys')
        .then(response => response.json())
        .then(data => {
            const apiKeyContainer = document.getElementById('api-keys');
            apiKeyContainer.innerHTML = data.keys.map(key => `
                <div class="api-key">
                    <div class="api-key-name">
                        ${key.name}
                    </div>
                    <div class="api-key-value">
                        ${key.value}
                    </div>
                </div>
            `).join('');
        })
        .catch(handleError);
};

// Initialize profile page
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners and initialize components here
    improveAccessibility();
    loadActivityLog();
    manageApiKeys();
});
