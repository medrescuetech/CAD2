"""
User WebSocket Events

This module contains WebSocket event handlers for user-related operations including:
- User presence/status updates
- User notifications
- User action broadcasts
"""

from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room
from models import User, Permission
from extensions import db, socketio
from datetime import datetime
import logging
from services.connection_manager import ConnectionManager
from services.notification_service import NotificationService
from utils.audit import create_audit_log

logger = logging.getLogger(__name__)

def check_auth():
    """Check if user is authenticated."""
    if not current_user.is_authenticated:
        emit('error', {'message': 'AUTH_REQUIRED', 'details': 'Authentication required'})
        return False
    return True

def check_permission(permission):
    """Check if user has required permission."""
    if not current_user.is_authenticated or not current_user.role.has_permission(permission):
        emit('error', {'message': 'PERMISSION_DENIED', 'details': 'Insufficient permissions'})
        return False
    return True

@socketio.on('join_user_room')
def handle_join_user_room():
    """Join a private room for the current user to receive personal notifications."""
    try:
        if not check_auth():
            return
        
        client_id = request.sid
        user_id = current_user.id
        room_name = f'user_{user_id}'
        
        join_room(room_name)
        ConnectionManager.add_to_room(client_id, room_name)
        
        emit('room_joined', {'room': room_name})
        logger.debug(f"Client {client_id} joined user room {room_name}")
        
        # Mark user as active/online
        user = User.query.get(user_id)
        if user:
            user.last_active = datetime.utcnow()
            user.is_online = True
            db.session.commit()
            
            # Broadcast user status to users with VIEW_USERS permission
            broadcast_user_status(user, 'online')
        
    except Exception as e:
        logger.error(f"Error joining user room: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('leave_user_room')
def handle_leave_user_room():
    """Leave the private user room."""
    try:
        if not check_auth():
            return
        
        client_id = request.sid
        user_id = current_user.id
        room_name = f'user_{user_id}'
        
        leave_room(room_name)
        ConnectionManager.remove_from_room(client_id, room_name)
        
        emit('room_left', {'room': room_name})
        logger.debug(f"Client {client_id} left user room {room_name}")
        
    except Exception as e:
        logger.error(f"Error leaving user room: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('join_user_updates')
def handle_join_user_updates():
    """Join the user updates room to receive broadcasts about user status changes."""
    try:
        if not check_auth():
            return
        
        if not check_permission(Permission.VIEW_USERS):
            return
            
        client_id = request.sid
        join_room('user_updates')
        ConnectionManager.add_to_room(client_id, 'user_updates')
        
        emit('room_joined', {'room': 'user_updates'})
        logger.debug(f"Client {client_id} joined user_updates room")
        
    except Exception as e:
        logger.error(f"Error joining user_updates room: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('leave_user_updates')
def handle_leave_user_updates():
    """Leave the user updates room."""
    try:
        if not check_auth():
            return
        
        client_id = request.sid
        leave_room('user_updates')
        ConnectionManager.remove_from_room(client_id, 'user_updates')
        
        emit('room_left', {'room': 'user_updates'})
        logger.debug(f"Client {client_id} left user_updates room")
        
    except Exception as e:
        logger.error(f"Error leaving user_updates room: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_active_users')
def handle_get_active_users():
    """Get all currently active users."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.VIEW_USERS):
            return
            
        # Get all active users (active in the last 15 minutes)
        from datetime import timedelta
        cutoff_time = datetime.utcnow() - timedelta(minutes=15)
        active_users = User.query.filter(User.last_active >= cutoff_time).all()
            
        # Convert to dictionary format for JSON response
        result = [user.to_dict(exclude_sensitive=True) for user in active_users]
            
        emit('active_users', {'users': result, 'count': len(result)})
            
    except Exception as e:
        logger.error(f"Error getting active users: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('update_user_status')
def handle_update_user_status(data):
    """Update a user's status (online, away, offline, busy, etc.)."""
    try:
        if not check_auth():
            return
            
        if 'status' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Status is required'})
            return
            
        user_id = current_user.id
        status = data['status']
        
        # Validate status
        valid_statuses = ['online', 'offline', 'away', 'busy', 'do_not_disturb']
        if status not in valid_statuses:
            emit('error', {
                'message': 'VALIDATION_ERROR', 
                'details': f'Invalid status. Valid statuses are: {", ".join(valid_statuses)}'
            })
            return
            
        # Update user status
        user = User.query.get(user_id)
        if user:
            # Update status-related fields
            user.status = status
            user.last_active = datetime.utcnow()
            user.is_online = status != 'offline'
            
            # Add status message if provided
            if 'status_message' in data:
                user.status_message = data['status_message']
                
            db.session.commit()
            
            # Broadcast user status update
            broadcast_user_status(user, status)
            
            # Send confirmation to the requesting client
            emit('user_status_updated_confirm', {
                'status': status,
                'message': f'Your status has been updated to {status}'
            })
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user status: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

def broadcast_user_status(user, status):
    """Broadcast user status change to all users in the user_updates room."""
    try:
        user_data = user.to_dict(exclude_sensitive=True)
        user_data['status'] = status
        
        socketio.emit('user_status_changed', {
            'user': user_data,
            'status': status,
            'timestamp': datetime.utcnow().isoformat()
        }, room='user_updates')
        
    except Exception as e:
        logger.error(f"Error broadcasting user status: {str(e)}")

@socketio.on('get_notifications')
def handle_get_notifications(data=None):
    """Get notifications for the current user."""
    try:
        if not check_auth():
            return
            
        user_id = current_user.id
        limit = data.get('limit', 50) if data else 50
        include_read = data.get('include_read', False) if data else False
        
        # Get notifications
        notifications = NotificationService.get_notifications_for_user(
            user_id=user_id,
            limit=limit,
            include_read=include_read
        )
        
        # Convert to dictionary format for JSON response
        result = [notification for notification in notifications]
        
        # Also count unread notifications
        unread_count = NotificationService.count_unread_notifications(user_id)
        
        emit('notifications', {
            'notifications': result, 
            'count': len(result),
            'unread_count': unread_count
        })
        
    except Exception as e:
        logger.error(f"Error getting notifications: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('mark_notification_read')
def handle_mark_notification_read(data):
    """Mark a notification as read."""
    try:
        if not check_auth():
            return
            
        if 'notification_id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Notification ID is required'})
            return
            
        user_id = current_user.id
        notification_id = data['notification_id']
        
        # Mark notification as read
        success = NotificationService.mark_notification_read(
            notification_id=notification_id,
            user_id=user_id
        )
        
        if not success:
            emit('error', {'message': 'NOT_FOUND', 'details': 'Notification not found or not owned by you'})
            return
            
        # Get updated unread count
        unread_count = NotificationService.count_unread_notifications(user_id)
        
        emit('notification_marked_read', {
            'notification_id': notification_id,
            'unread_count': unread_count,
            'message': 'Notification marked as read'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error marking notification as read: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('mark_all_notifications_read')
def handle_mark_all_notifications_read():
    """Mark all notifications as read for the current user."""
    try:
        if not check_auth():
            return
            
        user_id = current_user.id
        
        # Mark all notifications as read
        count = NotificationService.mark_all_notifications_read(user_id)
        
        emit('all_notifications_marked_read', {
            'count': count,
            'unread_count': 0,
            'message': f'Marked {count} notifications as read'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error marking all notifications as read: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('delete_notification')
def handle_delete_notification(data):
    """Delete a notification."""
    try:
        if not check_auth():
            return
            
        if 'notification_id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Notification ID is required'})
            return
            
        user_id = current_user.id
        notification_id = data['notification_id']
        
        # Delete notification
        success = NotificationService.delete_notification(
            notification_id=notification_id,
            user_id=user_id
        )
        
        if not success:
            emit('error', {'message': 'NOT_FOUND', 'details': 'Notification not found or not owned by you'})
            return
            
        # Get updated unread count
        unread_count = NotificationService.count_unread_notifications(user_id)
        
        emit('notification_deleted', {
            'notification_id': notification_id,
            'unread_count': unread_count,
            'message': 'Notification deleted'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting notification: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_user')
def handle_get_user(data):
    """Get details for a specific user."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.VIEW_USERS):
            return
            
        if 'id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'User ID is required'})
            return
            
        user_id = data['id']
        user = User.query.get(user_id)
            
        if not user:
            emit('error', {'message': 'NOT_FOUND', 'details': f'User with ID {user_id} not found'})
            return
            
        # Get user data, excluding sensitive information
        user_data = user.to_dict(exclude_sensitive=True)
            
        emit('user_details', {'user': user_data})
            
    except Exception as e:
        logger.error(f"Error getting user details: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})
