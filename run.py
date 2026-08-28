"""
Run script for the CAD system application.
This script will directly run the Flask application without using the Flask CLI.
"""
import os
import logging
import sys
import traceback
import eventlet
import datetime
from logging.handlers import RotatingFileHandler

# Patch before other imports to ensure WebSocket compatibility
eventlet.monkey_patch()

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

from app import create_app, ServerManager
from extensions import socketio
from utils.log_setup import setup_logger

# Set up basic temporary logging until the main logging system is initialized
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.__stdout__),
        logging.FileHandler(f'logs/startup_{datetime.datetime.now().strftime("%Y-%m-%d")}.log')
    ]
)

# Get a temporary logger for initialization
run_logger = logging.getLogger('run')

if __name__ == '__main__':
    run_logger.info("Initializing application")
    
    try:
        # Set Flask environment
        os.environ['FLASK_ENV'] = 'development'
        
        # Create the application instance
        app = create_app()
        
        # Logging is already set up in app.py via setup_logger()
        
        # Enable debug logging for SocketIO
        socketio.logger = True
        socketio.engineio_logger = True
        
        # WebSocket handlers are already initialized in app.py, no need to reinitialize
        
        run_logger.info("Application created successfully with SocketIO configured")
        
        # Create the server manager GUI
        manager = ServerManager(app)
        run_logger.info("Server manager initialized")
        
        # Print additional debug info
        run_logger.info("Starting GUI - if no window appears, check for Tkinter issues")
        
        # Run the GUI
        manager.run()
        
    except Exception as e:
        run_logger.error(f"Error launching application: {str(e)}")
        run_logger.error(traceback.format_exc())
        sys.exit(1)
