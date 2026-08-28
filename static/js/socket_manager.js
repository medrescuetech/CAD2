// Socket.IO Manager for CAD System
class SocketManager {
    constructor() {
        this.socket = null;
        this.connected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.handlers = new Map();
        
        // Bind methods
        this.connect = this.connect.bind(this);
        this.disconnect = this.disconnect.bind(this);
        this.emit = this.emit.bind(this);
        this.on = this.on.bind(this);
        this.off = this.off.bind(this);
        
        // Initialize
        this.initializeEventListeners();
        this.connect();
    }
    
    initializeEventListeners() {
        // Global error handlers
        window.addEventListener('error', (event) => {
            console.error('Global error:', event.error);
            this.emit('error', { message: event.error.message });
        });
        
        window.addEventListener('unhandledrejection', (event) => {
            console.error('Unhandled rejection:', event.reason);
            this.emit('error', { message: event.reason.message });
        });
    }
    
    connect() {
        if (this.socket) {
            return;
        }
        
        // Extract the protocol and host from the current URL
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const socketUrl = `${window.location.protocol}//${host}`;
        
        console.log('Connecting to Socket.IO at:', socketUrl);
        
        // Initialize Socket.IO with configuration
        this.socket = io(socketUrl, {
            reconnection: true,
            reconnectionAttempts: this.maxReconnectAttempts,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 30000,
            timeout: 20000,
            transports: ['websocket', 'polling'] // Try WebSocket first, then fall back to polling
        });
        
        // Connection events
        this.socket.on('connect', () => {
            console.log('Socket.IO connected');
            this.connected = true;
            this.reconnectAttempts = 0;
            this.emit('connection_status', { status: 'connected' });
            window.dispatchEvent(new Event('socket_initialized'));
        });
        
        this.socket.on('disconnect', () => {
            console.log('Socket.IO disconnected');
            this.connected = false;
            this.emit('connection_status', { status: 'disconnected' });
        });
        
        this.socket.on('connect_error', (error) => {
            console.error('Socket.IO error:', error);
            this.emit('connection_status', { status: 'error', error: error.message });
            showAlert('danger', 'Lost connection to server. Attempting to reconnect...');
        });
        
        this.socket.on('reconnect', (attemptNumber) => {
            console.log('Socket reconnected after', attemptNumber, 'attempts');
            showAlert('success', 'Reconnected to server');
        });
        
        // Authentication events
        this.socket.on('connect_success', () => {
            console.log('Authentication successful');
            document.dispatchEvent(new CustomEvent('socketAuthenticated'));
        });
        
        // Error events
        this.socket.on('error', (data) => {
            console.error('Server error:', data);
            document.dispatchEvent(new CustomEvent('serverError', { detail: data }));
            showAlert('danger', data.message || 'An error occurred');
        });
        
        // Incident events
        this.socket.on('incident_created', (data) => {
            document.dispatchEvent(new CustomEvent('incidentCreated', { detail: data }));
            this.handleIncidentUpdate(data);
        });
        
        this.socket.on('incident_updated', (data) => {
            document.dispatchEvent(new CustomEvent('incidentUpdated', { detail: data }));
            this.handleIncidentUpdate(data);
        });
        
        this.socket.on('incident_status_changed', (data) => {
            document.dispatchEvent(new CustomEvent('incidentStatusChanged', { detail: data }));
            this.handleIncidentUpdate(data);
        });
        
        this.socket.on('incident_unit_assigned', (data) => {
            document.dispatchEvent(new CustomEvent('incidentUnitAssigned', { detail: data }));
            this.handleIncidentUpdate(data);
        });
        
        this.socket.on('incident_unit_cleared', (data) => {
            document.dispatchEvent(new CustomEvent('incidentUnitCleared', { detail: data }));
            this.handleIncidentUpdate(data);
        });
        
        this.socket.on('incident_closed', (data) => {
            document.dispatchEvent(new CustomEvent('incidentClosed', { detail: data }));
            this.handleIncidentUpdate(data);
        });
        
        this.socket.on('incident_log_added', (data) => {
            document.dispatchEvent(new CustomEvent('incidentLogAdded', { detail: data }));
            this.handleIncidentUpdate(data);
        });
        
        // Unit events
        this.socket.on('unit_status_changed', (data) => {
            document.dispatchEvent(new CustomEvent('unitStatusChanged', { detail: data }));
            this.handleUnitUpdate(data);
        });
        
        this.socket.on('unit_location_updated', (data) => {
            document.dispatchEvent(new CustomEvent('unitLocationUpdated', { detail: data }));
            this.handleUnitUpdate(data);
        });
    }
    
    handleIncidentUpdate(data) {
        if (window.location.pathname === '/') {
            // Refresh dashboard if on home page
            if (typeof refreshDashboard === 'function') {
                refreshDashboard();
            }
        } else if (window.location.pathname.startsWith('/incidents/')) {
            // Refresh incident page if viewing the updated incident
            const currentIncidentId = window.location.pathname.split('/').pop();
            if (data.id === currentIncidentId || data.incident_id === currentIncidentId) {
                location.reload();
            }
        }
    }
    
    handleUnitUpdate(data) {
        if (window.location.pathname === '/' || window.location.pathname === '/units') {
            if (typeof refreshDashboard === 'function') {
                refreshDashboard();
            }
        }
    }
    
    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
            this.connected = false;
        }
    }
    
    emit(event, data) {
        if (this.connected && this.socket) {
            this.socket.emit(event, data);
        } else {
            console.warn('Socket not connected, message not sent:', event, data);
        }
    }
    
    on(event, callback) {
        if (this.socket) {
            this.socket.on(event, callback);
        }
        this.handlers.set(event, callback);
    }
    
    off(event) {
        if (this.socket) {
            this.socket.off(event);
        }
        this.handlers.delete(event);
    }
}

// Create global instance
window.socketManager = new SocketManager();
