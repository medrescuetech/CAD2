// Socket.io connection management
const socket = io({
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: 5
});

// Connection event handlers
socket.on('connect', () => {
    console.log('Connected to server');
    notifyUser('success', 'Connected to server');
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
    notifyUser('warning', 'Disconnected from server. Attempting to reconnect...');
});

socket.on('error', (error) => {
    console.error('Socket error:', error);
    notifyUser('error', `Socket error: ${error.message || 'Unknown error'}`);
});

socket.on('reconnect', (attemptNumber) => {
    console.log(`Reconnected after ${attemptNumber} attempts`);
    notifyUser('success', 'Reconnected to server');
});

socket.on('reconnect_error', (error) => {
    console.error('Reconnection error:', error);
    notifyUser('error', 'Failed to reconnect to server');
});

// Generic error handler for all events
socket.onAny((eventName, ...args) => {
    if (args[0] && args[0].error) {
        console.error(`Error in event ${eventName}:`, args[0].error);
        notifyUser('error', args[0].error.message || 'An error occurred');
    }
});

// Wrapper function for emitting events with Promise interface
function emitEvent(eventName, data, timeout = 5000) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            reject(new Error(`Event ${eventName} timed out after ${timeout}ms`));
        }, timeout);

        socket.emit(eventName, data, (response) => {
            clearTimeout(timer);
            if (response && response.error) {
                reject(new Error(response.error));
            } else {
                resolve(response);
            }
        });
    });
}

// Event handlers for incidents
const incidentHandlers = {
    async createIncident(data) {
        try {
            const response = await emitEvent('create_incident', data);
            notifyUser('success', 'Incident created successfully');
            return response;
        } catch (error) {
            notifyUser('error', `Failed to create incident: ${error.message}`);
            throw error;
        }
    },

    async updateIncident(data) {
        try {
            const response = await emitEvent('update_incident', data);
            notifyUser('success', 'Incident updated successfully');
            return response;
        } catch (error) {
            notifyUser('error', `Failed to update incident: ${error.message}`);
            throw error;
        }
    },

    async closeIncident(data) {
        try {
            const response = await emitEvent('close_incident', data);
            notifyUser('success', 'Incident closed successfully');
            return response;
        } catch (error) {
            notifyUser('error', `Failed to close incident: ${error.message}`);
            throw error;
        }
    }
};

// Event handlers for units
const unitHandlers = {
    async updateUnitStatus(data) {
        try {
            const response = await emitEvent('update_unit_status', data);
            notifyUser('success', 'Unit status updated successfully');
            return response;
        } catch (error) {
            notifyUser('error', `Failed to update unit status: ${error.message}`);
            throw error;
        }
    },

    async updateUnitLocation(data) {
        try {
            const response = await emitEvent('update_unit_location', data);
            notifyUser('success', 'Unit location updated successfully');
            return response;
        } catch (error) {
            notifyUser('error', `Failed to update unit location: ${error.message}`);
            throw error;
        }
    }
};

// Event handlers for admin functions
const adminHandlers = {
    async getSystemStats() {
        try {
            const response = await emitEvent('get_system_stats');
            return response;
        } catch (error) {
            notifyUser('error', `Failed to get system stats: ${error.message}`);
            throw error;
        }
    },

    async updateSystemSettings(data) {
        try {
            const response = await emitEvent('update_system_settings', data);
            notifyUser('success', 'System settings updated successfully');
            return response;
        } catch (error) {
            notifyUser('error', `Failed to update system settings: ${error.message}`);
            throw error;
        }
    }
};

// Helper function to show notifications to user
function notifyUser(type, message) {
    // Check if Toastify is available
    if (typeof Toastify === 'function') {
        Toastify({
            text: message,
            duration: 3000,
            gravity: "top",
            position: 'right',
            backgroundColor: type === 'success' ? '#4caf50' : 
                           type === 'error' ? '#f44336' : 
                           type === 'warning' ? '#ff9800' : '#2196f3'
        }).showToast();
    } else {
        // Fallback to console
        console.log(`${type.toUpperCase()}: ${message}`);
    }
}

// Export handlers for use in other modules
export {
    socket,
    emitEvent,
    incidentHandlers,
    unitHandlers,
    adminHandlers
};
