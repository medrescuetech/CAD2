import os
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
from flask import request, current_app
import time

# Ensure new_log directory exists
os.makedirs('new_log', exist_ok=True)

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

def setup_logger(app=None):
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
        # Basic app logging
        file_handler = RotatingFileHandler(
            filename=f'new_log/cad_system_{datetime.now().strftime("%Y-%m-%d")}.log',
            maxBytes=10485760,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(CustomFormatter())
        
        # Application-level logging (named app_handler used elsewhere)
        app_handler = RotatingFileHandler(
            filename='new_log/app.log',
            maxBytes=10485760,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
        app_handler.setLevel(logging.INFO)
        app_handler.setFormatter(CustomFormatter())
        
        # Error log for errors only
        error_handler = RotatingFileHandler(
            filename='new_log/error.log',
            maxBytes=10485760,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(CustomFormatter())
        
        # Warning log for warnings and above
        warning_handler = RotatingFileHandler(
            filename='new_log/warning.log',
            maxBytes=10485760,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        warning_handler.setLevel(logging.WARNING)
        warning_handler.setFormatter(CustomFormatter())
        
        # Access logging
        access_handler = RotatingFileHandler(
            filename='new_log/access.log',
            maxBytes=10485760,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        access_handler.setLevel(logging.INFO)
        access_handler.setFormatter(CustomFormatter())
        
        # Audit logging (for security and changes)
        audit_handler = RotatingFileHandler(
            filename='new_log/audit.log',
            maxBytes=10485760,  # 10MB
            backupCount=30,
            encoding='utf-8'
        )
        audit_handler.setLevel(logging.INFO)
        audit_handler.setFormatter(CustomFormatter())
        
        # Debug log for detailed debugging
        debug_handler = RotatingFileHandler(
            filename='new_log/debug.log',
            maxBytes=20971520,  # 20MB
            backupCount=3,
            encoding='utf-8'
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(CustomFormatter())
        
        # Database logging
        db_handler = RotatingFileHandler(
            filename='new_log/database.log',
            maxBytes=10485760,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        db_handler.setLevel(logging.DEBUG)
        db_handler.setFormatter(CustomFormatter())
        
        # WebSocket logging
        websocket_handler = RotatingFileHandler(
            filename='new_log/websocket.log',
            maxBytes=10485760,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        websocket_handler.setLevel(logging.DEBUG)
        websocket_handler.setFormatter(CustomFormatter())
        
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
            'app': (logging.getLogger('app'), [app_handler, console_handler]),
            'init': (logging.getLogger('init'), [debug_handler, console_handler, error_handler]),
            'websocket': (logging.getLogger('websocket'), [websocket_handler, console_handler])
        }
        
        # Configure all loggers
        for name, (logger, handlers) in loggers.items():
            logger.setLevel(logging.DEBUG)  # Allow all levels, handlers will filter
            logger.propagate = False  # Prevent duplicate logging
            for handler in handlers:
                logger.addHandler(handler)
                
        # Create a default logger for modules to use
        module_logger = logging.getLogger('cad_system')
        module_logger.setLevel(logging.DEBUG)
        module_logger.propagate = False
        module_logger.addHandler(app_handler)
        module_logger.addHandler(console_handler)
        module_logger.addHandler(error_handler)  # Make sure errors are captured
                
    except Exception as e:
        # If we encounter an error while setting up logging, log to console
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logging.error(f"Failed to configure advanced logging: {str(e)}")
        
    if app:
        # Register after-request handler for access logging if app is provided
        @app.after_request
        def log_request(response):
            access_logger = logging.getLogger('access')
            # Don't log asset requests to reduce noise
            if not request.path.startswith('/static'):
                # Calculate request duration
                duration = None
                if hasattr(request, 'start_time'):
                    duration = time.time() - request.start_time
                    duration = round(duration * 1000, 2)  # Convert to ms
                    
                # Create log record with extra context
                access_logger.info(
                    f"{request.method} {request.path} {response.status_code} {duration}ms",
                    extra={
                        'ip': request.remote_addr,
                        'user_agent': request.user_agent.string,
                        'status': response.status_code,
                        'duration': duration
                    }
                )
            return response

    # Return a default logger that can be used by imported modules
    return logging.getLogger('cad_system')

# Create a global logger for this module
logger = setup_logger()
