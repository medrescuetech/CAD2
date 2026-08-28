"""
Audit Logging Utility

This module provides functions for creating security audit logs for important events
in the CAD system. It captures detailed information about user actions, API access,
authentication events, and other security-critical operations.
"""

import logging
from flask import request, current_app, g
from datetime import datetime
import json
import uuid
from functools import wraps

# Set up a dedicated logger for audit events
audit_logger = logging.getLogger('audit_log')

# Event categories
class AuditCategory:
    """Categories for audit log events."""
    AUTHENTICATION = "AUTHENTICATION"  # Login, logout, password changes
    ACCESS_CONTROL = "ACCESS_CONTROL"  # Permission checks, access denials
    DATA_ACCESS = "DATA_ACCESS"        # Reading sensitive data
    DATA_MODIFICATION = "DATA_MODIFICATION"  # Creating, updating, deleting data
    CONFIGURATION = "CONFIGURATION"    # System configuration changes
    API_ACCESS = "API_ACCESS"          # API endpoint access
    SECURITY = "SECURITY"              # Security-related events
    ADMIN = "ADMIN"                    # Administrative actions
    SYSTEM = "SYSTEM"                  # System-level events
    REQUEST = "REQUEST"                # Incoming HTTP requests
    RESPONSE = "RESPONSE"              # Outgoing HTTP responses
    ERROR = "ERROR"                    # Error events

# Severity levels
class AuditSeverity:
    """Severity levels for audit log events."""
    INFO = "INFO"           # Routine operations
    WARNING = "WARNING"     # Unusual but not critical events
    ERROR = "ERROR"         # Errors that might indicate security issues
    CRITICAL = "CRITICAL"   # Serious security concerns

def log_audit_event(category, action, severity=AuditSeverity.INFO, details=None, user_id=None, resource_id=None, resource_type=None):
    """
    Log an audit event to the audit log.
    
    Args:
        category (str): Event category from AuditCategory
        action (str): Description of the action
        severity (str): Severity level from AuditSeverity
        details (dict): Additional details about the event
        user_id (int): ID of the user who performed the action
        resource_id (str): ID of the resource being accessed/modified
        resource_type (str): Type of resource being accessed/modified
    """
    try:
        # Get request information if available
        request_id = str(uuid.uuid4())
        ip_address = None
        user_agent = None
        endpoint = None
        
        if request:
            ip_address = request.remote_addr
            
            # Fix: Get string representation of user_agent
            if request.user_agent:
                try:
                    user_agent = request.user_agent.string
                except (AttributeError, TypeError):
                    # Fallback to str() if string property is not available
                    user_agent = str(request.user_agent)
            
            endpoint = request.endpoint
            
            # Use existing request ID if available
            if hasattr(g, 'request_id'):
                request_id = g.request_id
        
        # Make sure details is JSON serializable
        if details:
            # Convert any non-serializable objects to strings
            serializable_details = {}
            for key, value in details.items():
                try:
                    # Test if it's JSON serializable
                    json.dumps({key: value})
                    serializable_details[key] = value
                except (TypeError, OverflowError):
                    # If not serializable, convert to string
                    serializable_details[key] = str(value)
            details = serializable_details
        
        # Construct the audit log entry
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'request_id': request_id,
            'category': category,
            'action': action,
            'severity': severity,
            'user_id': user_id,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'endpoint': endpoint,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'details': details or {}
        }
        
        # Log the entry as JSON
        audit_logger.info(json.dumps(log_entry))
        
        # For critical events, also log to the application logger
        if severity == AuditSeverity.CRITICAL:
            app_logger = logging.getLogger('app')
            app_logger.critical(f"SECURITY ALERT: {action} - {json.dumps(details or {})}")
        
        # Store in database if configured
        if current_app.config.get('AUDIT_LOG_TO_DB', False):
            try:
                from models import AuditLog, db
                
                audit_db_entry = AuditLog(
                    request_id=request_id,
                    timestamp=datetime.utcnow(),
                    category=category,
                    action=action,
                    severity=severity,
                    user_id=user_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    endpoint=endpoint,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    details=json.dumps(details or {})
                )
                
                db.session.add(audit_db_entry)
                db.session.commit()
            except Exception as e:
                # Don't let database issues prevent logging
                logging.getLogger('error').error(f"Failed to save audit log to database: {str(e)}")
    except Exception as e:
        # Don't let logging errors crash the application
        logging.getLogger('logging').error(f"Error logging activity: {str(e)}")

