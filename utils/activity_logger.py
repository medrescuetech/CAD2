"""
Activity logger module for the CAD system.

This module provides functions for logging user activity within the application
for audit purposes and system monitoring.
"""

import logging
from datetime import datetime
from flask import current_app, request, g
import json
from threading import Lock

# Set up logging
logger = logging.getLogger(__name__)

# Thread safety for activity logging
activity_log_lock = Lock()

class ActivityType:
    """Activity type enumeration for consistent categorization."""
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    VIEW = "VIEW"
    EXPORT = "EXPORT"
    IMPORT = "IMPORT"
    CONFIGURATION = "CONFIGURATION"
    SYSTEM = "SYSTEM"
    ERROR = "ERROR"
    WARNING = "WARNING"
    OTHER = "OTHER"

def log_activity(activity_type, description, user_id=None, entity_type=None, entity_id=None, details=None):
    """
    Log a user activity event.
    
    Args:
        activity_type (str): Type of activity (use ActivityType enum)
        description (str): Human-readable description of the activity
        user_id (int, optional): ID of the user performing the action
        entity_type (str, optional): Type of entity being acted upon (e.g., 'incident', 'user')
        entity_id (int/str, optional): ID of the entity being acted upon
        details (dict, optional): Additional details about the activity
    """
    try:
        # Get user ID from flask login if not provided
        if user_id is None:
            try:
                from flask_login import current_user
                if current_user.is_authenticated:
                    user_id = current_user.id
                else:
                    user_id = None
            except Exception:
                user_id = None
        
        # Get IP address from request context if available
        ip_address = None
        try:
            if request:
                ip_address = request.remote_addr
        except Exception:
            pass
            
        # Create activity record
        activity = {
            'timestamp': datetime.utcnow().isoformat(),
            'activity_type': activity_type,
            'description': description,
            'user_id': user_id,
            'ip_address': ip_address,
            'entity_type': entity_type,
            'entity_id': entity_id,
            'details': details or {}
        }
        
        # Log to application log
        with activity_log_lock:
            logger.info(f"ACTIVITY: {json.dumps(activity)}")
        
        # Store in database if configured
        try:
            if hasattr(current_app, 'db') and current_app.config.get('LOG_ACTIVITIES_TO_DB', True):
                from models import ActivityLog, db
                
                with activity_log_lock:
                    log_entry = ActivityLog(
                        timestamp=datetime.utcnow(),
                        activity_type=activity_type,
                        description=description,
                        user_id=user_id,
                        ip_address=ip_address,
                        entity_type=entity_type,
                        entity_id=str(entity_id) if entity_id is not None else None,
                        details=json.dumps(details) if details else None
                    )
                    db.session.add(log_entry)
                    db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to store activity log in database: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error logging activity: {str(e)}")

def get_recent_activities(limit=100, user_id=None, activity_type=None, entity_type=None, entity_id=None):
    """
    Get recent activity logs from the database.
    
    Args:
        limit (int): Maximum number of activities to return
        user_id (int, optional): Filter by user ID
        activity_type (str, optional): Filter by activity type
        entity_type (str, optional): Filter by entity type
        entity_id (int/str, optional): Filter by entity ID
        
    Returns:
        list: List of activity logs
    """
    try:
        from models import ActivityLog
        
        query = ActivityLog.query
        
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
            
        if activity_type is not None:
            query = query.filter_by(activity_type=activity_type)
            
        if entity_type is not None:
            query = query.filter_by(entity_type=entity_type)
            
        if entity_id is not None:
            query = query.filter_by(entity_id=str(entity_id))
            
        activities = query.order_by(ActivityLog.timestamp.desc()).limit(limit).all()
        
        return activities
    except Exception as e:
        logger.error(f"Error retrieving activity logs: {str(e)}")
        return []

def clear_old_activity_logs(days_to_keep=90):
    """
    Remove activity logs older than the specified number of days.
    
    Args:
        days_to_keep (int): Number of days worth of logs to keep
        
    Returns:
        int: Number of logs deleted
    """
    try:
        from models import ActivityLog, db
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        with activity_log_lock:
            deleted_count = ActivityLog.query.filter(ActivityLog.timestamp < cutoff_date).delete()
            db.session.commit()
            
        logger.info(f"Cleared {deleted_count} activity logs older than {days_to_keep} days")
        return deleted_count
    except Exception as e:
        logger.error(f"Error clearing old activity logs: {str(e)}")
        return 0
