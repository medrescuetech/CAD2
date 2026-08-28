"""
Automated logging utility for system events.
This module provides functions to automatically create log entries for system events.
"""

from flask import current_app
from datetime import datetime
from models import DailyLog, DailyLogEntry, User
from extensions import db
from sqlalchemy import desc

# Define system event types
EVENT_TYPES = {
    'SYSTEM': 'SYSTEM',
    'INCIDENT': 'INCIDENT',
    'USER': 'USER',
    'RESOURCE': 'RESOURCE',
    'ERROR': 'ERROR',
    'SECURITY': 'SECURITY',
    'MAINTENANCE': 'MAINTENANCE'
}

def get_or_create_system_log():
    """
    Get the current system log or create one if it doesn't exist.
    System logs are special daily logs used for automated system events.
    """
    try:
        # Get the system user (ID 1 is typically system/admin user)
        system_user = User.query.filter_by(username='system').first()
        
        if not system_user:
            # If no system user exists, get the first admin user
            system_user = User.query.filter_by(is_admin=True).first()
            
            if not system_user:
                current_app.logger.error("No system or admin user found for system logging")
                return None
        
        # Get current date
        current_date = datetime.now().date()
        
        # Check if a system log exists for today
        system_log = DailyLog.query.filter(
            DailyLog.user_id == system_user.id,
            DailyLog.date == current_date,
            DailyLog.shift == 'system'
        ).first()
        
        # If no system log exists, create one
        if not system_log:
            system_log = DailyLog(
                date=current_date,
                shift='system',
                user_id=system_user.id,
                notes="System automated log for recording system events."
            )
            db.session.add(system_log)
            db.session.commit()
            
            current_app.logger.info(f"Created new system log for {current_date}")
        
        return system_log
        
    except Exception as e:
        current_app.logger.error(f"Error in get_or_create_system_log: {str(e)}")
        db.session.rollback()
        return None

def log_system_event(event_type, message, related_id=None, related_type=None):
    """
    Log a system event into the system daily log.
    
    Args:
        event_type: Type of event (use EVENT_TYPES constants)
        message: Description of the event
        related_id: Optional ID of related object (incident ID, user ID, etc.)
        related_type: Optional type of related object ('incident', 'user', etc.)
    
    Returns:
        The created log entry or None if failed
    """
    try:
        # Validate event type
        if event_type not in EVENT_TYPES.values():
            event_type = EVENT_TYPES['SYSTEM']
        
        # Get or create system log
        system_log = get_or_create_system_log()
        if not system_log:
            current_app.logger.error("Failed to get or create system log")
            return None
        
        # Format message with related information if provided
        full_message = message
        if related_id and related_type:
            full_message = f"{message} [{related_type}:{related_id}]"
        
        # Get system user
        system_user = User.query.get(system_log.user_id)
        if not system_user:
            current_app.logger.error("System user not found")
            return None
        
        # Create log entry
        entry = DailyLogEntry(
            log_id=system_log.id,
            user_id=system_user.id,
            type=event_type,
            text=full_message
        )
        
        db.session.add(entry)
        db.session.commit()
        
        current_app.logger.debug(f"Logged system event: {event_type} - {full_message}")
        return entry
        
    except Exception as e:
        current_app.logger.error(f"Error in log_system_event: {str(e)}")
        db.session.rollback()
        return None

def log_incident_creation(incident_id, incident_type, created_by_user_id):
    """Convenience function to log incident creation."""
    user = User.query.get(created_by_user_id)
    username = user.username if user else "Unknown user"
    
    message = f"New incident created: {incident_type} by {username}"
    return log_system_event(EVENT_TYPES['INCIDENT'], message, incident_id, 'incident')

def log_incident_update(incident_id, incident_type, updated_by_user_id, changes=None):
    """Convenience function to log incident updates."""
    user = User.query.get(updated_by_user_id)
    username = user.username if user else "Unknown user"
    
    change_text = ""
    if changes and isinstance(changes, list):
        change_text = " - Changes: " + ", ".join(changes)
    
    message = f"Incident updated: {incident_type} by {username}{change_text}"
    return log_system_event(EVENT_TYPES['INCIDENT'], message, incident_id, 'incident')

def log_user_activity(user_id, action, details=None):
    """Convenience function to log user activity."""
    user = User.query.get(user_id)
    username = user.username if user else "Unknown user"
    
    detail_text = f": {details}" if details else ""
    message = f"User activity: {username} performed {action}{detail_text}"
    return log_system_event(EVENT_TYPES['USER'], message, user_id, 'user')

def log_error(error_message, module=None, function=None):
    """Convenience function to log system errors."""
    context = ""
    if module and function:
        context = f" in {module}.{function}"
    elif module:
        context = f" in {module}"
    
    message = f"System error{context}: {error_message}"
    return log_system_event(EVENT_TYPES['ERROR'], message)

def log_security_event(event_description, user_id=None, ip_address=None):
    """Convenience function to log security events."""
    context = ""
    if user_id:
        user = User.query.get(user_id)
        username = user.username if user else "Unknown user"
        context += f" User: {username}"
    
    if ip_address:
        context += f" IP: {ip_address}"
    
    message = f"Security event:{context} - {event_description}"
    return log_system_event(EVENT_TYPES['SECURITY'], message, user_id, 'user' if user_id else None)

def get_recent_system_events(limit=50, event_type=None):
    """
    Get recent system events.
    
    Args:
        limit: Maximum number of events to return
        event_type: Optional filter for specific event type
    
    Returns:
        List of log entries
    """
    try:
        # Find the system log
        system_user = User.query.filter_by(username='system').first()
        if not system_user:
            system_user = User.query.filter_by(is_admin=True).first()
        
        if not system_user:
            return []
        
        # Find system logs from the past 30 days
        thirty_days_ago = datetime.now().date() - db.text("interval '30 days'")
        system_logs = DailyLog.query.filter(
            DailyLog.user_id == system_user.id,
            DailyLog.shift == 'system',
            DailyLog.date >= thirty_days_ago
        ).all()
        
        if not system_logs:
            return []
        
        # Get log IDs
        log_ids = [log.id for log in system_logs]
        
        # Query entries
        query = DailyLogEntry.query.filter(DailyLogEntry.log_id.in_(log_ids))
        
        if event_type:
            query = query.filter(DailyLogEntry.type == event_type)
        
        # Get most recent entries
        entries = query.order_by(desc(DailyLogEntry.timestamp)).limit(limit).all()
        
        return [entry.to_dict() for entry in entries]
        
    except Exception as e:
        current_app.logger.error(f"Error in get_recent_system_events: {str(e)}")
        return []
