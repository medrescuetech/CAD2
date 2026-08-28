"""
Security utilities for the CAD system.

This module provides security-related utilities such as CSRF protection helpers,
API key validation, and rate limiting functionality.
"""

from flask import current_app, session, request, jsonify
from flask_wtf.csrf import generate_csrf, validate_csrf, CSRFError
from functools import wraps
import time
from threading import Lock

# Dictionary to store request counts for rate limiting
rate_limit_data = {}
rate_limit_lock = Lock()

def get_csrf_token():
    """
    Generate a CSRF token for the current session.
    
    Returns:
        str: CSRF token
    """
    return generate_csrf()

def ajax_csrf_protect(view_function):
    """
    Decorator to check CSRF token in AJAX requests.
    
    Args:
        view_function: The view function to protect
        
    Returns:
        function: Decorated function
    """
    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        # Skip CSRF check if testing or explicitly disabled
        if not current_app.config.get('WTF_CSRF_ENABLED', True):
            return view_function(*args, **kwargs)
            
        # For GET requests, we don't need CSRF protection
        if request.method == 'GET':
            return view_function(*args, **kwargs)
            
        # Extract token from headers or form data
        token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
        
        if not token:
            return jsonify({
                'success': False,
                'message': 'CSRF token missing',
                'error': 'csrf_required'
            }), 400
            
        try:
            validate_csrf(token)
        except CSRFError:
            return jsonify({
                'success': False,
                'message': 'Invalid or expired CSRF token',
                'error': 'csrf_invalid'
            }), 400
            
        return view_function(*args, **kwargs)
        
    return decorated_function

def rate_limit(limit=30, period=60):
    """
    Decorator for rate limiting requests by IP address.
    
    Args:
        limit (int): Maximum number of requests allowed in the period
        period (int): Time period in seconds
        
    Returns:
        function: Decorated function
    """
    def decorator(view_function):
        @wraps(view_function)
        def decorated_function(*args, **kwargs):
            # Skip rate limiting if testing
            if current_app.config.get('TESTING', False):
                return view_function(*args, **kwargs)
                
            ip = request.remote_addr
            current_time = time.time()
            
            with rate_limit_lock:
                # Clean up old entries first
                for key in list(rate_limit_data.keys()):
                    if current_time - rate_limit_data[key]['start_time'] > period:
                        del rate_limit_data[key]
                
                # Create or update entry for this IP
                if ip not in rate_limit_data:
                    rate_limit_data[ip] = {
                        'count': 1,
                        'start_time': current_time
                    }
                else:
                    # If period has expired, reset count
                    if current_time - rate_limit_data[ip]['start_time'] > period:
                        rate_limit_data[ip] = {
                            'count': 1,
                            'start_time': current_time
                        }
                    else:
                        rate_limit_data[ip]['count'] += 1
                
                # Check if limit exceeded
                if rate_limit_data[ip]['count'] > limit:
                    return jsonify({
                        'success': False,
                        'message': 'Rate limit exceeded. Please try again later.',
                        'error': 'rate_limit_exceeded'
                    }), 429
            
            return view_function(*args, **kwargs)
        
        return decorated_function
    
    return decorator

def validate_api_key(api_key_header='X-API-Key'):
    """
    Decorator to validate API key in requests.
    
    Args:
        api_key_header (str): Header name for API key
        
    Returns:
        function: Decorated function
    """
    def decorator(view_function):
        @wraps(view_function)
        def decorated_function(*args, **kwargs):
            # Skip API key validation if testing
            if current_app.config.get('TESTING', False):
                return view_function(*args, **kwargs)
                
            # Get API key from header
            api_key = request.headers.get(api_key_header)
            
            if not api_key:
                return jsonify({
                    'success': False,
                    'message': 'API key missing',
                    'error': 'api_key_required'
                }), 401
                
            # Validate API key (will need to implement this part)
            # This is a placeholder - actual validation needs to be implemented
            from models import APIKey
            
            key_record = APIKey.query.filter_by(active=True).all()
            valid_key = False
            
            for record in key_record:
                if record.verify_key(api_key):
                    valid_key = True
                    # Update last used timestamp
                    record.update_last_used()
                    break
                    
            if not valid_key:
                return jsonify({
                    'success': False,
                    'message': 'Invalid API key',
                    'error': 'api_key_invalid'
                }), 401
                
            return view_function(*args, **kwargs)
            
        return decorated_function
        
    return decorator

