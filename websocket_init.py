"""
WebSocket Initialization Module

This module initializes the WebSocket functionality for the CAD system, 
connecting event handlers with the Socket.IO instance and setting up
the connection manager.

It should be imported and initialized in the app factory.
"""

import logging
import time
from functools import wraps
from flask import current_app, request, session
from flask_socketio import emit, disconnect
from flask_login import current_user
from extensions import socketio
from services.connection_manager import ConnectionManager
from datetime import datetime, timedelta

# Use a specific logger for WebSocket operations
logger = logging.getLogger('websocket')

# Track active connections and their metadata
active_connections = {}

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 25

# Timeout for considering a connection dead
CONNECTION_TIMEOUT = 60

def authenticated_only(f):
    """Decorator to ensure WebSocket connections are authenticated."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            logger.warning(f"Unauthenticated WebSocket connection attempt from {request.remote_addr}")
            emit('auth_error', {'message': 'Authentication required'})
            disconnect()
            return False
        return f(*args, **kwargs)
    return wrapped

def track_connection(client_id, user_id):
    """Track a new WebSocket connection."""
    active_connections[client_id] = {
        'user_id': user_id,
        'last_heartbeat': time.time(),
        'status': 'connected',
        'ip_address': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', 'unknown'),
        'connected_at': datetime.utcnow()
    }
    # Application-level logging only (no DB dependency here)
    logger.debug(f"Tracked connection for user {user_id} with client_id {client_id}")

def update_heartbeat(client_id):
    """Update the last heartbeat time for a connection."""
    if client_id in active_connections:
        active_connections[client_id]['last_heartbeat'] = time.time()
        return True
    return False

def cleanup_stale_connections():
    """Clean up connections that haven't sent a heartbeat."""
    current_time = time.time()
    stale_clients = []
    
    for client_id, conn in list(active_connections.items()):
        if current_time - conn['last_heartbeat'] > CONNECTION_TIMEOUT:
            stale_clients.append(client_id)
    
    for client_id in stale_clients:
        logger.info(f"Cleaning up stale connection: {client_id}")
        disconnect_client(client_id, 'connection_timeout')

def disconnect_client(client_id, reason='unknown'):
    """Handle client disconnection."""
    if client_id in active_connections:
        conn = active_connections.pop(client_id, None)
        if conn:
            logger.info(f"Client {client_id} disconnected: {reason}")
            # Notify other users if needed (no DB updates)
            if 'user_id' in conn:
                socketio.emit('user_disconnected', {
                    'user_id': conn['user_id'],
                    'timestamp': datetime.utcnow().isoformat(),
                    'reason': reason
                }, room=f"user_{conn['user_id']}")

# Flag to track whether init_socketio has been called
_socketio_initialized = False
_cleanup_task = None

def init_socketio(app=None):
    """Initialize Socket.IO with event handlers and background tasks."""
    global _socketio_initialized, _cleanup_task
    
    # Prevent duplicate initialization
    if _socketio_initialized:
        logger.info("WebSocket functionality already initialized, skipping")
        return
    
    try:
        logger.info("Initializing WebSocket functionality")
        
        # Initialize connection manager
        if app:
            with app.app_context():
                ConnectionManager.initialize()
                # Start cleanup task
                _cleanup_task = socketio.start_background_task(connection_cleanup_loop)
        else:
            ConnectionManager.initialize()
            _cleanup_task = socketio.start_background_task(connection_cleanup_loop)
        
        # Register namespace handlers
        from websocket_events import register_handlers
        register_handlers(socketio)
        
        _socketio_initialized = True
        logger.info("WebSocket functionality initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize WebSocket functionality: {str(e)}")
        raise

def connection_cleanup_loop():
    """Background task to clean up stale connections."""
    while True:
        try:
            cleanup_stale_connections()
            socketio.sleep(30)  # Check every 30 seconds
        except Exception as e:
            logger.error(f"Error in connection cleanup loop: {str(e)}")
            socketio.sleep(30)  # Wait before retrying

def shutdown_socketio():
    """Shutdown Socket.IO and clean up connections."""
    global _socketio_initialized, _cleanup_task, active_connections
    
    # Disconnect all active connections
    for client_id in list(active_connections.keys()):
        disconnect_client(client_id, 'server_shutdown')
    
    # Clear active connections
    active_connections.clear()
    
    # Stop cleanup task if running
    if _cleanup_task:
        _cleanup_task.cancel()
        _cleanup_task = None
    
    _socketio_initialized = False
    logger.info("WebSocket functionality shutdown complete")
    logger.info("Shutting down WebSocket functionality")
    ConnectionManager.shutdown()
