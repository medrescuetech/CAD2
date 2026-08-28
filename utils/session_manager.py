"""
Session Management Utility

This module provides functions for managing user sessions,
including active session tracking, force logout, and session timeouts.
"""

from datetime import datetime, timedelta
from flask import current_app, session, request
from flask_login import current_user
from models import db, User, APIKey
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
import uuid
import json

def get_client_info():
    """Get client information for session tracking."""
    return {
        'ip_address': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', 'Unknown'),
        'referrer': request.referrer or 'Direct',
        'session_id': session.get('session_id', 'No Session')
    }

def generate_session_id():
    """Generate a unique session ID."""
    return str(uuid.uuid4())

def initialize_session(user):
    """
    Initialize a new session for a user.
    
    Args:
        user (User): The user to initialize the session for
        
    Returns:
        str: The new session ID
    """
    # Generate a new session ID
    session_id = generate_session_id()
    session['session_id'] = session_id
    
    # Set session timeout
    idle_timeout_minutes = current_app.config.get('SESSION_IDLE_TIMEOUT_MINUTES', 30)
    session['last_activity'] = datetime.utcnow().isoformat()
    session['idle_timeout_minutes'] = idle_timeout_minutes
    
    # Store session ID in user record
    user.session_id = session_id
    db.session.add(user)
    db.session.commit()
    
    # Log session creation
    client_info = get_client_info()
    log_audit_event(
        category=AuditCategory.AUTHENTICATION,
        action="Session started",
        severity=AuditSeverity.INFO,
        user_id=user.id,
        details={
            'session_id': session_id,
            'ip_address': client_info['ip_address'],
            'user_agent': client_info['user_agent']
        }
    )
    
    return session_id

def end_session(user=None):
    """
    End a user session.
    
    Args:
        user (User, optional): The user to end the session for. If None, uses current_user.
        
    Returns:
        bool: True if session was ended, False otherwise
    """
    if user is None and not current_user.is_authenticated:
        return False
    
    user_obj = user or current_user
    
    # Get session ID
    session_id = user_obj.session_id
    
    # Clear session ID from user record
    user_obj.session_id = None
    db.session.add(user_obj)
    db.session.commit()
    
    # Log session end
    client_info = get_client_info()
    log_audit_event(
        category=AuditCategory.AUTHENTICATION,
        action="Session ended",
        severity=AuditSeverity.INFO,
        user_id=user_obj.id,
        details={
            'session_id': session_id,
            'ip_address': client_info['ip_address'],
            'user_agent': client_info['user_agent']
        }
    )
    
    return True

def check_session_timeout():
    """
    Check if the current session has timed out due to inactivity.
    
    Returns:
        bool: True if session has timed out, False otherwise
    """
    if not current_user.is_authenticated:
        return False
    
    # Get last activity time and timeout setting
    last_activity_str = session.get('last_activity')
    idle_timeout_minutes = session.get('idle_timeout_minutes', 
                                     current_app.config.get('SESSION_IDLE_TIMEOUT_MINUTES', 30))
    
    if not last_activity_str:
        # No activity recorded, update and continue
        session['last_activity'] = datetime.utcnow().isoformat()
        return False
    
    # Parse last activity time
    try:
        last_activity = datetime.fromisoformat(last_activity_str)
    except (ValueError, TypeError):
        # Invalid timestamp, update and continue
        session['last_activity'] = datetime.utcnow().isoformat()
        return False
    
    # Check if session has timed out
    if datetime.utcnow() - last_activity > timedelta(minutes=idle_timeout_minutes):
        # Session has timed out
        log_audit_event(
            category=AuditCategory.AUTHENTICATION,
            action="Session timeout",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            details={
                'session_id': session.get('session_id', 'Unknown'),
                'idle_timeout_minutes': idle_timeout_minutes,
                'last_activity': last_activity_str
            }
        )
        return True
    
    # Update last activity time
    session['last_activity'] = datetime.utcnow().isoformat()
    return False

def get_active_sessions(user_id=None):
    """
    Get active sessions for all users or a specific user.
    
    Args:
        user_id (int, optional): User ID to get sessions for. If None, gets all active sessions.
        
    Returns:
        list: List of active session information
    """
    query = User.query.filter(User.session_id.isnot(None))
    
    if user_id is not None:
        query = query.filter_by(id=user_id)
    
    users_with_sessions = query.all()
    
    sessions = []
    for user in users_with_sessions:
        sessions.append({
            'user_id': user.id,
            'username': user.username,
            'session_id': user.session_id,
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'email': user.email
        })
    
    return sessions

def force_logout_session(session_id):
    """
    Force logout a session by session ID.
    
    Args:
        session_id (str): Session ID to force logout
        
    Returns:
        bool: True if session was ended, False otherwise
    """
    user = User.query.filter_by(session_id=session_id).first()
    
    if not user:
        return False
    
    # End the session
    return end_session(user)

def invalidate_api_key(api_key_value):
    """
    Invalidate an API key by marking it as inactive.
    
    Args:
        api_key_value (str): API key value to invalidate
        
    Returns:
        bool: True if API key was invalidated, False otherwise
    """
    # Find the API key by its value
    api_key = APIKey.query.filter_by(api_key=api_key_value).first()
    
    if not api_key:
        return False
    
    # Mark the API key as inactive
    api_key.is_active = False
    api_key.revoked_at = datetime.utcnow()
    db.session.add(api_key)
    db.session.commit()
    
    # Log API key invalidation
    log_audit_event(
        category=AuditCategory.API,
        action="API key invalidated",
        severity=AuditSeverity.INFO,
        user_id=api_key.user_id,
        details={
            'api_key_id': api_key.id,
            'revoked_at': api_key.revoked_at.isoformat(),
            'reason': 'Manual invalidation'
        }
    )
    
    return True

def update_session_activity():
    """Update the last activity timestamp for the current session."""
    if current_user.is_authenticated:
        session['last_activity'] = datetime.utcnow().isoformat()
