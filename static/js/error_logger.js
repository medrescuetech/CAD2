// Frontend Error Logging System
const ErrorLogger = {
    // Error types
    ERRORS: {
        NETWORK: 'NETWORK_ERROR',
        SERVER: 'SERVER_ERROR',
        CLIENT: 'CLIENT_ERROR',
        VALIDATION: 'VALIDATION_ERROR',
        UNKNOWN: 'UNKNOWN_ERROR'
    },

    // Error tracking for deduplication
    _errorTracker: {
        errors: new Map(),
        maxErrors: 10,
        timeWindow: 60000 // 1 minute
    },

    // Check if error is duplicate
    _isDuplicate(errorData) {
        const now = Date.now();
        const key = `${errorData.type}:${errorData.message}`;
        const existing = this._errorTracker.errors.get(key);

        if (existing) {
            if (now - existing.timestamp < this._errorTracker.timeWindow) {
                existing.count++;
                existing.timestamp = now;
                return true;
            }
        }

        // Clean old entries
        if (this._errorTracker.errors.size >= this._errorTracker.maxErrors) {
            const oldestKey = Array.from(this._errorTracker.errors.entries())
                .sort(([, a], [, b]) => a.timestamp - b.timestamp)[0][0];
            this._errorTracker.errors.delete(oldestKey);
        }

        this._errorTracker.errors.set(key, {
            timestamp: now,
            count: 1
        });

        return false;
    },

    // Enhanced error logging with categorization
    logError: function(errorType, errorDetails) {
        const logData = {
            type: errorType,
            ...errorDetails,
            userAgent: navigator.userAgent,
            timestamp: new Date().toISOString(),
            url: window.location.href,
            online: navigator.onLine,
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight
            },
            performance: this._getPerformanceMetrics()
        };

        // Check for duplicates
        if (this._isDuplicate(logData)) {
            return;
        }

        // Log to console with enhanced formatting
        console.error(
            `[${errorType}] ${errorDetails.message || 'Error occurred'}`,
            {
                details: errorDetails,
                timestamp: logData.timestamp,
                url: logData.url
            }
        );

        // Send to backend if online
        if (navigator.onLine) {
            this._sendToServer(logData);
        } else {
            this._storeOffline(logData);
        }
    },

    // Get performance metrics
    _getPerformanceMetrics() {
        if (!window.performance) return null;

        const timing = performance.timing;
        return {
            loadTime: timing.loadEventEnd - timing.navigationStart,
            domReady: timing.domContentLoadedEventEnd - timing.navigationStart,
            firstPaint: performance.getEntriesByType('paint')[0]?.startTime,
            memory: performance.memory ? {
                usedJSHeapSize: performance.memory.usedJSHeapSize,
                totalJSHeapSize: performance.memory.totalJSHeapSize
            } : null
        };
    },

    // Enhanced server communication with retry
    _sendToServer: function(logData, retryCount = 0) {
        const maxRetries = 3;

        fetch('/api/client-logs', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                type: logData.type,
                level: 'error',
                message: logData.message || 'Error occurred',
                context: logData,
                userAgent: navigator.userAgent,
                url: window.location.href,
                timestamp: new Date().toISOString()
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .catch(err => {
            console.error('Failed to send error to server:', err);
            if (retryCount < maxRetries) {
                setTimeout(() => {
                    this._sendToServer(logData, retryCount + 1);
                }, Math.pow(2, retryCount) * 1000);
            } else {
                this._storeOffline(logData);
            }
        });
    },

    // Enhanced offline storage
    _storeOffline: function(logData) {
        try {
            const offlineErrors = JSON.parse(localStorage.getItem('offlineErrors') || '[]');
            offlineErrors.push(logData);
            
            // Limit stored errors
            while (offlineErrors.length > 50) {
                offlineErrors.shift();
            }
            
            localStorage.setItem('offlineErrors', JSON.stringify(offlineErrors));
        } catch (e) {
            console.error('Failed to store error offline:', e);
        }
    },

    // Log user notifications with priority
    logNotification: function(type, message, level = 'info', priority = 'normal') {
        const logData = {
            type: this.ERRORS.UNKNOWN,
            notificationType: type,
            message: message,
            level: level,
            priority: priority,
            timestamp: new Date().toISOString(),
            url: window.location.href
        };

        // Log based on priority
        if (priority === 'high' || navigator.onLine) {
            this._sendToServer(logData);
        } else {
            this._storeOffline(logData);
        }

        // Console logging with color coding
        const styles = {
            error: 'background: #ff0000; color: white; padding: 2px;',
            warning: 'background: #ffaa00; color: white; padding: 2px;',
            info: 'background: #00aa00; color: white; padding: 2px;'
        };

        console.log(
            `%c${level.toUpperCase()}%c [${type}] ${message}`,
            styles[level] || styles.info,
            'color: inherit'
        );
    }
};

