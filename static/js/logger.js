// Client-side logger
const Logger = {
    // Log levels
    levels: {
        DEBUG: 'debug',
        INFO: 'info',
        WARNING: 'warning',
        ERROR: 'error'
    },

    // Rate limiting configuration
    _rateLimit: {
        maxRequests: 10,
        timeWindow: 1000, // 1 second
        requests: [],
        queued: []
    },

    // Fallback configuration
    _fallback: {
        enabled: false,
        maxStoredLogs: 100,
        storageKey: 'pendingLogs',
        failureCount: 0,
        maxFailures: 3
    },

    // Initialize logger
    init() {
        this._setupFallback();
        this._processPendingLogs();
        this._setupHeartbeat();
        this._setupFormTracking();
        return this;
    },

    // Setup fallback mechanism
    _setupFallback() {
        try {
            const pendingLogs = localStorage.getItem(this._fallback.storageKey);
            if (pendingLogs) {
                const logs = JSON.parse(pendingLogs);
                if (logs.length > 0) {
                    this._processPendingLogs();
                }
            }
        } catch (e) {
            console.error('Failed to setup logger fallback:', e);
        }
    },

    // Process any pending logs
    _processPendingLogs() {
        try {
            const pendingLogs = JSON.parse(localStorage.getItem(this._fallback.storageKey) || '[]');
            if (pendingLogs.length > 0) {
                pendingLogs.forEach(log => {
                    this._sendToServer(log, 0, true);
                });
                localStorage.removeItem(this._fallback.storageKey);
            }
        } catch (e) {
            console.error('Failed to process pending logs:', e);
        }
    },

    // Setup heartbeat to check server availability
    _setupHeartbeat() {
        setInterval(() => {
            if (this._fallback.enabled) {
                this._checkServerAvailability();
            }
        }, 30000); // Check every 30 seconds
    },

    // Check if server is available
    _checkServerAvailability() {
        fetch('/api/health', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            if (response.ok) {
                this._fallback.enabled = false;
                this._fallback.failureCount = 0;
                this._processPendingLogs();
            }
        })
        .catch(() => {
            this._fallback.enabled = true;
        });
    },

    // Store log in fallback storage
    _storeFallbackLog(logData) {
        try {
            const pendingLogs = JSON.parse(localStorage.getItem(this._fallback.storageKey) || '[]');
            pendingLogs.push(logData);
            
            // Limit stored logs
            while (pendingLogs.length > this._fallback.maxStoredLogs) {
                pendingLogs.shift();
            }
            
            localStorage.setItem(this._fallback.storageKey, JSON.stringify(pendingLogs));
        } catch (e) {
            console.error('Failed to store log in fallback:', e);
        }
    },

    // Check if we should rate limit
    _shouldRateLimit() {
        const now = Date.now();
        this._rateLimit.requests = this._rateLimit.requests.filter(time => now - time < this._rateLimit.timeWindow);
        return this._rateLimit.requests.length >= this._rateLimit.maxRequests;
    },

    // Queue a log if rate limited
    _queueLog(logData) {
        this._rateLimit.queued.push({
            data: logData,
            timestamp: Date.now()
        });
        // Process queue after time window
        setTimeout(() => this._processQueue(), this._rateLimit.timeWindow);
    },

    // Process queued logs
    _processQueue() {
        const now = Date.now();
        if (!this._shouldRateLimit()) {
            const nextLog = this._rateLimit.queued.shift();
            if (nextLog) {
                this._sendToServer(nextLog.data);
            }
        }
    },

    // Send log to server with retry logic
    _sendToServer(logData, retryCount = 0, isRetry = false) {
        const maxRetries = 3;

        if (this._shouldRateLimit() && !isRetry) {
            this._queueLog(logData);
            return;
        }

        if (!isRetry) {
            this._rateLimit.requests.push(Date.now());
        }

        // Ensure required fields for the API endpoint
        const payload = {
            level: logData.level || 'INFO',
            message: logData.message || 'No message provided',
            context: logData
        };

        fetch('/api/client-logs', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(() => {
            this._fallback.failureCount = 0;
            this._fallback.enabled = false;
        })
        .catch(error => {
            console.error('Error sending log to server:', error);
            this._fallback.failureCount++;
            
            if (this._fallback.failureCount >= this._fallback.maxFailures) {
                this._fallback.enabled = true;
                this._storeFallbackLog(logData);
            } else if (retryCount < maxRetries) {
                setTimeout(() => {
                    this._sendToServer(logData, retryCount + 1, true);
                }, Math.pow(2, retryCount) * 1000);
            } else {
                this._storeFallbackLog(logData);
            }
        });
    },

    // Log a message with level and context
    log: function(level, message, context = {}) {
        if (!this.levels[level.toUpperCase()]) {
            level = this.levels.INFO;
        }

        const logData = {
            timestamp: new Date().toISOString(),
            level: level,
            message: message,
            url: window.location.href,
            context: context,
            sessionId: this._getSessionId(),
            userAgent: navigator.userAgent,
            screenSize: {
                width: window.innerWidth,
                height: window.innerHeight
            }
        };

        // Log to console for development
        this._logToConsole(level, message, context);

        // Send to server or use fallback
        if (this._fallback.enabled) {
            this._storeFallbackLog(logData);
        } else {
            this._sendToServer(logData);
        }
    },

    // Enhanced console logging
    _logToConsole(level, message, context) {
        const styles = {
            debug: 'color: #7f8c8d',
            info: 'color: #2ecc71',
            warning: 'color: #f1c40f',
            error: 'color: #e74c3c'
        };

        console.log(
            `%c[${level.toUpperCase()}] ${message}`,
            styles[level.toLowerCase()] || styles.info,
            context
        );
    },

    // Get or create session ID
    _getSessionId() {
        let sessionId = sessionStorage.getItem('loggerSessionId');
        if (!sessionId) {
            sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            sessionStorage.setItem('loggerSessionId', sessionId);
        }
        return sessionId;
    },

    // Convenience methods for different log levels
    debug: function(message, context = {}) {
        this.log(this.levels.DEBUG, message, context);
    },

    info: function(message, context = {}) {
        this.log(this.levels.INFO, message, context);
    },

    warning: function(message, context = {}) {
        this.log(this.levels.WARNING, message, context);
    },

    error: function(message, context = {}) {
        this.log(this.levels.ERROR, message, context);
    },

    // Authentication error handling
    _handleAuthError(error) {
        const authError = {
            type: 'AUTH_ERROR',
            message: error.message || 'Authentication failed',
            timestamp: new Date().toISOString(),
            url: window.location.href,
            details: error
        };
        this.error('Authentication error', authError);
        return authError;
    },

    // Form validation helper
    validateForm(form) {
        const formData = new FormData(form);
        const errors = [];
        
        // Basic email validation
        const email = formData.get('email');
        if (email) {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(email)) {
                errors.push({
                    field: 'email',
                    message: 'Please enter a valid email address'
                });
            }
        }

        // Password validation - removed length requirement
        const password = formData.get('password');
        if (!password || password.trim() === '') {
            errors.push({
                field: 'password',
                message: 'Password is required'
            });
        }

        return {
            isValid: errors.length === 0,
            errors
        };
    },

    // Enhanced form tracking
    _setupFormTracking() {
        document.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('form').forEach(form => {
                // Track form submissions with enhanced validation
                form.addEventListener('submit', (event) => {
                    const formData = {
                        formId: form.id || 'unnamed-form',
                        formAction: form.action,
                        formMethod: form.method,
                        formFields: Array.from(form.elements)
                            .filter(el => el.name)
                            .map(el => ({
                                name: el.name,
                                type: el.type,
                                valid: el.validity.valid,
                                errors: Object.keys(el.validity)
                                    .filter(key => key !== 'valid' && el.validity[key])
                            }))
                    };

                    this.info('Form submitted', formData);
                });

                // Clear validation errors on input
                form.querySelectorAll('input').forEach(input => {
                    input.addEventListener('input', () => {
                        input.classList.remove('is-invalid');
                        const feedback = input.nextElementSibling;
                        if (feedback && feedback.className === 'invalid-feedback') {
                            feedback.remove();
                        }
                    });
                });

                // Track form validation errors
                form.addEventListener('invalid', (event) => {
                    event.preventDefault();
                    this.warning('Form validation error', {
                        formId: form.id || 'unnamed-form',
                        fieldName: event.target.name,
                        fieldType: event.target.type,
                        validationMessage: event.target.validationMessage
                    });
                }, true);
            });
        });
    }
};

