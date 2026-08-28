import logging
import time
from flask import request, g
from flask_login import current_user

# Create database logger
db_logger = logging.getLogger('database')

class DBQueryTimer:
    """Context manager to time database operations and log them."""
    
    def __init__(self, operation_type, query=None):
        self.operation_type = operation_type
        self.query = query
        self.start_time = None
        
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        # Get user info if available
        username = getattr(current_user, 'username', 'anonymous') if current_user else 'anonymous'
        ip = request.remote_addr if request else '-'
        
        # Log the database operation
        extra = {
            'username': username,
            'ip': ip,
            'session': request.cookies.get('session', '-') if request else '-'
        }
        
        if exc_type:
            # Log database errors
            db_logger.error(
                f"DB {self.operation_type} ERROR: {exc_val} - Query: {self.query} - Duration: {duration:.4f}s",
                extra=extra
            )
        else:
            # Log successful operations
            level = logging.INFO if duration > 0.5 else logging.DEBUG
            db_logger.log(
                level,
                f"DB {self.operation_type}: {self.query} - Duration: {duration:.4f}s",
                extra=extra
            )
            
        # Return False to not suppress exceptions
        return False

def log_query(query):
    """Log a database query."""
    return DBQueryTimer('QUERY', query)
    
def log_insert():
    """Log a database insert operation."""
    return DBQueryTimer('INSERT')
    
def log_update():
    """Log a database update operation."""
    return DBQueryTimer('UPDATE')
    
def log_delete():
    """Log a database delete operation."""
    return DBQueryTimer('DELETE')
