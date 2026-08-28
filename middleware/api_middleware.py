"""
API Middleware for the CAD System.

This module provides middleware components for API request processing,
including authentication, request validation, and response formatting.
"""

from flask import request, g, jsonify, current_app
from functools import wraps
import time
import json
from werkzeug.exceptions import HTTPException

from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
from utils.security import validate_api_key
from models import User, APIKey

def setup_middleware(app):
    """Set up API middleware components.
    
    Args:
        app: Flask application instance
    """
    @app.before_request
    def setup_request_context():
        """Set up request context for all requests."""
        # Only set up timing if not already set by another middleware
        if not hasattr(g, 'start_time') and not hasattr(g, 'request_start_time'):
            g.request_start_time = time.time()
            g.start_time = g.request_start_time  # For compatibility with other middleware
            
        # Set request ID if not already set
        if not hasattr(g, 'request_id') and 'X-Request-ID' in request.headers:
            g.request_id = request.headers.get('X-Request-ID')
            
        # Log API requests at debug level to avoid duplicate logs
        if request.path.startswith('/api/'):
            current_app.logger.debug(f"API Request: {request.method} {request.path} - IP: {request.remote_addr}")
    
    @app.before_request
    def authenticate_request():
        """Authenticate API requests."""
        # Skip non-API routes
        if not request.path.startswith('/api/'):
            return
            
        # Handle CORS preflight
        if request.method == 'OPTIONS':
            return
            
        # Skip authentication for public endpoints
        if _is_public_endpoint(request.path):
            return
            
        # Check for API key in headers or query params
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if api_key:
            # Validate API key
            key = APIKey.query.filter_by(key=api_key, is_active=True).first()
            
            if not key or not key.is_valid():
                return jsonify({
                    'success': False,
                    'error': 'invalid_api_key',
                    'message': 'Invalid or expired API key'
                }), 401
                
            # Check if key has required permissions for this endpoint
            if not key.has_permission_for_path(request.path, request.method):
                return jsonify({
                    'success': False,
                    'error': 'insufficient_permissions',
                    'message': 'Insufficient permissions for this endpoint'
                }), 403
                
            # Store API key and user in request context
            g.api_key = key
            g.current_user = key.user
            
            # Log API key usage
            log_audit_event(
                category=AuditCategory.API_ACCESS,
                action=f"API key used: {key.name}",
                severity=AuditSeverity.INFO,
                user_id=key.user_id,
                details={
                    'endpoint': request.path,
                    'method': request.method,
                    'key_id': key.id,
                    'key_name': key.name
                }
            )
        else:
            # Fall back to session-based auth
            from flask_login import current_user
            if not current_user.is_authenticated:
                return jsonify({
                    'success': False,
                    'error': 'authentication_required',
                    'message': 'API key or login required'
                }), 401
            g.current_user = current_user
    
    @app.before_request
    def validate_json():
        """Validate JSON request body."""
        if not request.path.startswith('/api/'):
            return
            
        if request.method in ('POST', 'PUT', 'PATCH') and request.content_type == 'application/json':
            try:
                # Parse and store JSON data
                if request.get_data():
                    g.json_data = request.get_json(force=True)
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': 'invalid_json',
                    'message': 'Invalid JSON in request body',
                    'details': str(e)
                }), 400
    
    @app.after_request
    def log_response(response):
        """Log API responses."""
        # Only process API routes
        if not request.path.startswith('/api/'):
            return response
            
        # Calculate request duration
        start_time = g.get('request_start_time', g.get('start_time', time.time()))
        duration = time.time() - start_time
        
        # Log response at appropriate level
        if response.status_code >= 400:
            log_level = current_app.logger.warning
        else:
            log_level = current_app.logger.debug
            
        log_msg = f"API Response: {request.method} {request.path} - Status: {response.status_code} - Duration: {duration:.3f}s"
        if hasattr(g, 'request_id'):
            log_msg += f" - ID: {g.request_id}"
            
        log_level(log_msg)
        
        # Prepare audit log data
        log_data = {
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'content_type': response.content_type,
            'content_length': response.content_length or 0,
            'duration_ms': round(duration * 1000, 2)
        }
        
        # Add request ID if available
        if hasattr(g, 'request_id'):
            log_data['request_id'] = g.request_id
        
        # Only include response body for error responses and non-sensitive endpoints
        if (response.status_code >= 400 and 
            not _is_sensitive_endpoint(request.path) and
            response.content_length and 
            response.content_length < 1024 * 10):  # Limit response body size
            
            try:
                if response.is_json:
                    log_data['response_body'] = response.get_json()
                elif response.content_type == 'text/plain':
                    log_data['response_body'] = response.get_data(as_text=True)[:1000]  # Limit length
            except Exception as e:
                current_app.logger.debug(f"Failed to parse response body: {e}")
        
        # Log the audit event
        log_audit_event(
            category=AuditCategory.API_ACCESS,
            action=f"API response: {request.method} {request.path} ({response.status_code})",
            severity=AuditSeverity.INFO if response.status_code < 400 else AuditSeverity.WARNING,
            details=log_data
        )
        
        return response
    
    @app.after_request
    def format_response(response):
        """Format API responses consistently."""
        if not request.path.startswith('/api/'):
            return response
            
        # Skip for error responses
        if response.status_code >= 400:
            return response
            
        # Don't process if already JSON
        if response.is_json:
            return response
            
        # Convert string responses to JSON
        if response.is_sequence and not response.is_streamed:
            try:
                data = json.loads(response.get_data(as_text=True))
                response.set_data(json.dumps({
                    'success': True,
                    'data': data
                }))
                response.content_type = 'application/json'
            except (ValueError, TypeError):
                pass
                
        return response
    
    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        """Handle HTTP errors with JSON responses."""
        if not request.path.startswith('/api/'):
            return error
            
        response = {
            'success': False,
            'error': error.name.lower().replace(' ', '_'),
            'message': error.description,
        }
        
        if current_app.debug:
            response['traceback'] = getattr(error, 'traceback', None)
            
        return jsonify(response), error.code

def _is_sensitive_endpoint(path):
    """Check if the given path is a sensitive endpoint that should not be logged.
    
    Args:
        path: The request path to check
        
    Returns:
        bool: True if the endpoint is sensitive, False otherwise
    """
    sensitive_paths = [
        '/api/auth/password',
        '/api/auth/token',
        '/api/auth/change-password',
        '/api/users/password',
        '/api/keys',
        '/api/credentials'
    ]
    return any(path.startswith(p) for p in sensitive_paths)

def _is_public_endpoint(path):
    """Check if the given path is a public API endpoint."""
    public_paths = [
        '/api/auth/login',
        '/api/auth/refresh',
        '/api/status',
        '/api/version',
        '/api/docs',
        '/api/spec.json',
        '/api/spec',
        '/api/client-logs'
    ]
    return any(path.startswith(p) for p in public_paths)

def require_permission(permission_name):
    """Decorator to require a specific permission for an endpoint."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(g, 'current_user') or not g.current_user:
                return jsonify({
                    'success': False,
                    'error': 'authentication_required',
                    'message': 'Authentication required'
                }), 401
                
            if not g.current_user.has_permission(permission_name):
                return jsonify({
                    'success': False,
                    'error': 'permission_denied',
                    'message': f'Missing required permission: {permission_name}'
                }), 403
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator
