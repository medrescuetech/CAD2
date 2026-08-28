"""
Middleware package for the CAD system.

This package contains middleware components for request/response processing,
including authentication, rate limiting, and request validation.
"""

from .api_middleware import setup_middleware
from .rate_limiting import setup_rate_limiting
from .request_logging import setup_request_logging
from .security_headers import setup_security_headers

def init_app(app):
    """Initialize all middleware components.
    
    Args:
        app: Flask application instance
    """
    # Order matters here - they will be executed in reverse order
    setup_security_headers(app)
    setup_rate_limiting(app)
    setup_request_logging(app)
    setup_middleware(app)
