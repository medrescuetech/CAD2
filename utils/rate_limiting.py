"""
Rate limiting utilities for the application.

This module provides rate limiting functionality to prevent abuse of the API endpoints.
"""

def get_limiter_key():
    """
    Get the key used for rate limiting.
    
    Returns:
        str: The key to use for rate limiting (defaults to client IP).
    """
    from flask import request
    
    # Use the client's IP address as the default key
    return request.remote_addr
