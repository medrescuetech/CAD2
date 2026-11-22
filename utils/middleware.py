"""
Middleware Utilities

This module provides middleware functions for the CAD system.
"""

from flask import request, jsonify, g, current_app, session, abort
from functools import wraps
from utils.api_auth import get_api_key_from_request, validate_api_key
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
from models import Permission, User
import re
import time
import json
from datetime import datetime
from werkzeug.exceptions import HTTPException
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError
from extensions import limiter

def setup_api_middleware(app):
    """
    Setup middleware for API routes.
    
    This function adds before_request handlers to apply middleware to specific route patterns.
    
    Args:
        app: Flask application
    """
    @app.before_request
    def api_key_auth():
        """Check API key authentication for API routes."""
        # Only apply to API routes
        if not _is_api_route(request.path):
            return
            
        # Skip authentication for OPTIONS requests (CORS preflight)
        if request.method == 'OPTIONS':
            return
            
        # Skip authentication for public API routes
        if _is_public_api_route(request.path):
            return
            
        # Get API key from request
        api_key = get_api_key_from_request()
        
        # If no API key provided, check if user is authenticated
        if not api_key:
            # User not authenticated via API key, check session
            from flask_login import current_user
            if not current_user.is_authenticated:
                return jsonify({
                    'success': False,
                    'message': 'Authentication required'
                }), 401
            return
        
        # Validate API key (without specific permission checks - those happen at the route level)
        is_valid, key_obj = validate_api_key(api_key)
        
        if not is_valid:
            return jsonify({
                'success': False,
                'message': 'Invalid API key'
            }), 403
        
        # Store API key object in request context
        g.api_key = key_obj
        g.api_user = None
        
        # If API key is associated with a user, set the user context
        if key_obj.created_by_id:
            g.api_user = User.query.get(key_obj.created_by_id)
    
    @app.before_request
    def log_api_request():
        """Log API requests to audit log."""
        # Only apply to API routes
        if not _is_api_route(request.path):
            return
            
        # Get user ID from session or API key
        user_id = None
        from flask_login import current_user
        
        if current_user.is_authenticated:
            user_id = current_user.id
        elif hasattr(g, 'api_user') and g.api_user:
            user_id = g.api_user.id
        
        # Add request start time for performance tracking
        g.request_start_time = time.time()
        
        # Create audit log entry
        log_audit_event(
            category=AuditCategory.API_ACCESS,
            action=f"API request: {request.method} {request.path}",
            severity=AuditSeverity.INFO,
            user_id=user_id,
            details={
                'method': request.method,
                'path': request.path,
                'query_params': dict(request.args),
                'remote_addr': request.remote_addr,
                'api_key_used': hasattr(g, 'api_key'),
                'user_agent': request.headers.get('User-Agent', 'Unknown')
            }
        )
    
    @app.before_request
    def validate_request_data():
        """Validate request data for API routes."""
        # Only apply to API routes with JSON data
        if not _is_api_route(request.path) or not request.is_json:
            return
        
        # Check content type
        if request.method in ['POST', 'PUT', 'PATCH'] and not request.headers.get('Content-Type', '').startswith('application/json'):
            return jsonify({
                'success': False,
                'message': 'Content-Type must be application/json'
            }), 415
        
        # Check request body size
        max_length = current_app.config.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024)
        if request.content_length and max_length is not None and request.content_length > max_length:
            return jsonify({
                'success': False,
                'message': 'Request body too large'
            }), 413
            
        # Validate JSON format
        try:
            if request.data:
                request.get_json()
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Invalid JSON format',
                'error': str(e)
            }), 400
    
    @app.before_request
    def check_csrf_token():
        """Check CSRF token for API routes that modify data."""
        # Only apply to non-GET/HEAD API routes that aren't public
        if not _is_api_route(request.path) or request.method in ['GET', 'HEAD', 'OPTIONS'] or _is_public_api_route(request.path):
            return
            
        # Skip CSRF check if using API key authentication
        if hasattr(g, 'api_key'):
            return
            
        # Check CSRF token in header or form data. The client sends the
        # signed Flask-WTF token (csrf_token() in base.html), not the raw
        # session secret — validate it the same way CSRFProtect does.
        csrf_token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
        try:
            validate_csrf(csrf_token)
            valid = True
        except ValidationError:
            valid = False
        if not valid:
            log_audit_event(
                category=AuditCategory.SECURITY,
                action="CSRF token validation failed",
                severity=AuditSeverity.WARNING,
                details={
                    'method': request.method,
                    'path': request.path,
                    'remote_addr': request.remote_addr
                }
            )
            return jsonify({
                'success': False,
                'message': 'CSRF token validation failed'
            }), 403
    
    @app.after_request
    def add_security_headers(response):
        """Add security headers to response."""
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Add CORS headers
        if _is_api_route(request.path):
            response.headers['Access-Control-Allow-Origin'] = current_app.config.get('CORS_ORIGIN', '*')
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key, X-CSRF-Token'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
        
        return response
    
    @app.after_request
    def log_api_response(response):
        """Log API responses to audit log."""
        # Only apply to API routes
        if not _is_api_route(request.path):
            return response
            
        # Calculate request duration
        duration = None
        if hasattr(g, 'request_start_time'):
            duration = round((time.time() - g.request_start_time) * 1000, 2)  # in ms
            
        # Get user ID from session or API key
        user_id = None
        from flask_login import current_user
        
        if current_user.is_authenticated:
            user_id = current_user.id
        elif hasattr(g, 'api_user') and g.api_user:
            user_id = g.api_user.id
            
        # Determine severity based on status code
        severity = AuditSeverity.INFO
        if response.status_code >= 400:
            severity = AuditSeverity.WARNING
        if response.status_code >= 500:
            severity = AuditSeverity.ERROR
            
        # Create audit log entry
        log_audit_event(
            category=AuditCategory.API_ACCESS,
            action=f"API response: {request.method} {request.path} ({response.status_code})",
            severity=severity,
            user_id=user_id,
            details={
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'duration_ms': duration,
                'content_length': response.content_length
            }
        )
        
        return response
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        """Handle exceptions and return appropriate API responses."""
        # Only handle exceptions for API routes
        if not _is_api_route(request.path):
            # Re-raise the exception for non-API routes
            raise e
            
        # Get user ID from session or API key
        user_id = None
        from flask_login import current_user
        
        if current_user.is_authenticated:
            user_id = current_user.id
        elif hasattr(g, 'api_user') and g.api_user:
            user_id = g.api_user.id
            
        # Handle HTTPExceptions
        if isinstance(e, HTTPException):
            log_audit_event(
                category=getattr(AuditCategory, 'API_ERROR', AuditCategory.SECURITY),
                action=f"HTTP error: {e.code} - {e.name}",
                severity=AuditSeverity.WARNING,
                user_id=user_id,
                details={
                    'method': request.method,
                    'path': request.path,
                    'error_code': e.code,
                    'error_name': e.name,
                    'description': e.description
                }
            )
            
            return jsonify({
                'success': False,
                'message': e.description,
                'error_code': e.code,
                'error_name': e.name
            }), e.code
            
        # Handle other exceptions
        log_audit_event(
            category=getattr(AuditCategory, 'API_ERROR', AuditCategory.SECURITY),
            action=f"Server error: {str(e)}",
            severity=AuditSeverity.ERROR,
            user_id=user_id,
            details={
                'method': request.method,
                'path': request.path,
                'error_type': type(e).__name__,
                'error_message': str(e)
            }
        )
        
        # In production, don't expose the actual error message
        if current_app.config.get('ENV') == 'production':
            error_message = "An internal server error occurred."
        else:
            error_message = str(e)
            
        return jsonify({
            'success': False,
            'message': error_message,
            'error_type': type(e).__name__
        }), 500