// Initialize logger
Logger.init();

// Add click tracking to all buttons and links with debouncing
document.addEventListener('DOMContentLoaded', function() {
    let lastClickTime = 0;
    const CLICK_THRESHOLD = 300; // milliseconds

    function shouldTrackClick() {
        const now = Date.now();
        if (now - lastClickTime > CLICK_THRESHOLD) {
            lastClickTime = now;
            return true;
        }
        return false;
    }

    // Track button clicks
    document.querySelectorAll('button').forEach(button => {
        button.addEventListener('click', function(event) {
            if (!shouldTrackClick()) return;

            Logger.info('Button clicked', {
                buttonId: this.id || 'unnamed-button',
                buttonText: this.textContent.trim(),
                buttonType: this.type || 'button',
                path: event.composedPath().map(el => el.tagName || 'window').join(' > ')
            });
        });
    });

    // Track link clicks
    document.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', function(event) {
            if (!shouldTrackClick()) return;

            Logger.info('Link clicked', {
                linkHref: this.href,
                linkText: this.textContent.trim(),
                path: event.composedPath().map(el => el.tagName || 'window').join(' > ')
            });
        });
    });

    // Track form submissions with validation
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(event) {
            const formData = {
                formId: this.id || 'unnamed-form',
                formAction: this.action,
                formMethod: this.method,
                formFields: Array.from(this.elements)
                    .filter(el => el.name)
                    .map(el => ({
                        name: el.name,
                        type: el.type,
                        valid: el.validity.valid,
                        errors: Object.keys(el.validity).filter(key => key !== 'valid' && el.validity[key])
                    }))
            };

            Logger.info('Form submitted', formData);
        });

        // Track form validation errors
        form.addEventListener('invalid', function(event) {
            event.preventDefault();
            Logger.warning('Form validation error', {
                formId: this.id || 'unnamed-form',
                fieldName: event.target.name,
                fieldType: event.target.type,
                validationMessage: event.target.validationMessage
            });
        }, true);
    });

    // Initialize form tracking
    Logger._setupFormTracking();

    // Add global error boundary
    window.addEventListener('error', function(event) {
        if (event.error) {
            Logger.error('Global error caught', {
                message: event.error.message,
                stack: event.error.stack,
                type: event.error.name,
                source: event.filename,
                line: event.lineno,
                column: event.colno
            });
        }
    });

    // Add authentication error handling
    document.addEventListener('submit', function(event) {
        const form = event.target;
        if (form.id === 'login-form' || form.action.includes('/login')) {
            event.preventDefault();
            
            const formData = new FormData(form);
            fetch(form.action, {
                method: form.method,
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(Object.fromEntries(formData))
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    window.location.href = data.redirect || '/';
                } else {
                    throw new Error(data.message || 'Login failed');
                }
            })
            .catch(error => {
                Logger._handleAuthError(error);
                // Display error to user
                const alertDiv = document.createElement('div');
                alertDiv.className = 'alert alert-danger';
                alertDiv.textContent = error.message || 'Login failed. Please try again.';
                form.insertBefore(alertDiv, form.firstChild);
            });
        }
    });
});
