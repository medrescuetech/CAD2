"""
Rate Limiting Middleware for the CAD System.

This module provides rate limiting functionality to prevent abuse of the API.
"""

from flask import request, jsonify, g
from functools import wraps
import time
from threading import Lock
from datetime import datetime, timedelta
import re

# In-memory storage for rate limiting (consider using Redis in production)
_rate_limit_storage = {}
_rate_limit_lock = Lock()

def setup_rate_limiting(app):
    """Set up rate limiting for the application.
    
    Args:
        app: Flask application instance
    """
    # Configure default rate limits from app config
    default_limits = app.config.get('RATE_LIMITS', {
        'default': '1000 per hour',
        'auth': '10 per minute',
        'api': '100 per minute',
    })
    
    @app.before_request
    def apply_rate_limits():
        """Apply rate limiting to incoming requests."""
        # Skip rate limiting for certain paths
        if request.path.startswith('/static/') or request.path == '/health' or request.method == 'OPTIONS':
            return
        
        # Get client identifier (API key or IP)
        identifier = _get_client_identifier()
        
        # Determine the rate limit rule to apply
        rule = _get_rate_limit_rule(request.path, default_limits)
        
        if rule:
            limit, window = _parse_rate_limit(rule)
            
            # Check rate limit
            current = _get_request_count(identifier, request.path, window)
            
            if current >= limit:
                # Calculate when the rate limit will reset
                reset_time = _get_window_start(time.time(), window) + window
                reset_seconds = int(reset_time - time.time())
                
                # Set rate limit headers
                response = jsonify({
                    'success': False,
                    'error': 'rate_limit_exceeded',
                    'message': f'Too many requests. Limit is {limit} per {window} seconds',
                    'retry_after': reset_seconds
                })
                
                response.headers['X-RateLimit-Limit'] = str(limit)
                response.headers['X-RateLimit-Remaining'] = '0'
                response.headers['X-RateLimit-Reset'] = str(int(reset_time))
                response.headers['Retry-After'] = str(reset_seconds)
                
                return response, 429
            
            # Update rate limit counter
            _increment_request_count(identifier, request.path)
            
            # Set rate limit headers
            remaining = limit - current - 1
            g.rate_limit = {
                'limit': limit,
                'remaining': remaining,
                'reset': _get_window_start(time.time(), window) + window
            }
    
    @app.after_request
    def add_rate_limit_headers(response):
        """Add rate limit headers to responses."""
        if hasattr(g, 'rate_limit'):
            response.headers['X-RateLimit-Limit'] = str(g.rate_limit['limit'])
            response.headers['X-RateLimit-Remaining'] = str(g.rate_limit['remaining'])
            response.headers['X-RateLimit-Reset'] = str(int(g.rate_limit['reset']))
        return response

def _get_client_identifier():
    """Get a unique identifier for the client."""
    # Prefer API key if available
    if hasattr(g, 'api_key') and g.api_key:
        return f'key:{g.api_key.key}'
    
    # Fall back to IP address
    return f'ip:{request.remote_addr}'

def _get_rate_limit_rule(path, default_limits):
    """Determine the rate limit rule to apply to a request."""
    # Check for path-specific rules first
    for prefix, rule in default_limits.items():
        if path.startswith(f'/api/{prefix}') or path.startswith(f'/{prefix}'):
            return rule
    
    # Check for default API rule
    if path.startswith('/api/'):
        return default_limits.get('api', '100 per minute')
    
    # Default rule
    return default_limits.get('default', '1000 per hour')

def _parse_rate_limit(limit_str):
    """Parse a rate limit string into count and window in seconds."""
    match = re.match(r'(\d+)\s*(?:per|/)\s*(\w+)', limit_str.lower())
    if not match:
        return 1000, 3600  # Default to 1000 requests per hour
    
    count = int(match.group(1))
    unit = match.group(2)
    
    # Convert time unit to seconds
    if unit in ('second', 'sec', 's'):
        window = 1
    elif unit in ('minute', 'min', 'm'):
        window = 60
    elif unit in ('hour', 'hr', 'h'):
        window = 3600
    elif unit in ('day', 'd'):
        window = 86400
    else:
        window = 3600  # Default to hour
    
    return count, window

def _get_window_start(timestamp, window):
    """Get the start of the current rate limit window."""
    return int(timestamp) // window * window

def _get_request_count(identifier, path, window):
    """Get the number of requests in the current window."""
    window_start = _get_window_start(time.time(), window)
    key = f"{identifier}:{path}:{window_start}"
    
    with _rate_limit_lock:
        return _rate_limit_storage.get(key, 0)

def _increment_request_count(identifier, path):
    """Increment the request count for the current window."""
    window = 60  # Default to 1-minute windows for counting
    window_start = _get_window_start(time.time(), window)
    key = f"{identifier}:{path}:{window_start}"
    
    with _rate_limit_lock:
        _rate_limit_storage[key] = _rate_limit_storage.get(key, 0) + 1
        
        # Clean up old entries (simple garbage collection)
        current_time = time.time()
        for k in list(_rate_limit_storage.keys()):
            # Split only on the last colon to handle paths with colons
            try:
                # Find the last colon in the key
                last_colon_pos = k.rfind(':')
                if last_colon_pos == -1:
                    continue
                    
                # Extract the timestamp (everything after the last colon)
                ts_str = k[last_colon_pos + 1:]
                
                # Try to convert to int and check if it's old
                ts = int(ts_str)
                if current_time - ts > 3600:  # Keep data for up to 1 hour
                    del _rate_limit_storage[k]
            except (ValueError, IndexError):
                # If we can't parse the timestamp, remove the malformed key
                del _rate_limit_storage[k]