// Network status monitoring with reconnection handling
let reconnectionAttempts = 0;
const maxReconnectionAttempts = 5;

window.addEventListener('online', function() {
    reconnectionAttempts = 0;
    ErrorLogger.logNotification('Network', 'Connection restored', 'info', 'high');
    
    // Send stored offline errors
    try {
        const offlineErrors = JSON.parse(localStorage.getItem('offlineErrors') || '[]');
        if (offlineErrors.length > 0) {
            offlineErrors.forEach(error => {
                ErrorLogger.logError(error.type, error);
            });
            localStorage.removeItem('offlineErrors');
        }
    } catch (e) {
        console.error('Failed to process offline errors:', e);
    }
});

window.addEventListener('offline', function() {
    ErrorLogger.logError(ErrorLogger.ERRORS.NETWORK, {
        message: 'Lost network connection',
        timestamp: new Date().toISOString(),
        reconnectionAttempts
    });
});

// Enhanced global error handler with source mapping support
window.onerror = function(msg, url, lineNo, columnNo, error) {
    ErrorLogger.logError(ErrorLogger.ERRORS.UNKNOWN, {
        message: msg,
        sourceUrl: url,
        lineNumber: lineNo,
        columnNumber: columnNo,
        stack: error?.stack,
        errorName: error?.name,
        errorMessage: error?.message
    });
    return false;
};

// Enhanced promise rejection handler
window.addEventListener('unhandledrejection', function(event) {
    ErrorLogger.logError(ErrorLogger.ERRORS.UNKNOWN, {
        message: event.reason?.message || 'Unhandled Promise Rejection',
        stack: event.reason?.stack,
        reason: event.reason,
        promise: event.promise
    });
});

// Enhanced resource error tracking
window.addEventListener('error', function(event) {
    if (event.target instanceof HTMLElement) {
        if (['IMG', 'SCRIPT', 'LINK', 'AUDIO', 'VIDEO'].includes(event.target.tagName)) {
            ErrorLogger.logError(ErrorLogger.ERRORS.UNKNOWN, {
                element: event.target.tagName,
                source: event.target.src || event.target.href,
                id: event.target.id,
                className: event.target.className
            });
        }
    }
}, true);

// Enhanced AJAX error handling with detailed information
$(document).ajaxError(function(event, jqXHR, settings, error) {
    ErrorLogger.logError(ErrorLogger.ERRORS.UNKNOWN, {
        status: jqXHR.status,
        statusText: jqXHR.statusText,
        responseText: jqXHR.responseText,
        url: settings.url,
        type: settings.type,
        data: settings.data,
        error: error
    });
});

// Enhanced fetch error handling with request details
const originalFetch = window.fetch;
window.fetch = function(...args) {
    const startTime = performance.now();
    
    return originalFetch.apply(this, args)
        .then(response => {
            const duration = performance.now() - startTime;
            
            if (!response.ok) {
                ErrorLogger.logError(ErrorLogger.ERRORS.UNKNOWN, {
                    status: response.status,
                    statusText: response.statusText,
                    url: args[0],
                    options: args[1],
                    duration,
                    headers: Object.fromEntries(response.headers.entries())
                });
            }
            return response;
        })
        .catch(error => {
            const duration = performance.now() - startTime;
            
            ErrorLogger.logError(ErrorLogger.ERRORS.UNKNOWN, {
                message: error.message,
                url: args[0],
                options: args[1],
                stack: error.stack,
                duration
            });
            throw error;
        });
};
