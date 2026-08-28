"""
Logging Utility

This module provides functions for activity logging in the CAD system.
It captures user actions, system events, and general activity to track system usage.
"""

import logging
from flask import request, current_app, g
from datetime import datetime
import json
from flask_login import current_user

# Set up a dedicated logger for activity events
activity_logger = logging.getLogger('activity')

def log_activity(action, details=None, user_id=None, resource_id=None, resource_type=None):
    """
    Log a user or system activity event.
    
    Args:
        action (str): Description of the action
        details (dict): Additional details about the activity
        user_id (int): ID of the user who performed the action
        resource_id (str): ID of the resource being accessed/modified
        resource_type (str): Type of resource being accessed/modified
    """
    try:
        # Get user ID from current user if not provided
        if user_id is None and hasattr(current_user, 'is_authenticated'):
            if current_user.is_authenticated:
                user_id = current_user.id
            
        # Normalize details to a dictionary
        if details is None:
            details = {}
        elif not isinstance(details, dict):
            details = {'data': str(details)}
            
        # Create timestamp
        timestamp = datetime.utcnow().isoformat()
        
        # Get user_agent as string
        user_agent_str = None
        if hasattr(request, 'user_agent') and request.user_agent:
            try:
                user_agent_str = request.user_agent.string
            except (AttributeError, TypeError):
                user_agent_str = str(request.user_agent)
        
        # Make sure details is JSON serializable
        serializable_details = {}
        for key, value in details.items():
            try:
                # Test if it's JSON serializable
                json.dumps({key: value})
                serializable_details[key] = value
            except (TypeError, OverflowError):
                # If not serializable, convert to string
                serializable_details[key] = str(value)
        
        # Build log entry
        log_entry = {
            'timestamp': timestamp,
            'action': action,
            'user_id': user_id,
            'resource_id': resource_id,
            'resource_type': resource_type,
            'details': serializable_details,
            'ip_address': getattr(request, 'remote_addr', None),
            'user_agent': user_agent_str,
            'endpoint': getattr(request, 'endpoint', None)
        }
        
        # Log to file
        activity_logger.info(json.dumps(log_entry))
        
        # In development, also log to console
        if current_app.config.get('DEBUG', False):
            print(f"ACTIVITY: {action} | User: {user_id} | Resource: {resource_type}:{resource_id}")
            
        # Store in database if configured
        if current_app.config.get('LOG_TO_DATABASE', False):
            _log_to_database(log_entry)
            
    except Exception as e:
        current_app.logger.error(f"Error logging activity: {str(e)}")
        
def _log_to_database(log_entry):
    """
    Store activity log in database.
    
    Args:
        log_entry (dict): Log entry to store
    """
    try:
        from models import ActivityLog, db
        
        # Create new log entry
        activity_log = ActivityLog(
            timestamp=datetime.fromisoformat(log_entry['timestamp']),
            action=log_entry['action'],
            user_id=log_entry['user_id'],
            resource_id=log_entry['resource_id'],
            resource_type=log_entry['resource_type'],
            details=json.dumps(log_entry['details']),
            ip_address=log_entry['ip_address'],
            user_agent=log_entry['user_agent'],
            endpoint=log_entry['endpoint']
        )
        
        # Add to database
        db.session.add(activity_log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Error logging to database: {str(e)}")
        # Rollback if there was an error
        try:
            db.session.rollback()
        except:
            pass
