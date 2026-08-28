// WebSocket connection handling
let socket;
let reconnectAttempts = 0;
let heartbeatTimer = null;

function initWebSocket() {
    // Create WebSocket connection with automatic reconnection
    socket = io({
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 10000,
        timeout: 20000
    });

    // Connection opened
    socket.on('connect', function() {
        console.log('[WS] Connected to WebSocket server');
        reconnectAttempts = 0;
        // Ask for system status after connect
        socket.emit('get_system_status');
        // Start heartbeat every 25s (match server heartbeat interval)
        if (heartbeatTimer) clearInterval(heartbeatTimer);
        heartbeatTimer = setInterval(() => {
            try {
                socket.emit('heartbeat');
            } catch (e) {
                console.warn('[WS] Heartbeat emit failed:', e);
            }
        }, 25000);
    });

    // Connection closed
    socket.on('disconnect', function(reason) {
        console.log('[WS] Disconnected from WebSocket server:', reason);
        if (heartbeatTimer) {
            clearInterval(heartbeatTimer);
            heartbeatTimer = null;
        }
    });

    // Reconnect handling
    socket.on('reconnect_attempt', function() {
        reconnectAttempts += 1;
        console.log(`[WS] Reconnect attempt #${reconnectAttempts}`);
    });
    socket.on('reconnect', function(attemptNumber) {
        console.log('[WS] Reconnected after attempts:', attemptNumber);
        // Notify server we reconnected
        socket.emit('reconnect', { old_client_id: window.__lastClientId || null });
    });

    // Store connect_success info
    socket.on('connect_success', function(payload) {
        console.log('[WS] Connect success', payload);
        window.__lastClientId = payload.client_id;
        // Optionally update UI with user/permissions
        document.body.dataset.wsConnected = 'true';
    });

    // Heartbeat pong
    socket.on('heartbeat', function(data) {
        // server timestamp available
        // console.debug('[WS] Heartbeat:', data);
    });

    // System status
    socket.on('system_status', function(status) {
        console.log('[WS] System status:', status);
    });

    // Error and auth handling
    socket.on('auth_error', function(err) {
        console.warn('[WS] Auth error:', err);
    });
    socket.on('rate_limit_exceeded', function(info) {
        console.warn('[WS] Rate limit exceeded:', info);
    });
    socket.on('error', function(err) {
        console.error('[WS] Error:', err);
    });

    // Incident events
    socket.on('incident_created', function(incident) {
        console.log('[WS] Incident created', incident);
        updateIncident(incident);
    });
    socket.on('incident_updated', function(incident) {
        console.log('[WS] Incident updated', incident);
        updateIncident(incident);
    });

    // Unit events
    socket.on('unit_created', function(unit) {
        console.log('[WS] Unit created', unit);
        updateUnit(unit);
    });
    socket.on('unit_status_updated', function(update) {
        console.log('[WS] Unit status updated', update);
        updateUnit(update);
    });
    socket.on('unit_location_updated', function(update) {
        console.log('[WS] Unit location updated', update);
        updateUnit(update);
    });

    // Backward-compatible generic updates
    socket.on('update', function(data) {
        console.log('[WS] Received generic update:', data);
        handleUpdate(data);
    });
}

function handleUpdate(data) {
    // Handle different types of updates
    switch(data.type) {
        case 'incident':
            updateIncident(data.data);
            break;
        case 'unit':
            updateUnit(data.data);
            break;
        case 'assignment':
            updateAssignment(data.data);
            break;
        default:
            console.log('Unknown update type:', data.type);
    }
}

function updateIncident(incident) {
    // Update incident in the UI
    const incidentRow = document.querySelector(`tr[data-incident-id="${incident.id}"]`);
    if (incidentRow) {
        // Update incident details
        const statusCell = incidentRow.querySelector('.incident-status');
        const priorityCell = incidentRow.querySelector('.incident-priority');
        if (statusCell) statusCell.textContent = incident.status || incident.status_text || '';
        if (priorityCell) priorityCell.textContent = incident.priority || incident.priority_string || '';
        // Add any other updates needed
    }
}

function updateUnit(unit) {
    // Update unit in the UI
    const unitRow = document.querySelector(`tr[data-unit-id="${unit.id}"]`);
    if (unitRow) {
        // Update unit details
        const statusCell = unitRow.querySelector('.unit-status');
        const locCell = unitRow.querySelector('.unit-location');
        if (statusCell) statusCell.textContent = unit.status || '';
        if (locCell) locCell.textContent = unit.location || unit.current_location || '';
        // Add any other updates needed
    }
}

function updateAssignment(assignment) {
    // Update assignment in the UI
    const unitRow = document.querySelector(`tr[data-unit-id="${assignment.unit_id}"]`);
    if (unitRow) {
        // Update assignment details
        unitRow.querySelector('.unit-status').textContent = assignment.status;
        // Add any other updates needed
    }
}

// Initialize WebSocket when the page loads
document.addEventListener('DOMContentLoaded', function() {
    initWebSocket();
});