def _is_api_route(path):
    """
    Check if a route is an API route.
    
    Args:
        path (str): Request path
        
    Returns:
        bool: True if API route, False otherwise
    """
    api_patterns = [
        r'^/api/',
        r'^/audit/',
    ]
    
    return any(re.match(pattern, path) for pattern in api_patterns)

def _is_public_api_route(path):
    """
    Check if a route is a public API route that doesn't require authentication.
    
    Args:
        path (str): Request path
        
    Returns:
        bool: True if public API route, False otherwise
    """
    public_patterns = [
        r'^/api/auth/',
        r'^/api/public/',
        r'^/api/docs/',
    ]
    
    return any(re.match(pattern, path) for pattern in public_patterns)

def api_key_required(permissions=None):
    """
    Decorator to require a valid API key for accessing an endpoint.
    This is different from the require_api_key decorator in api_auth.py
    as it integrates with the middleware and also checks for user authentication.
    
    Args:
        permissions (int, optional): Permission bitmask required for this request
    
    Returns:
        function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if user is authenticated via API key
            api_key = getattr(g, 'api_key', None)
            
            if api_key:
                # Check if API key has required permissions
                if permissions and not api_key.permissions & permissions:
                    log_audit_event(
                        category=AuditCategory.ACCESS_CONTROL,
                        action="API key has insufficient permissions",
                        severity=AuditSeverity.WARNING,
                        details={
                            'key_prefix': api_key.key_prefix, 
                            'required_permissions': permissions,
                            'actual_permissions': api_key.permissions,
                            'endpoint': request.endpoint
                        }
                    )
                    return jsonify({
                        'success': False,
                        'message': 'Insufficient permissions for API key'
                    }), 403
                
                # API key is valid and has required permissions
                return f(*args, **kwargs)
            
            # If no API key, check if user is authenticated via session
            from flask_login import current_user
            if not current_user.is_authenticated:
                return jsonify({
                    'success': False,
                    'message': 'Authentication required'
                }), 401
            
            # Check if user has required permissions
            if permissions and not current_user.can(permissions):
                log_audit_event(
                    category=AuditCategory.ACCESS_CONTROL,
                    action="User has insufficient permissions",
                    severity=AuditSeverity.WARNING,
                    user_id=current_user.id,
                    details={
                        'required_permissions': permissions,
                        'endpoint': request.endpoint
                    }
                )
                return jsonify({
                    'success': False,
                    'message': 'Insufficient permissions'
                }), 403
            
            # User is authenticated and has required permissions
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def rate_limiter(limit_string):
    """
    Decorator to apply rate limiting to a route.
    
    Args:
        limit_string (str): Rate limit string e.g. "5 per minute", "100 per day"
    
    Returns:
        function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Apply rate limit
            try:
                from flask import request
                if not limiter.check():  # Method doesn't take the limit_string parameter directly
                    # Rate limit exceeded
                    log_audit_event(
                        category=AuditCategory.RATE_LIMIT,
                        action="Rate limit exceeded",
                        severity=AuditSeverity.WARNING,
                        details={
                            'method': request.method,
                            'path': request.path,
                            'remote_addr': request.remote_addr,
                            'limit': limit_string
                        }
                    )
                    return jsonify({
                        'success': False,
                        'message': 'Rate limit exceeded'
                    }), 429
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': 'Error applying rate limit',
                    'error': str(e)
                }), 500
            
            # Rate limit not exceeded
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def validate_json_schema(schema):
    """
    Decorator to validate request JSON against a schema.
    
    Args:
        schema (dict): JSON schema to validate against
        
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
            
            try:
                from jsonschema import validate, ValidationError
                data = request.get_json()
                
                # Validate JSON against schema
                validate(instance=data, schema=schema)
                
                # JSON is valid
                return f(*args, **kwargs)
            except ValidationError as e:
                return jsonify({
                    'success': False,
                    'message': 'Invalid request data',
                    'error': str(e)
                }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': 'Error validating request data',
                    'error': str(e)
                }), 400
                
        return decorated_function
    return decorator
