import os
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
from flask import request
import time

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Common log format for all handlers
class CustomFormatter(logging.Formatter):
    def format(self, record):
        record.username = getattr(record, 'username', 'system')
        record.ip = getattr(record, 'ip', '-')
        record.session = getattr(record, 'session', '-')
        
        format_str = '%(asctime)s - %(levelname)s - [%(username)s@%(ip)s] - %(message)s'
        if hasattr(record, 'audit_type'):
            format_str = '%(asctime)s - AUDIT - [%(username)s@%(ip)s] - %(audit_type)s - %(message)s'
            
        formatter = logging.Formatter(format_str)
        return formatter.format(record)

def setup_logging(app):
    """Setup all logging for the application"""
    
    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Create a formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(module)s@%(process)d] - %(message)s'
    )
    
    # Set up console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Set up file handlers with proper error handling
    try:
        # Error logging
        if os.name == 'nt':
            from concurrent_log_handler import ConcurrentRotatingFileHandler
            error_handler = ConcurrentRotatingFileHandler(
                'logs/error.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=10,
                encoding='utf-8'
            )
        else:
            error_handler = RotatingFileHandler(
                'logs/error.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=10,
                encoding='utf-8'
            )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(CustomFormatter())
        
        # Warning logging
        if os.name == 'nt':
            from concurrent_log_handler import ConcurrentRotatingFileHandler
            warning_handler = ConcurrentRotatingFileHandler(
                'logs/warning.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
        else:
            warning_handler = RotatingFileHandler(
                'logs/warning.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
        warning_handler.setLevel(logging.WARNING)
        warning_handler.setFormatter(CustomFormatter())
        
        # Access logging
        if os.name == 'nt':
            from concurrent_log_handler import ConcurrentRotatingFileHandler
            access_handler = ConcurrentRotatingFileHandler(
                'logs/access.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=30,
                encoding='utf-8'
            )
        else:
            access_handler = TimedRotatingFileHandler(
                'logs/access.log',
                when='midnight',
                interval=1,
                backupCount=30,
                encoding='utf-8'
            )
        access_handler.setLevel(logging.INFO)
        access_handler.setFormatter(CustomFormatter())
        
        # Audit logging (for security and changes)
        if os.name == 'nt':
            from concurrent_log_handler import ConcurrentRotatingFileHandler
            audit_handler = ConcurrentRotatingFileHandler(
                'logs/audit.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=365,  # Keep one year of audit logs
                encoding='utf-8'
            )
        else:
            audit_handler = TimedRotatingFileHandler(
                'logs/audit.log',
                when='midnight',
                interval=1,
                backupCount=365,  # Keep one year of audit logs
                encoding='utf-8'
            )
        audit_handler.setLevel(logging.INFO)
        audit_handler.setFormatter(CustomFormatter())
        
        # Debug logging (development only)
        if os.name == 'nt':
            from concurrent_log_handler import ConcurrentRotatingFileHandler
            debug_handler = ConcurrentRotatingFileHandler(
                'logs/debug.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=3,
                encoding='utf-8'
            )
        else:
            debug_handler = RotatingFileHandler(
                'logs/debug.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=3,
                encoding='utf-8'
            )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(CustomFormatter())
        
        # Database logging
        if os.name == 'nt':
            from concurrent_log_handler import ConcurrentRotatingFileHandler
            db_handler = ConcurrentRotatingFileHandler(
                'logs/database.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
        else:
            db_handler = RotatingFileHandler(
                'logs/database.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
        db_handler.setLevel(logging.DEBUG)
        db_handler.setFormatter(CustomFormatter())
        
        # Add handlers to root logger
        root_logger.addHandler(error_handler)
        root_logger.addHandler(warning_handler)
        
        # Setup loggers
        loggers = {
            'error': (logging.getLogger('error'), [error_handler, console_handler]),
            'warning': (logging.getLogger('warning'), [warning_handler, console_handler]),
            'access': (logging.getLogger('access'), [access_handler]),
            'audit': (logging.getLogger('audit'), [audit_handler, console_handler]),
            'debug': (logging.getLogger('debug'), [debug_handler, console_handler]),
            'database': (logging.getLogger('database'), [db_handler, console_handler]),
            'app': (logging.getLogger('app'), [debug_handler, console_handler]),
            'init': (logging.getLogger('init'), [debug_handler, console_handler, error_handler])
        }
        
        # Configure all loggers
        for name, (logger, handlers) in loggers.items():
            logger.setLevel(logging.DEBUG)  # Allow all levels, handlers will filter
            logger.propagate = False  # Prevent duplicate logging
            for handler in handlers:
                logger.addHandler(handler)
        
        # Create template logger with dedicated file handler
        template_logger = logging.getLogger('template')
        template_logger.setLevel(logging.DEBUG)
        template_logger.propagate = False  # Prevent propagation to avoid duplicate logs
        
        # Remove any existing handlers to prevent duplication
        while template_logger.handlers:
            template_logger.removeHandler(template_logger.handlers[0])
        
        # Template logging with a single consistent formatter
        if os.name == 'nt':
            from concurrent_log_handler import ConcurrentRotatingFileHandler
            template_handler = ConcurrentRotatingFileHandler(
                'logs/templates.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
        else:
            template_handler = RotatingFileHandler(
                'logs/templates.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
        template_handler.setLevel(logging.DEBUG)  # Capture all template interactions
        
        # Use a standard formatter for all template logs to ensure consistency
        template_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s@%(process)d] - %(message)s')
        template_handler.setFormatter(template_formatter)
        template_logger.addHandler(template_handler)
        
        # Add error handler to template logger, but with a filter to prevent recursion
        class RecursionFilter(logging.Filter):
            def __init__(self, max_count=1):
                super().__init__()
                self.max_count = max_count
                self.counts = {}
                
            def filter(self, record):
                # Create a key based on the log message and timestamp
                key = f"{record.msg}-{time.time():.0f}"
                count = self.counts.get(key, 0) + 1
                self.counts[key] = count
                
                # Clean up old keys to prevent memory leak
                if len(self.counts) > 1000:
                    self.counts = {k: v for k, v in list(self.counts.items())[-100:]}
                    
                # Only allow up to max_count logs with the same message in a short timeframe
                return count <= self.max_count
        
        # Create a filtered version of the error handler for template errors
        template_error_handler = error_handler
        recursion_filter = RecursionFilter(max_count=2)  # Allow max 2 identical messages
        template_error_handler.addFilter(recursion_filter)
        template_logger.addHandler(template_error_handler)
        
        # Also configure root logger for uncaught logs, with recursion protection
        root_logger.setLevel(logging.WARNING)  # Only log warnings and above
        root_recursion_filter = RecursionFilter(max_count=3)  # More permissive for root logger
        
        # Clear existing handlers from root logger to avoid duplication
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            
        # Add filtered handlers to root logger
        console_handler.addFilter(root_recursion_filter)
        error_handler.addFilter(root_recursion_filter)
        warning_handler.addFilter(root_recursion_filter)
        
        root_logger.addHandler(console_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(warning_handler)
        
        root_logger.info("Logging configured")
    except Exception as e:
        # Log to console if file handlers fail
        console_handler.setLevel(logging.ERROR)
        root_logger.error(f"Failed to set up log files: {str(e)}")
    
    # Audit decorator
    def audit_log(audit_type):
        def decorator(f):
            def wrapped(*args, **kwargs):
                # Get user info from flask-login
                from flask_login import current_user
                from flask import request
                
                username = current_user.username if hasattr(current_user, 'username') else 'anonymous'
                ip = request.remote_addr
                session = request.cookies.get('session', '-')
                
                audit_logger = logging.getLogger('audit')
                extra = {
                    'username': username,
                    'ip': ip,
                    'session': session,
                    'audit_type': audit_type
                }
                
                # Log the function call
                audit_logger.info(
                    f"Function {f.__name__} called with args={args}, kwargs={kwargs}",
                    extra=extra
                )
                
                try:
                    result = f(*args, **kwargs)
                    # Log successful execution
                    audit_logger.info(
                        f"Function {f.__name__} completed successfully",
                        extra=extra
                    )
                    return result
                except Exception as e:
                    # Log the error
                    audit_logger.error(
                        f"Function {f.__name__} failed: {str(e)}",
                        extra=extra
                    )
                    raise
            return wrapped
        return decorator
    
    # Add audit decorator to app context
    app.audit_log = audit_log
    
    # Setup error logging for Flask
    @app.errorhandler(Exception)
    def handle_error(error):
        error_logger = logging.getLogger('error')
        error_logger.exception("Unhandled exception: %s", str(error))
        return "Internal Server Error", 500
    
    # Setup access logging for Flask
    @app.after_request
    def log_request(response):
        try:
            if not request.path.startswith('/static'):  # Skip static file access
                from flask_login import current_user
                username = current_user.username if hasattr(current_user, 'username') else 'anonymous'
                
                access_logger = logging.getLogger('access')
                try:
                    access_logger.info(
                        f"{request.method} {request.path} {response.status_code}",
                        extra={
                            'username': username,
                            'ip': request.remote_addr,
                            'session': request.cookies.get('session', '-')
                        }
                    )
                except PermissionError:
                    # Ignore permission errors during log rotation
                    pass
        except Exception as e:
            error_logger = logging.getLogger('error')
            try:
                error_logger.exception("Error in request logging: %s", str(e))
            except PermissionError:
                # Ignore permission errors during log rotation
                pass
        return response
    
    return app