def secure_endpoint(limit=None, requires_csrf=True, requires_auth=True):
    """
    Comprehensive security decorator that combines multiple security measures.
    
    Args:
        limit (str, optional): Rate limit in format "count/period" (e.g., "30/minute")
        requires_csrf (bool): Whether to check CSRF token
        requires_auth (bool): Whether endpoint requires authentication
        
    Returns:
        function: Decorated function
    """
    def decorator(view_function):
        # Apply rate limiting if specified
        if limit:
            count, period_str = limit.split('/')
            count = int(count)
            
            # Convert period string to seconds
            if period_str.lower() == 'second':
                period = 1
            elif period_str.lower() == 'minute':
                period = 60
            elif period_str.lower() == 'hour':
                period = 3600
            elif period_str.lower() == 'day':
                period = 86400
            else:
                period = 60  # Default to minute
                
            view_function = rate_limit(limit=count, period=period)(view_function)
        
        # Apply CSRF protection if required
        if requires_csrf:
            view_function = ajax_csrf_protect(view_function)
            
        # Apply IP access control (check if IP is allowed)
        @wraps(view_function)
        def decorated_function(*args, **kwargs):
            from utils.ip_access_control import is_ip_allowed
            
            ip_address = request.remote_addr
            if not is_ip_allowed(ip_address):
                # Log the blocked request
                from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
                
                log_audit_event(
                    category=AuditCategory.SECURITY,
                    action="IP access denied",
                    severity=AuditSeverity.WARNING,
                    details={
                        'ip_address': ip_address,
                        'path': request.path,
                        'method': request.method
                    }
                )
                
                return jsonify({
                    'success': False,
                    'message': 'Access denied: Your IP address is restricted',
                    'error': 'ip_restricted'
                }), 403
                
            return view_function(*args, **kwargs)
            
        return decorated_function
        
    return decorator

def rate_limit_by_ip(limit=30, period=60):
    """
    Rate limiter that focuses specifically on IP-based limiting.
    
    Args:
        limit (int or str): Maximum number of requests allowed in the period. Can be an integer or string in format "count/period" (e.g., "10/minute")
        period (int): Time period in seconds, used only when limit is an integer
        
    Returns:
        function: Decorated function
    """
    # Parse limit if it's a string in format "count/period"
    if isinstance(limit, str) and '/' in limit:
        parts = limit.split('/')
        limit_count = int(parts[0])
        
        period_unit = parts[1].lower()
        if period_unit == 'second':
            period = 1
        elif period_unit == 'minute':
            period = 60
        elif period_unit == 'hour':
            period = 3600
        elif period_unit == 'day':
            period = 86400
        else:
            # Default to minute if unit is not recognized
            period = 60
            
        # Use the parsed count as the actual limit
        limit = limit_count
    
    def decorator(view_function):
        @wraps(view_function)
        def decorated_function(*args, **kwargs):
            ip = request.remote_addr

            with rate_limit_lock:
                current_time = time.time()
                if ip not in rate_limit_data:
                    rate_limit_data[ip] = []
                
                # Remove requests that are outside of the time period
                rate_limit_data[ip] = [t for t in rate_limit_data[ip] if current_time - t < period]
                
                # Check if the IP has hit the rate limit
                if len(rate_limit_data[ip]) >= limit:
                    return jsonify({
                        'success': False,
                        'message': 'Rate limit exceeded. Please try again later.'
                    }), 429
                
                # Add the current request
                rate_limit_data[ip].append(current_time)
            
            return view_function(*args, **kwargs)
        return decorated_function
    return decorator

def validate_coordinates(lat, lng):
    """
    Validate geographical coordinates to ensure they are within valid ranges
    and properly formatted.
    
    Args:
        lat (float): Latitude value
        lng (float): Longitude value
        
    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        lat = float(lat)
        lng = float(lng)
        
        if not (-90 <= lat <= 90):
            return False, "Latitude must be between -90 and 90 degrees"
        
        if not (-180 <= lng <= 180):
            return False, "Longitude must be between -180 and 180 degrees"
        
        return True, None
    except (ValueError, TypeError):
        return False, "Coordinates must be valid numbers"
