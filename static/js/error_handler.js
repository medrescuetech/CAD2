// Error handler for CAD System
class ErrorHandler {
    constructor() {
        this.debug = false;
        this.init();
        
        // Global error handler
        window.onerror = (msg, url, lineNo, columnNo, error) => {
            this.handleError('Global Error', {
                message: msg,
                url: url,
                lineNo: lineNo,
                columnNo: columnNo,
                error: error
            });
            return false;
        };

        // Handle unhandled promise rejections
        window.addEventListener('unhandledrejection', (event) => {
            this.handleError('Unhandled Promise Rejection', {
                message: event.reason,
                promise: event.promise
            });
        });

        // Handle network errors
        window.addEventListener('error', (event) => {
            if (event.target && (event.target.tagName === 'IMG' || event.target.tagName === 'SCRIPT' || event.target.tagName === 'LINK')) {
                this.handleError('Resource Load Error', {
                    message: `Failed to load ${event.target.tagName.toLowerCase()}: ${event.target.src || event.target.href}`,
                    element: event.target.outerHTML
                });
            }
        }, true);
    }

    init() {
        try {
            // Get debug mode from meta tag
            const configMeta = document.querySelector('meta[name="app-config"]');
            if (configMeta) {
                const config = JSON.parse(configMeta.content);
                this.debug = config.debug;
                window.APP_CONFIG = config;
            }
        } catch (error) {
            console.error('Failed to initialize error handler:', error);
        }
    }

    async handleError(type, details) {
        try {
            const errorInfo = {
                type: type,
                timestamp: new Date().toISOString(),
                details: details,
                url: window.location.href,
                userAgent: navigator.userAgent
            };

            // Log to console in debug mode
            if (this.debug) {
                console.error('Error:', type, details);
            }

            // Show error to user
            const src = details.url ? ` [${details.url.split('/').pop()}:${details.lineNo}]` : '';
            if (typeof showAlert === 'function') {
                showAlert('error', (details.message || 'An error occurred') + src);
            } else {
                console.error('Error:', details.message || 'An error occurred');
            }

            // Get API key if available
            let apiKey = localStorage.getItem('apiKey');
            
            // Send error to server
            try {
                const response = await fetch('/api/client-logs', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...(apiKey && {'X-API-Key': apiKey})
                    },
                    body: JSON.stringify(errorInfo),
                    credentials: 'same-origin'  // Include cookies
                });

                if (response.status === 401 || response.status === 403) {
                    // Not logged in or unauthorized - do not store error locally
                    return;
                }

                if (!response.ok) {
                    throw new Error(`Server returned ${response.status}: ${response.statusText}`);
                }

                // Clear any stored errors if we successfully logged this one
                const storedErrors = JSON.parse(localStorage.getItem('pendingErrors') || '[]');
                if (storedErrors.length > 0) {
                    // Try to send stored errors
                    const promises = storedErrors.map(error => 
                        fetch('/api/client-logs', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                ...(apiKey && {'X-API-Key': apiKey})
                            },
                            body: JSON.stringify(error),
                            credentials: 'same-origin'
                        }).catch(e => {
                            console.error('Failed to send stored error:', e);
                            return null;
                        })
                    );

                    // Wait for all requests to complete
                    const results = await Promise.allSettled(promises);
                    
                    // Remove successfully sent errors
                    const failedErrors = storedErrors.filter((_, index) => 
                        results[index].status === 'rejected' || 
                        (results[index].status === 'fulfilled' && results[index].value === null)
                    );

                    if (failedErrors.length > 0) {
                        localStorage.setItem('pendingErrors', JSON.stringify(failedErrors));
                    } else {
                        localStorage.removeItem('pendingErrors');
                    }
                }
            } catch (e) {
                // If we can't send to server, store locally
                const storedErrors = JSON.parse(localStorage.getItem('pendingErrors') || '[]');
                storedErrors.push(errorInfo);
                localStorage.setItem('pendingErrors', JSON.stringify(storedErrors));
                console.error('Failed to send error to server:', e);
            }
        } catch (e) {
            // Last resort error logging
            console.error('Error in error handler:', e);
        }
    }
}

// Initialize error handler
window.errorHandler = new ErrorHandler();