// Common functions shared across pages

// Get application base path
const getBasePath = () => {
    const scriptElement = document.querySelector('script[src*="/static/js/"]');
    if (scriptElement) {
        const src = scriptElement.getAttribute('src');
        return src.split('/static/')[0] || '';
    }
    return '';
};

// URL helper function
function url_for(path) {
    // Get the base URL from the app config if available
    const appConfig = document.getElementById('app-config');
    if (appConfig) {
        const config = JSON.parse(appConfig.textContent);
        if (config.routes && config.routes[path]) {
            return config.routes[path];
        }
    }

    // Fallback to manual URL construction with base path
    path = path.replace(/^\/*/, ''); // Remove leading slashes
    const basePath = getBasePath();
    return `${window.location.origin}${basePath}/${path}`;
}

// WebSocket Manager
const WebSocketManager = {
    socket: null,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    reconnectDelay: 5000,
    messageQueue: [],
    listeners: new Map(),
    
    init: function() {
        this.connect();
        this._setupHeartbeat();
    },
    
    _setupHeartbeat: function() {
        setInterval(() => {
            if (this.socket && this.socket.connected) {
                this.socket.emit('ping');
            }
        }, 30000);
    },
    
    connect: function() {
        try {
            this.socket = io({
                path: '/socket.io',
                transports: ['websocket', 'polling'],
                reconnection: true,
                reconnectionAttempts: this.maxReconnectAttempts,
                reconnectionDelay: this.reconnectDelay,
                timeout: 10000
            });
            
            this._setupEventHandlers();
        } catch (error) {
            console.error('Error creating Socket.IO connection:', error);
            Utils.showToast('Failed to create connection', 'danger');
        }
    },
    
    _setupEventHandlers: function() {
        this.socket.on('connect', () => {
            console.log('Socket.IO connected');
            this.reconnectAttempts = 0;
            Utils.showToast('Connected to server', 'success');
            this._processMessageQueue();
            this.emit('connection_status', { status: 'connected' });
        });
        
        this.socket.on('disconnect', () => {
            console.log('Socket.IO disconnected');
            Utils.showToast('Disconnected from server', 'warning');
            this.emit('connection_status', { status: 'disconnected' });
        });
        
        this.socket.on('connect_error', (error) => {
            console.error('Socket.IO connection error:', error);
            Utils.showToast('Connection error', 'danger');
            this.emit('error', { message: 'Connection error' });
            
            if (++this.reconnectAttempts >= this.maxReconnectAttempts) {
                Utils.showToast('Unable to connect to server. Please refresh the page.', 'danger');
            }
        });
        
        this.socket.on('pong', () => {
            this.lastPong = Date.now();
        });
        
        ['incident_updated', 'unit_updated', 'log_updated'].forEach(type => {
            this.socket.on(type, (data) => this.handleMessage({ type, data }));
        });
    },
    
    _processMessageQueue: function() {
        while (this.messageQueue.length > 0) {
            const { type, data } = this.messageQueue.shift();
            this.emit(type, data);
        }
    },
    
    handleMessage: function(data) {
        const listeners = this.listeners.get(data.type) || [];
        listeners.forEach(callback => {
            try {
                callback(data);
            } catch (error) {
                console.error('Error in message handler:', error);
            }
        });
    },
    
    on: function(type, callback) {
        if (!this.listeners.has(type)) {
            this.listeners.set(type, []);
        }
        this.listeners.get(type).push(callback);
        
        // Also register with Socket.IO if it's a known event type
        if (['incident_updated', 'unit_updated', 'log_updated'].includes(type)) {
            this.socket.on(type, callback);
        }
    },
    
    off: function(type, callback) {
        if (this.listeners.has(type)) {
            const listeners = this.listeners.get(type);
            const index = listeners.indexOf(callback);
            if (index !== -1) {
                listeners.splice(index, 1);
            }
            // Also unregister from Socket.IO
            this.socket.off(type, callback);
        }
    },
    
    emit: function(type, data) {
        if (this.socket && this.socket.connected) {
            this.socket.emit(type, data);
        } else {
            this.messageQueue.push({ type, data });
        }
    },
    
    joinRoom: function(room) {
        this.emit('join', { room });
    },
    
    leaveRoom: function(room) {
        this.emit('leave', { room });
    }
};

// Window management helper
function openWindow(url, title, options = {}) {
    // Ensure URL is absolute or properly prefixed with base path
    const fullUrl = url.startsWith('http') ? url : url_for(url);
    const defaultOptions = {
        width: 800,
        height: 600,
        location: 'no',
        menubar: 'no',
        toolbar: 'no',
        status: 'no',
        scrollbars: 'yes',
        resizable: 'yes'
    };

    const windowOptions = { ...defaultOptions, ...options };
    const optionsString = Object.entries(windowOptions)
        .map(([key, value]) => `${key}=${value}`)
        .join(',');

    return window.open(fullUrl, title, optionsString);
}

// Show incident in a new tab
function viewIncident(id) {
    window.open(url_for(`incidents/${id}`), '_blank');
}

// Show medical dialog as a popup
function showMedicalDialog(incidentId) {
    return openWindow(
        `incidents/${incidentId}/medical`,
        'Medical Protocol',
        {
            width: 1000,
            height: 800
        }
    );
}

// Show unit manager in a new window
function showUnitManager() {
    return openWindow(
        'units',
        'Unit Manager',
        {
            width: 1000,
            height: 800
        }
    );
}

// Show new incident form in a new tab
function showNewIncident() {
    window.open(url_for('incidents/new'), '_blank');
}

// Show daily log in a new window
function showDailyLog() {
    return openWindow(
        'daily_log',
        'Daily Log',
        {
            width: 1200,
            height: 800
        }
    );
}

// API endpoints with proper URL construction
const API_ENDPOINTS = {
    incidents: url_for('api/incidents'),
    units: url_for('api/units'),
    logs: url_for('api/logs')
};

// Shared utilities for CAD System
const AppUrls = {
    base: getBasePath(),
    
    // Generate URL with proper prefix
    url: function(path) {
        return url_for(path);
    },
    
    // API URLs
    api: {
        units: {
            status: (unitId) => this.url(`api/units/${unitId}/status`),
            list: () => this.url('api/units')
        },
        incidents: {
            create: () => this.url('api/incidents/create'),
            update: (id) => this.url(`api/incidents/${id}`),
            close: (id) => this.url(`api/incidents/${id}/close`),
            report: (id) => this.url(`api/incidents/${id}/report`)
        },
        dailyLog: {
            create: () => this.url('api/daily_log'),
            update: (id) => this.url(`api/daily_log/${id}`),
            delete: (id) => this.url(`api/daily_log/${id}`),
            types: () => this.url('api/daily_log/types'),
            export: (date) => this.url(`api/daily_log/export?date=${date}`)
        },
        pickupPoints: {
            list: () => this.url('api/pickup-points'),
            create: () => this.url('api/pickup-points'),
            update: (id) => this.url(`api/pickup-points/${id}`),
            delete: (id) => this.url(`api/pickup-points/${id}`)
        }
    }
};

// Utility functions
const Utils = {
    formatTimestamp(timestamp) {
        return new Date(timestamp).toLocaleString();
    },

    showToast(message, type = 'info') {
        showAlert(type, message);
    },

    async apiRequest(url, options = {}) {
        try {
            const defaultOptions = {
                headers: {
                    'Content-Type': 'application/json'
                }
            };

            const response = await fetch(url, { ...defaultOptions, ...options });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'API request failed');
            }

            return data;
        } catch (error) {
            console.error('API Request Error:', error);
            throw error;
        }
    }
};

// Initialize components when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    try {
        // Initialize app configuration
        const configMeta = document.querySelector('meta[name="app-config"]');
        if (configMeta) {
            window.APP_CONFIG = JSON.parse(configMeta.content);
        }
    } catch (error) {
        console.error('Failed to initialize app configuration:', error);
    }
    WebSocketManager.init();
});
