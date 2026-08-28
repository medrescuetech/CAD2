"""
API Authentication Utilities

This module provides utilities for authenticating API requests using API keys.
"""

from functools import wraps
from flask import request, jsonify, current_app, g
from models import APIKey
from utils.audit_log import audit_api_key_usage, log_audit_event, AuditCategory, AuditSeverity
from datetime import datetime, timezone

def get_api_key_from_request():
    """
    Extract API key from request headers or query parameters.
    
    Returns:
        str: API key or None if not found
    """
    # First check Authorization header
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('ApiKey '):
        return auth_header.split(' ')[1].strip()
    
    # Then check X-API-Key header
    api_key = request.headers.get('X-API-Key')
    if api_key:
        return api_key.strip()
    
    # Finally check query parameter
    api_key = request.args.get('api_key')
    if api_key:
        return api_key.strip()
    
    return None

def validate_api_key(key, required_permissions=None):
    """
    Validate an API key and check if it has the required permissions.
    
    Args:
        key (str): The API key to validate
        required_permissions (int, optional): Permission bitmask required for this request
        
    Returns:
        tuple: (bool, APIKey or None) - (is_valid, api_key_object)
    """
    if not key:
        return False, None
    
    try:
        # Check if key exists and is valid
        prefix = key[:8]  # Assuming 8-char prefix - adjust if different in your APIKey model
        api_key_obj = APIKey.query.filter_by(key_prefix=prefix, active=True).first()
        
        if not api_key_obj:
            # Log unauthorized access attempt
            log_audit_event(
                category=AuditCategory.API_ACCESS,
                action="Invalid API key prefix used",
                severity=AuditSeverity.WARNING,
                details={'key_prefix': prefix}
            )
            return False, None
            
        # Check if the key is expired
        if api_key_obj.expires_at and api_key_obj.expires_at < datetime.now(timezone.utc):
            # Log expired key usage
            log_audit_event(
                category=AuditCategory.API_ACCESS,
                action="Expired API key used",
                severity=AuditSeverity.WARNING,
                details={'key_prefix': prefix, 'expired_at': api_key_obj.expires_at.isoformat()}
            )
            return False, None
            
        # Verify the key hash
        if not api_key_obj.verify_key(key):
            # Log key validation failure
            log_audit_event(
                category=AuditCategory.API_ACCESS,
                action="API key validation failed",
                severity=AuditSeverity.WARNING,
                details={'key_prefix': prefix}
            )
            return False, None
            
        # Check permissions if specified
        if required_permissions is not None and not api_key_obj.permissions & required_permissions:
            # Log insufficient permissions
            log_audit_event(
                category=AuditCategory.ACCESS_CONTROL,
                action="API key has insufficient permissions",
                severity=AuditSeverity.WARNING,
                details={
                    'key_prefix': prefix, 
                    'required_permissions': required_permissions,
                    'actual_permissions': api_key_obj.permissions
                }
            )
            return False, None
            
        # Update last used timestamp
        api_key_obj.last_used_at = datetime.now(timezone.utc)
        from models import db
        db.session.commit()
        
        # Log successful API key usage
        audit_api_key_usage(prefix, request.endpoint, True)
        
        return True, api_key_obj
        
    except Exception as e:
        current_app.logger.error(f"Error validating API key: {str(e)}")
        # Log validation error
        log_audit_event(
            category=AuditCategory.API_ACCESS,
            action="API key validation error",
            severity=AuditSeverity.ERROR,
            details={'error': str(e)}
        )
        return False, None

def require_api_key(permissions=None):
    """
    Decorator to require a valid API key for accessing an endpoint.
    
    Args:
        permissions (int, optional): Permission bitmask required for this request
    
    Returns:
        function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            api_key = get_api_key_from_request()
            
            if not api_key:
                # Log missing API key
                log_audit_event(
                    category=AuditCategory.API_ACCESS,
                    action="API request without API key",
                    severity=AuditSeverity.WARNING,
                    details={'endpoint': request.endpoint}
                )
                return jsonify({
                    'success': False,
                    'message': 'API key is required'
                }), 401
                
            is_valid, key_obj = validate_api_key(api_key, permissions)
            
            if not is_valid:
                return jsonify({
                    'success': False,
                    'message': 'Invalid or insufficient permissions for API key'
                }), 403
                
            # Store API key object in request context
            g.api_key = key_obj
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def with_api_key(permissions=None):
    """
    Decorator to optionally use an API key if provided, but not require it.
    
    This decorator allows endpoints to be accessed with or without an API key.
    If a key is provided, it will be validated and made available in the request context.
    
    Args:
        permissions (int, optional): Permission bitmask required if a key is provided
    
    Returns:
        function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            api_key = get_api_key_from_request()
            
            if api_key:
                is_valid, key_obj = validate_api_key(api_key, permissions)
                
                if is_valid:
                    # Store API key object in request context
                    g.api_key = key_obj
                else:
                    # Invalid key provided, but key is optional, so continue
                    # Just log the invalid key attempt
                    log_audit_event(
                        category=AuditCategory.API_ACCESS,
                        action="Invalid API key provided to optional endpoint",
                        severity=AuditSeverity.INFO,
                        details={'endpoint': request.endpoint}
                    )
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
