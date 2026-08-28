"""
Connection Manager Service

This module handles WebSocket connection management and reconnection strategies.
- Tracks active connections 
- Manages connection states
- Handles client reconnection
- Provides connection recovery mechanisms
"""

from flask_socketio import disconnect, emit, join_room, leave_room
from flask import current_app
import logging
from datetime import datetime, timedelta
import json
import threading
import time

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manages WebSocket connections and their states."""
    
    # Connection states
    STATE_CONNECTED = 'connected'
    STATE_DISCONNECTED = 'disconnected'
    STATE_RECONNECTING = 'reconnecting'
    STATE_INACTIVE = 'inactive'
    
    # Store active connections
    # Format: {client_id: {user_id: X, state: Y, last_seen: Z, rooms: [room1, room2]}}
    _active_connections = {}
    
    # Store user-to-client mappings
    # Format: {user_id: [client_id1, client_id2]}
    _user_connections = {}
    
    # Reconnection timeouts in seconds
    RECONNECT_TIMEOUT = 30
    INACTIVE_TIMEOUT = 300  # 5 minutes
    
    # Maintenance lock
    _lock = threading.RLock()
    
    # Cleanup thread
    _cleanup_thread = None
    _running = False
    
    @classmethod
    def register_connection(cls, client_id, user_id, rooms=None):
        """
        Register a new connection.
        
        Args:
            client_id (str): The client's socket ID
            user_id (int): The user's ID
            rooms (list): Optional list of rooms to join
        """
        with cls._lock:
            now = datetime.utcnow()
            
            # Create connection record
            cls._active_connections[client_id] = {
                'user_id': user_id,
                'state': cls.STATE_CONNECTED,
                'last_seen': now,
                'connected_at': now,
                'rooms': rooms or []
            }
            
            # Update user connections map
            if user_id not in cls._user_connections:
                cls._user_connections[user_id] = []
            if client_id not in cls._user_connections[user_id]:
                cls._user_connections[user_id].append(client_id)
            
            # Log the connection
            logger.info(f"User {user_id} connected with client ID {client_id}")
            
            # Join user's personal room
            join_room(f"user_{user_id}")
            
            # Join additional rooms if provided
            if rooms:
                for room in rooms:
                    join_room(room)
            
            # Ensure cleanup thread is running
            cls._ensure_cleanup_thread()
                    
            return True
    
    @classmethod
    def unregister_connection(cls, client_id):
        """
        Unregister a connection.
        
        Args:
            client_id (str): The client's socket ID
        """
        with cls._lock:
            if client_id in cls._active_connections:
                user_id = cls._active_connections[client_id]['user_id']
                
                # Update user connections map
                if user_id in cls._user_connections:
                    if client_id in cls._user_connections[user_id]:
                        cls._user_connections[user_id].remove(client_id)
                    # Clean up empty user entries
                    if not cls._user_connections[user_id]:
                        del cls._user_connections[user_id]
                
                # Remove connection record
                del cls._active_connections[client_id]
                
                # Log the disconnection
                logger.info(f"Client {client_id} (User {user_id}) disconnected")
                
                return True
            
            return False
    
    @classmethod
    def update_connection_state(cls, client_id, state):
        """
        Update a connection's state.
        
        Args:
            client_id (str): The client's socket ID
            state (str): The new connection state
        """
        with cls._lock:
            if client_id in cls._active_connections:
                cls._active_connections[client_id]['state'] = state
                cls._active_connections[client_id]['last_seen'] = datetime.utcnow()
                
                logger.debug(f"Client {client_id} state changed to {state}")
                return True
            
            return False
    
    @classmethod
    def heartbeat(cls, client_id):
        """
        Update last seen timestamp for a connection.
        
        Args:
            client_id (str): The client's socket ID
        """
        with cls._lock:
            if client_id in cls._active_connections:
                cls._active_connections[client_id]['last_seen'] = datetime.utcnow()
                
                # If the connection was inactive, mark it as connected again
                if cls._active_connections[client_id]['state'] == cls.STATE_INACTIVE:
                    cls._active_connections[client_id]['state'] = cls.STATE_CONNECTED
                    logger.info(f"Client {client_id} is active again")
                
                return True
            
            return False
    
    @classmethod
    def get_user_connections(cls, user_id):
        """
        Get all connections for a user.
        
        Args:
            user_id (int): The user's ID
            
        Returns:
            dict: Dictionary of client connections for this user
        """
        with cls._lock:
            result = {}
            if user_id in cls._user_connections:
                for client_id in cls._user_connections[user_id]:
                    if client_id in cls._active_connections:
                        result[client_id] = cls._active_connections[client_id]
            return result
    
    @classmethod
    def get_all_connections(cls):
        """
        Get all active connections.
        
        Returns:
            dict: Dictionary of all active connections
        """
        with cls._lock:
            return cls._active_connections.copy()
    
    @classmethod
    def get_active_users(cls):
        """
        Get list of currently active user IDs.
        
        Returns:
            list: List of active user IDs
        """
        with cls._lock:
            return list(cls._user_connections.keys())
    
    @classmethod
    def get_connection_details(cls, client_id):
        """
        Get details for a specific connection.
        
        Args:
            client_id (str): The client's socket ID
            
        Returns:
            dict: Connection details or None if not found
        """
        with cls._lock:
            return cls._active_connections.get(client_id)
    
    @classmethod
    def is_user_online(cls, user_id):
        """
        Check if a user has any active connections.
        
        Args:
            user_id (int): The user's ID
            
        Returns:
            bool: True if user has active connections
        """
        with cls._lock:
            if user_id not in cls._user_connections:
                return False
                
            # Check if any connections are in CONNECTED state
            for client_id in cls._user_connections[user_id]:
                if client_id in cls._active_connections:
                    if cls._active_connections[client_id]['state'] == cls.STATE_CONNECTED:
                        return True
                        
            return False
    
    @classmethod
    def add_to_room(cls, client_id, room):
        """
        Add a client to a room.
        
        Args:
            client_id (str): The client's socket ID
            room (str): Room name
        """
        with cls._lock:
            if client_id in cls._active_connections:
                if room not in cls._active_connections[client_id]['rooms']:
                    cls._active_connections[client_id]['rooms'].append(room)
                    return True
            return False
    
    @classmethod
    def remove_from_room(cls, client_id, room):
        """
        Remove a client from a room.
        
        Args:
            client_id (str): The client's socket ID
            room (str): Room name
        """
        with cls._lock:
            if client_id in cls._active_connections:
                if room in cls._active_connections[client_id]['rooms']:
                    cls._active_connections[client_id]['rooms'].remove(room)
                    return True
            return False
    
    @classmethod
    def reconnect_client(cls, old_client_id, new_client_id):
        """
        Reconnect a client with a new ID.
        
        Args:
            old_client_id (str): The old client's socket ID
            new_client_id (str): The new client's socket ID
            
        Returns:
            bool: True if reconnection was successful
        """
        with cls._lock:
            # Check if old connection exists
            if old_client_id not in cls._active_connections:
                logger.warning(f"Attempted to reconnect unknown client {old_client_id}")
                return False
                
            # Get the old connection details
            connection = cls._active_connections[old_client_id]
            user_id = connection['user_id']
            rooms = connection['rooms']
            
            # Create new connection with same details
            now = datetime.utcnow()
            cls._active_connections[new_client_id] = {
                'user_id': user_id,
                'state': cls.STATE_CONNECTED,
                'last_seen': now,
                'connected_at': now,
                'reconnected_from': old_client_id,
                'original_connected_at': connection.get('connected_at'),
                'rooms': rooms.copy()
            }
            
            # Update user connections map
            if user_id in cls._user_connections:
                if new_client_id not in cls._user_connections[user_id]:
                    cls._user_connections[user_id].append(new_client_id)
                    
                # Remove old client ID
                if old_client_id in cls._user_connections[user_id]:
                    cls._user_connections[user_id].remove(old_client_id)
            
            # Join rooms with new client ID
            join_room(f"user_{user_id}")
            for room in rooms:
                join_room(room)
            
            # Remove old connection
            del cls._active_connections[old_client_id]
            
            logger.info(f"Reconnected client {old_client_id} as {new_client_id} for user {user_id}")
            return True
    
    @classmethod
    def broadcast_to_user(cls, user_id, event, data, include_inactive=False):
        """
        Broadcast an event to all of a user's connections.
        
        Args:
            user_id (int): The user's ID
            event (str): The event name
            data (dict): The event data
            include_inactive (bool): Whether to include inactive connections
            
        Returns:
            int: Number of connections the event was sent to
        """
        with cls._lock:
            sent_count = 0
            
            if user_id in cls._user_connections:
                for client_id in cls._user_connections[user_id]:
                    if client_id in cls._active_connections:
                        conn = cls._active_connections[client_id]
                        
                        # Skip inactive connections unless requested
                        if not include_inactive and conn['state'] != cls.STATE_CONNECTED:
                            continue
                            
                        # Emit event to this client
                        try:
                            emit(event, data, room=client_id)
                            sent_count += 1
                        except Exception as e:
                            logger.error(f"Error broadcasting to client {client_id}: {str(e)}")
            
            return sent_count
    
    @classmethod
    def broadcast_to_room(cls, room, event, data, skip_client_id=None):
        """
        Broadcast an event to all clients in a room.
        
        Args:
            room (str): The room name
            event (str): The event name
            data (dict): The event data
            skip_client_id (str): Optional client ID to skip
            
        Returns:
            int: Number of connections the event was sent to
        """
        with cls._lock:
            # Use Flask-SocketIO's room emit feature
            try:
                emit(event, data, room=room, skip_sid=skip_client_id)
                return True
            except Exception as e:
                logger.error(f"Error broadcasting to room {room}: {str(e)}")
                return False
    
    @classmethod
    def get_rooms_for_client(cls, client_id):
        """
        Get all rooms a client is in.
        
        Args:
            client_id (str): The client's socket ID
            
        Returns:
            list: List of room names
        """
        with cls._lock:
            if client_id in cls._active_connections:
                return cls._active_connections[client_id]['rooms'].copy()
            return []
    
    @classmethod
    def connection_exists(cls, client_id):
        """
        Check if a connection exists.
        
        Args:
            client_id (str): The client's socket ID
            
        Returns:
            bool: True if connection exists
        """
        with cls._lock:
            return client_id in cls._active_connections
    
    @classmethod
    def remove_connection(cls, client_id):
        """
        Forcibly remove a connection.
        
        Args:
            client_id (str): The client's socket ID
            
        Returns:
            bool: True if connection was removed
        """
        return cls.unregister_connection(client_id)
    
    @classmethod
    def _cleanup_inactive_connections(cls):
        """
        Cleanup inactive connections based on timeout values.
        
        Returns:
            tuple: (disconnected_count, inactive_count)
        """
        with cls._lock:
            now = datetime.utcnow()
            disconnected_count = 0
            inactive_count = 0
            
            # Find expired connections
            to_disconnect = []
            to_mark_inactive = []
            
            for client_id, conn in cls._active_connections.items():
                last_seen = conn['last_seen']
                
                # Check reconnection timeout for disconnected connections
                if conn['state'] == cls.STATE_DISCONNECTED:
                    if (now - last_seen).total_seconds() > cls.RECONNECT_TIMEOUT:
                        to_disconnect.append(client_id)
                        
                # Check inactivity timeout for connected connections
                elif conn['state'] == cls.STATE_CONNECTED:
                    if (now - last_seen).total_seconds() > cls.INACTIVE_TIMEOUT:
                        to_mark_inactive.append(client_id)
            
            # Handle disconnections (after removing from the iterator)
            for client_id in to_disconnect:
                cls.unregister_connection(client_id)
                disconnected_count += 1
                
            # Mark connections as inactive
            for client_id in to_mark_inactive:
                cls._active_connections[client_id]['state'] = cls.STATE_INACTIVE
                inactive_count += 1
                
            return disconnected_count, inactive_count
    
    @classmethod
    def _cleanup_thread_func(cls):
        """Thread function to periodically clean up inactive connections."""
        logger.info("Connection cleanup thread started")
        
        try:
            while cls._running:
                # Run cleanup every 60 seconds
                time.sleep(60)
                
                try:
                    disconnected, inactive = cls._cleanup_inactive_connections()
                    if disconnected > 0 or inactive > 0:
                        logger.info(f"Cleanup: Disconnected {disconnected} connections, marked {inactive} as inactive")
                except Exception as e:
                    logger.error(f"Error in connection cleanup: {str(e)}")
        except:
            logger.exception("Connection cleanup thread crashed")
        finally:
            logger.info("Connection cleanup thread stopped")
    
    # Class variable to track initialization status
    _initialized = False
    
    @classmethod
    def initialize(cls):
        """Initialize the ConnectionManager.
        
        This should be called once during application startup.
        """
        # Prevent multiple initializations
        if cls._initialized:
            logger.info("ConnectionManager already initialized, skipping")
            return
            
        logger.info("Initializing ConnectionManager")
        # Reset connections in case of server restart
        with cls._lock:
            cls._active_connections = {}
            cls._user_connections = {}
            
        # Start cleanup thread
        cls._ensure_cleanup_thread()
        
        # Mark as initialized
        cls._initialized = True
        logger.info("ConnectionManager initialized successfully")
    
    @classmethod
    def _ensure_cleanup_thread(cls):
        """Ensure the cleanup thread is running."""
        if cls._cleanup_thread is None or not cls._cleanup_thread.is_alive():
            cls._running = True
            cls._cleanup_thread = threading.Thread(target=cls._cleanup_thread_func)
            cls._cleanup_thread.daemon = True
            cls._cleanup_thread.start()
            logger.info("Connection cleanup thread started")
    
    @classmethod
    def get_connection_statistics(cls):
        """
        Get statistics about active connections.
        
        Returns:
            dict: Connection statistics
        """
        with cls._lock:
            total_connections = len(cls._active_connections)
            total_users = len(cls._user_connections)
            
            # Count connections by state
            connected = 0
            disconnected = 0
            reconnecting = 0
            inactive = 0
            
            for conn in cls._active_connections.values():
                state = conn['state']
                if state == cls.STATE_CONNECTED:
                    connected += 1
                elif state == cls.STATE_DISCONNECTED:
                    disconnected += 1
                elif state == cls.STATE_RECONNECTING:
                    reconnecting += 1
                elif state == cls.STATE_INACTIVE:
                    inactive += 1
            
            return {
                'total_connections': total_connections,
                'total_users': total_users,
                'connected': connected,
                'disconnected': disconnected,
                'reconnecting': reconnecting,
                'inactive': inactive
            }
