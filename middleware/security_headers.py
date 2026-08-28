"""
Security Headers Middleware for the CAD System.

This module provides middleware for adding security-related HTTP headers
to responses to enhance the security of the application.
"""

from flask import current_app, request, g
from functools import wraps
import random
import string

# Default security headers configuration
DEFAULT_SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'SAMEORIGIN',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'X-Permitted-Cross-Domain-Policies': 'none',
}

# CDN domains used by the application
_CDN_SCRIPTS = [
    'https://code.jquery.com',
    'https://cdn.jsdelivr.net',
    'https://cdnjs.cloudflare.com',
    'https://unpkg.com',
]
_CDN_STYLES = [
    'https://cdn.jsdelivr.net',
    'https://cdnjs.cloudflare.com',
    'https://unpkg.com',
]
_CDN_FONTS = [
    'https://cdnjs.cloudflare.com',
    'https://fonts.gstatic.com',
]

# CSP configuration
DEFAULT_CSP = {
    'default-src': "'self'",
    'script-src': [
        "'self'",
        "'unsafe-inline'",
        "'unsafe-eval'",
    ] + _CDN_SCRIPTS,
    'style-src': [
        "'self'",
        "'unsafe-inline'",
    ] + _CDN_STYLES,
    'img-src': [
        "'self'",
        'data:',
        'https:',
        'http:',
    ],
    'font-src': ["'self'", 'data:'] + _CDN_FONTS,
    'connect-src': [
        "'self'",
        'ws:',
        'wss:',
    ],
    'frame-ancestors': ["'self'"],
    'form-action': ["'self'"],
    'base-uri': ["'self'"],
    'object-src': ["'none'"],
}

def setup_security_headers(app):
    """Set up security headers for the application.
    
    Args:
        app: Flask application instance
    """
    # Apply security headers to all responses
    @app.after_request
    def add_security_headers(response):
        """Add security headers to the response."""
        # Skip headers for static files and error pages
        if (request.path.startswith('/static/') or 
            request.path.startswith('/_debug_toolbar/') or
            response.status_code >= 400):
            return response
        
        # Add default security headers
        for header, value in DEFAULT_SECURITY_HEADERS.items():
            if header not in response.headers:
                response.headers[header] = value
        
        # Add Content Security Policy
        if 'Content-Security-Policy' not in response.headers:
            csp = _build_csp()
            response.headers['Content-Security-Policy'] = csp
            
            # Add report-only CSP in development
            if app.debug:
                report_uri = app.config.get('CSP_REPORT_URI')
                if report_uri:
                    csp += f"; report-uri {report_uri}"
                response.headers['Content-Security-Policy-Report-Only'] = csp
        
        # Add HSTS header for HTTPS
        if request.is_secure and 'Strict-Transport-Security' not in response.headers:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        # Nonce handling is done via the template context processor;
        # no need to retroactively inject nonces into the CSP header here.
        
        # Add X-Request-ID if not present
        if 'X-Request-ID' not in response.headers and hasattr(g, 'request_id'):
            response.headers['X-Request-ID'] = g.request_id
        
        return response

def _build_csp():
    """Build the Content Security Policy header value."""
    csp_parts = []
    
    for directive, sources in DEFAULT_CSP.items():
        if isinstance(sources, (list, tuple)):
            sources = ' '.join(sources)
        csp_parts.append(f"{directive} {sources}")
    
    return '; '.join(csp_parts)

def _generate_nonce(length=16):
    """Generate a random nonce value."""
    chars = string.ascii_letters + string.digits + '-_'
    return ''.join(random.choice(chars) for _ in range(length))

def require_https(f):
    """Decorator to require HTTPS for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not request.is_secure and not current_app.debug:
            if request.url.startswith('http://'):
                https_url = request.url.replace('http://', 'https://', 1)
                return redirect(https_url, code=301)
        return f(*args, **kwargs)
    return decorated_function

def csp_nonce():
    """Get the current CSP nonce value, generating one if needed."""
    if 'csp_nonce' not in g:
        g.csp_nonce = _generate_nonce()
    return g.csp_nonce