def audit_access(category, action, severity=AuditSeverity.INFO, resource_type=None):
    """
    Decorator to audit access to resources.
    
    Args:
        category (str): Event category from AuditCategory
        action (str): Description of the action
        severity (str): Severity level from AuditSeverity
        resource_type (str): Type of resource being accessed
    
    Returns:
        function: Decorated function
    """
    def decorator(view_function):
        @wraps(view_function)
        def decorated_function(*args, **kwargs):
            # Extract user ID if available
            from flask_login import current_user
            user_id = current_user.id if current_user and current_user.is_authenticated else None
            
            # Extract resource ID from kwargs if possible
            resource_id = None
            for key in kwargs:
                if key.endswith('_id'):
                    resource_id = kwargs[key]
                    break
            
            # Log the audit event before executing the function
            log_audit_event(
                category=category,
                action=action,
                severity=severity,
                user_id=user_id,
                resource_id=resource_id,
                resource_type=resource_type
            )
            
            # Execute the function
            return view_function(*args, **kwargs)
        
        return decorated_function
    
    return decorator

# Common audit functions for frequent security events
def audit_login(user_id, success=True, details=None):
    """Audit a login attempt."""
    action = "User login successful" if success else "User login failed"
    severity = AuditSeverity.INFO if success else AuditSeverity.WARNING
    
    log_audit_event(
        category=AuditCategory.AUTHENTICATION,
        action=action,
        severity=severity,
        user_id=user_id,
        details=details
    )

def audit_logout(user_id):
    """Audit a user logout."""
    log_audit_event(
        category=AuditCategory.AUTHENTICATION,
        action="User logout",
        severity=AuditSeverity.INFO,
        user_id=user_id
    )

def audit_password_change(user_id, admin_action=False):
    """Audit a password change."""
    action = "Password changed by administrator" if admin_action else "Password changed by user"
    
    log_audit_event(
        category=AuditCategory.AUTHENTICATION,
        action=action,
        severity=AuditSeverity.INFO,
        user_id=user_id
    )

def audit_permission_denied(user_id, permission, resource_type=None, resource_id=None):
    """Audit a permission denial."""
    log_audit_event(
        category=AuditCategory.ACCESS_CONTROL,
        action="Permission denied",
        severity=AuditSeverity.WARNING,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        details={
            'permission': permission
        }
    )

def audit_api_key_usage(key_prefix, endpoint, success=True):
    """Audit API key usage."""
    action = "API key used successfully" if success else "API key usage failed"
    severity = AuditSeverity.INFO if success else AuditSeverity.WARNING
    
    log_audit_event(
        category=AuditCategory.API_ACCESS,
        action=action,
        severity=severity,
        details={
            'key_prefix': key_prefix,
            'endpoint': endpoint
        }
    )

def audit_configuration_change(user_id, setting, old_value=None, new_value=None):
    """Audit a configuration change."""
    log_audit_event(
        category=AuditCategory.CONFIGURATION,
        action="Configuration setting changed",
        severity=AuditSeverity.INFO,
        user_id=user_id,
        details={
            'setting': setting,
            'old_value': old_value,
            'new_value': new_value
        }
    )

def audit_role_change(user_id, target_user_id, old_role=None, new_role=None):
    """Audit a role change for a user."""
    log_audit_event(
        category=AuditCategory.ADMIN,
        action="User role changed",
        severity=AuditSeverity.INFO,
        user_id=user_id,
        resource_id=target_user_id,
        resource_type="user",
        details={
            'old_role': old_role,
            'new_role': new_role
        }
    )

def audit_data_export(user_id, data_type, record_count=None, filters=None):
    """Audit a data export operation."""
    log_audit_event(
        category=AuditCategory.DATA_ACCESS,
        action="Data exported",
        severity=AuditSeverity.INFO,
        user_id=user_id,
        resource_type=data_type,
        details={
            'record_count': record_count,
            'filters': filters
        }
    )

def audit_system_startup():
    """Audit system startup."""
    log_audit_event(
        category=AuditCategory.SYSTEM,
        action="System startup",
        severity=AuditSeverity.INFO
    )

def audit_system_shutdown():
    """Audit system shutdown."""
    log_audit_event(
        category=AuditCategory.SYSTEM,
        action="System shutdown",
        severity=AuditSeverity.INFO
    )
