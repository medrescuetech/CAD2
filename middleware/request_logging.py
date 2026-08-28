"""
Request Logging Middleware for the CAD System.

This module provides request logging functionality to track and log
incoming requests and outgoing responses.
"""

from flask import request, g, current_app
import time
import json
from datetime import datetime
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity

def setup_request_logging(app):
    """Set up request logging for the application.
    
    Args:
        app: Flask application instance
    """
    # Only set up logging if it hasn't been set up already
    if hasattr(app, '_request_logging_setup'):
        return
        
    app._request_logging_setup = True
    
    @app.before_request
    def log_request_start():
        """Log the start of each request."""
        # Skip logging for static files and health checks
        if request.path.startswith('/static/') or request.path == '/health':
            return
            
        # Set start time for request timing if not already set
        if not hasattr(g, 'start_time'):
            g.start_time = time.time()
        
        # Log request details at debug level to avoid duplicate logs
        if not request.path.startswith('/api/'):  # Skip API logs as they're handled by api_middleware
            current_app.logger.debug(f"Request: {request.method} {request.path} - IP: {request.remote_addr}")
            
            log_data = {
                'method': request.method,
                'path': request.path,
                'remote_addr': request.remote_addr,
                'user_agent': request.user_agent.string if request.user_agent else None,
                'content_type': request.content_type,
                'content_length': request.content_length or 0,
                'query_string': dict(request.args)
            }
            
            # Log request body for non-GET requests (except for sensitive endpoints)
            if request.method in ('POST', 'PUT', 'PATCH') and not _is_sensitive_endpoint(request.path):
                try:
                    if request.is_json:
                        log_data['request_body'] = request.get_json()
                    elif request.form:
                        log_data['form_data'] = dict(request.form)
                except Exception as e:
                    current_app.logger.debug(f"Failed to parse request body: {e}")
            
            # Log the request
            log_audit_event(
                category=AuditCategory.REQUEST,
                action=f"{request.method} {request.path}",
                severity=AuditSeverity.INFO,
                details=log_data
            )
    
    @app.after_request
    def log_request_complete(response):
        """Log the completion of each request with timing information."""
        # Skip logging for static files and health checks
        if request.path.startswith('/static/') or request.path == '/health':
            return response
            
        # Calculate request duration
        duration = time.time() - getattr(g, 'start_time', time.time())
        
        # Prepare response data
        log_data = {
            'status_code': response.status_code,
            'content_type': response.content_type,
            'content_length': response.content_length or 0,
            'duration_seconds': round(duration, 4)
        }
        
        # Add request ID if available
        if hasattr(g, 'request_id'):
            log_data['request_id'] = g.request_id
        
        # Log response body for errors (except for sensitive endpoints)
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
                current_app.logger.warning(f"Failed to parse response body: {e}")
        
        # Add duration to log data
        log_data['duration_seconds'] = round(duration, 4)
        
        # Log the response
        log_audit_event(
            category=AuditCategory.RESPONSE,
            action=f"{request.method} {request.path} -> {response.status_code}",
            severity=_get_severity_for_status(response.status_code),
            details=log_data
        )
        
        # Add request timing header
        response.headers['X-Request-Duration'] = f"{duration:.4f}s"
        
        return response
    
    @app.teardown_request
    def log_request_error(error):
        """Log any errors that occur during request processing."""
        if error is not None:
            log_audit_event(
                category=AuditCategory.ERROR,
                action=f"Error in {request.method} {request.path}",
                severity=AuditSeverity.ERROR,
                details={
                    'error': str(error),
                    'error_type': error.__class__.__name__,
                    'request_path': request.path,
                    'request_method': request.method,
                    'remote_addr': request.remote_addr,
                    'user_agent': request.user_agent.string,
                    'traceback': _get_traceback()
                }
            )

def _is_sensitive_endpoint(path):
    """Check if an endpoint contains sensitive data that shouldn't be logged."""
    sensitive_paths = [
        '/api/auth/',
        '/api/users/password',
        '/api/tokens',
        '/api/keys',
    ]
    return any(path.startswith(p) for p in sensitive_paths)

def _get_severity_for_status(status_code):
    """Determine the severity level based on HTTP status code."""
    if status_code < 400:
        return AuditSeverity.INFO
    elif status_code < 500:
        return AuditSeverity.WARNING
    else:
        return AuditSeverity.ERROR

def _get_traceback():
    """Get the current exception's traceback as a string."""
    import traceback
    import sys
    
    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type is None:
        return None
        
    return '\n'.join(traceback.format_exception(exc_type, exc_value, exc_tb))
