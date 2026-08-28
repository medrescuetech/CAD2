"""
Custom decorators for the CAD system API.

This module provides decorators for authentication, authorization, and request control.
"""

from functools import wraps
from flask import jsonify, request, abort, current_app
from flask_login import current_user
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
from models import Permission
from utils.security import rate_limit as security_rate_limit
import time
import json
from datetime import datetime
import inspect

def role_required(*roles):
    """
    Decorator to check if the current user has any of the specified roles.
    
    Args:
        *roles: One or more role names required to access the endpoint
        
    Returns:
        function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                log_audit_event(
                    category=AuditCategory.ACCESS_CONTROL,
                    action="Unauthenticated access attempt",
                    severity=AuditSeverity.WARNING,
                    details={
                        'endpoint': request.endpoint,
                        'method': request.method,
                        'ip': request.remote_addr,
                        'required_roles': roles
                    }
                )
                return jsonify({
                    'success': False,
                    'message': 'Authentication required'
                }), 401
                
            # Check if user has any of the required roles
            def _user_has_role(role_name: str) -> bool:
                # Prefer explicit has_role impl if present
                if hasattr(current_user, 'has_role'):
                    try:
                        return bool(current_user.has_role(role_name))
                    except Exception:
                        pass
                # Common fallback: ADMIN role maps to admin permission
                if role_name.upper() in ('ADMIN', 'ADMINISTRATOR'):
                    if hasattr(current_user, 'is_administrator'):
                        if current_user.is_administrator():
                            return True
                    # Fallback to permission flag
                    try:
                        return bool(current_user.can(Permission.ADMIN))
                    except Exception:
                        return False
                # If user has a single role attribute, compare by name
                if hasattr(current_user, 'role') and getattr(current_user.role, 'name', None):
                    return str(current_user.role.name).lower() == role_name.lower()
                # As last resort, check for roles iterable
                if hasattr(current_user, 'roles'):
                    try:
                        return any(getattr(r, 'name', '').lower() == role_name.lower() for r in current_user.roles)
                    except Exception:
                        return False
                return False

            if not any(_user_has_role(role) for role in roles):
                log_audit_event(
                    category=AuditCategory.ACCESS_CONTROL,
                    action="Insufficient role privileges",
                    severity=AuditSeverity.WARNING,
                    user_id=current_user.id,
                    details={
                        'endpoint': request.endpoint,
                        'method': request.method,
                        'required_roles': roles,
                        'user_roles': [role.name for role in current_user.roles]
                    }
                )
                return jsonify({
                    'success': False,
                    'message': 'Insufficient privileges'
                }), 403
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def permission_required(permission):
    """
    Decorator to check if the current user has the specified permission.
    
    Args:
        permission: The permission flag required to access the endpoint
        
    Returns:
        function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                log_audit_event(
                    category=AuditCategory.ACCESS_CONTROL,
                    action="Unauthenticated access attempt",
                    severity=AuditSeverity.WARNING,
                    details={
                        'endpoint': request.endpoint,
                        'method': request.method,
                        'ip': request.remote_addr,
                        'required_permission': permission
                    }
                )
                return jsonify({
                    'success': False,
                    'message': 'Authentication required'
                }), 401
                
            # Check if user has the required permission
            if not current_user.can(permission):
                log_audit_event(
                    category=AuditCategory.ACCESS_CONTROL,
                    action="Insufficient permission",
                    severity=AuditSeverity.WARNING,
                    user_id=current_user.id,
                    details={
                        'endpoint': request.endpoint,
                        'method': request.method,
                        'required_permission': permission,
                        'user_permissions': current_user.get_permissions() if hasattr(current_user, 'get_permissions') else None
                    }
                )
                return jsonify({
                    'success': False,
                    'message': 'Insufficient privileges'
                }), 403
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def permissions_required(*permissions):
    """
    Decorator to check if the current user has all of the specified permissions.
    
    Args:
        *permissions: One or more permission flags required to access the endpoint
        
    Returns:
        function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                log_audit_event(
                    category=AuditCategory.ACCESS_CONTROL,
                    action="Unauthenticated access attempt",
                    severity=AuditSeverity.WARNING,
                    details={
                        'endpoint': request.endpoint,
                        'method': request.method,
                        'ip': request.remote_addr,
                        'required_permissions': permissions
                    }
                )
                return jsonify({
                    'success': False,
                    'message': 'Authentication required'
                }), 401
                
            # Check if user has all of the required permissions
            missing_permissions = [p for p in permissions if not current_user.can(p)]
            
            if missing_permissions:
                log_audit_event(
                    category=AuditCategory.ACCESS_CONTROL,
                    action="Insufficient permissions",
                    severity=AuditSeverity.WARNING,
                    user_id=current_user.id,
                    details={
                        'endpoint': request.endpoint,
                        'method': request.method,
                        'required_permissions': permissions,
                        'missing_permissions': missing_permissions,
                        'user_permissions': current_user.get_permissions() if hasattr(current_user, 'get_permissions') else None
                    }
                )
                return jsonify({
                    'success': False,
                    'message': 'Insufficient privileges'
                }), 403
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def read_endpoint(limit=None, cache_timeout=None):
    """
    Decorator to mark an endpoint as a read-only operation.
    This can be used for monitoring and analytics to differentiate
    between read and write operations. Can also apply rate limiting
    and caching for improved performance.
    
    Args:
        limit (str, optional): Rate limit in format "count/period" (e.g., "30/minute")
        cache_timeout (int, optional): Cache timeout in seconds
        
    Returns:
        function: Decorated function
    """
    def decorator(f):
        # Mark the function as a read endpoint
        f._is_read_endpoint = True
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Start timing for performance metrics
            start_time = time.time()
            
            # Apply rate limiting if specified
            if limit:
                from utils.middleware import rate_limiter
                rate_limit_decorator = rate_limiter(limit)
                rate_limited_func = rate_limit_decorator(lambda *a, **kw: None)
                result = rate_limited_func(*args, **kwargs)
                if result is not None:
                    return result  # Return rate limit error response
            
            # Check for cache if specified
            if cache_timeout is not None:
                # Generate cache key based on endpoint, args, and kwargs
                cache_key = f"{request.endpoint}:{str(args)}:{str(sorted(kwargs.items()))}"
                
                # Try to get from cache
                from extensions import cache
                cached_response = cache.get(cache_key)
                if cached_response:
                    log_audit_event(
                        category=AuditCategory.API_ACCESS,
                        action=f"Cache hit for {request.endpoint}",
                        severity=AuditSeverity.INFO,
                        user_id=current_user.id if current_user.is_authenticated else None,
                        details={
                            'endpoint': request.endpoint,
                            'method': request.method,
                            'cache_key': cache_key
                        }
                    )
                    return cached_response
            
            # Execute the original function
            response = f(*args, **kwargs)
            
            # Log performance metrics
            duration_ms = round((time.time() - start_time) * 1000, 2)
            log_audit_event(
                category=AuditCategory.API_PERFORMANCE,
                action=f"Read operation completed: {request.endpoint}",
                severity=AuditSeverity.INFO,
                user_id=current_user.id if current_user.is_authenticated else None,
                details={
                    'endpoint': request.endpoint,
                    'method': request.method,
                    'duration_ms': duration_ms,
                    'is_read': True
                }
            )
            
            # Cache the response if specified
            if cache_timeout is not None:
                from extensions import cache
                cache.set(cache_key, response, timeout=cache_timeout)
            
            return response
        return decorated_function
    return decorator

def write_endpoint(limit=None):
    """
    Decorator to mark an endpoint as a write operation.
    This can be used for monitoring and analytics to differentiate
    between read and write operations. Can also apply rate limiting.
    
    Args:
        limit (str, optional): Rate limit in format "count/period" (e.g., "10/minute")
        
    Returns:
        function: Decorated function
    """
    def decorator(f):
        # Mark the function as a write endpoint
        f._is_write_endpoint = True
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Start timing for performance metrics
            start_time = time.time()
            
            # Apply rate limiting if specified
            if limit:
                from utils.middleware import rate_limiter
                rate_limit_decorator = rate_limiter(limit)
                rate_limited_func = rate_limit_decorator(lambda *a, **kw: None)
                result = rate_limited_func(*args, **kwargs)
                if result is not None:
                    return result  # Return rate limit error response
            
            # Execute the original function
            response = f(*args, **kwargs)
            
            # Log performance metrics
            duration_ms = round((time.time() - start_time) * 1000, 2)
            log_audit_event(
                category=AuditCategory.API_PERFORMANCE,
                action=f"Write operation completed: {request.endpoint}",
                severity=AuditSeverity.INFO,
                user_id=current_user.id if current_user.is_authenticated else None,
                details={
                    'endpoint': request.endpoint,
                    'method': request.method,
                    'duration_ms': duration_ms,
                    'is_write': True
                }
            )
            
            return response
        return decorated_function
    return decorator

def api_validation(required_fields=None, optional_fields=None, validation_function=None):
    """
    Decorator to validate API request data.
    
    Args:
        required_fields (list, optional): List of field names that must be present in the request
        optional_fields (list, optional): List of field names that may be present in the request
        validation_function (function, optional): Function to perform custom validation
        
    Returns:
        function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Only validate for JSON requests
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Request must be JSON'
                }), 415
                
            # Get request data
            data = request.get_json()
            
            # Check required fields
            if required_fields:
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    log_audit_event(
                        category=AuditCategory.API_VALIDATION,
                        action="Missing required fields",
                        severity=AuditSeverity.WARNING,
                        user_id=current_user.id if current_user.is_authenticated else None,
                        details={
                            'endpoint': request.endpoint,
                            'method': request.method,
                            'missing_fields': missing_fields
                        }
                    )
                    return jsonify({
                        'success': False,
                        'message': 'Missing required fields',
                        'missing_fields': missing_fields
                    }), 400
            
            # Check for unexpected fields
            if required_fields or optional_fields:
                allowed_fields = (required_fields or []) + (optional_fields or [])
                unexpected_fields = [field for field in data if field not in allowed_fields]
                if unexpected_fields and not current_app.config.get('ALLOW_EXTRA_FIELDS', False):
                    log_audit_event(
                        category=AuditCategory.API_VALIDATION,
                        action="Unexpected fields in request",
                        severity=AuditSeverity.WARNING,
                        user_id=current_user.id if current_user.is_authenticated else None,
                        details={
                            'endpoint': request.endpoint,
                            'method': request.method,
                            'unexpected_fields': unexpected_fields,
                            'allowed_fields': allowed_fields
                        }
                    )
                    return jsonify({
                        'success': False,
                        'message': 'Unexpected fields in request',
                        'unexpected_fields': unexpected_fields,
                        'allowed_fields': allowed_fields
                    }), 400
            
            # Apply custom validation if provided
            if validation_function:
                is_valid, error_message = validation_function(data)
                if not is_valid:
                    log_audit_event(
                        category=AuditCategory.API_VALIDATION,
                        action="Custom validation failed",
                        severity=AuditSeverity.WARNING,
                        user_id=current_user.id if current_user.is_authenticated else None,
                        details={
                            'endpoint': request.endpoint,
                            'method': request.method,
                            'error_message': error_message
                        }
                    )
                    return jsonify({
                        'success': False,
                        'message': error_message
                    }), 400
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Reuse the rate_limit function from security.py
rate_limit = security_rate_limit
