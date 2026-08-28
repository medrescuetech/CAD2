#!/usr/bin/env python
"""
CAD System - Main Entry Point

This is the primary entry point for the CAD System application.
It properly initializes all required components in the correct order
and launches the application with proper SocketIO support.

Usage:
    python main.py          - Launches the application with GUI
    python main.py --nogui  - Launches the application directly without GUI
"""
import os
import sys
import logging
import argparse
import eventlet
from datetime import datetime

# Patch before other imports to ensure WebSocket compatibility
eventlet.monkey_patch()

# Create new_log directory if it doesn't exist
os.makedirs('new_log', exist_ok=True)

# Set up basic temporary logging until the main logging system is initialized
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.__stdout__),
        logging.FileHandler(f'new_log/startup.log'),
        logging.FileHandler(f'new_log/terminal_output_{os.getpid()}.log')
    ]
)

logger = logging.getLogger('main')

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Run the CAD System application')
    parser.add_argument('--nogui', action='store_true', help='Run without GUI launcher')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the application on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to run the application on')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    return parser.parse_args()

if __name__ == '__main__':
    try:
        # Initialize terminal logging to capture all stdout and stderr
        from utils.terminal_logger import init_terminal_logging
        terminal_logger = init_terminal_logging()
        
        # Parse command line arguments
        args = parse_arguments()
        
        # Set Flask environment
        os.environ['FLASK_ENV'] = 'development'
        
        # Import after eventlet patch
        from app import create_app, ServerManager
        from extensions import socketio
        from utils.log_setup import setup_logger
        
        # Prevent WebSocket initialization during app creation by setting a flag
        os.environ['SKIP_WEBSOCKET_INIT'] = 'true'
        
        # Create the application instance
        logger.info("Creating application instance")
        app = create_app()
        
        # Now that the app is created, clear the flag and initialize WebSockets manually
        # in a controlled way to avoid duplicate initialization
        del os.environ['SKIP_WEBSOCKET_INIT']
        
        # Enable debug logging for SocketIO
        socketio.logger = True
        socketio.engineio_logger = True
        
        # Initialize WebSocket functionality exactly once
        from websocket_init import init_socketio
        logger.info("Manually initializing WebSocket functionality")
        init_socketio(app)
        
        if args.nogui:
            # Run the application directly with SocketIO
            logger.info(f"Starting application in direct mode on {args.host}:{args.port}")
            socketio.run(
                app, 
                host=args.host, 
                port=args.port, 
                debug=args.debug, 
                use_reloader=False
            )
        else:
            # Run the application with the GUI launcher
            logger.info("Starting application with GUI launcher")
            manager = ServerManager(app)
            manager.run()
            
    except Exception as e:
        logger.error(f"Error launching application: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
