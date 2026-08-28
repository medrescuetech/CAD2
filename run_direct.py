"""
Direct run script for the CAD system application.
This script will directly run the Flask application using SocketIO.
"""
import os
import logging
import sys
from app import create_app
from extensions import socketio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('run')

if __name__ == '__main__':
    logger.info("Initializing application with direct SocketIO")
    
    try:
        # Set Flask environment
        os.environ['FLASK_ENV'] = 'development'
        
        # Create the application instance
        app = create_app()
        logger.info("Application created successfully")
        
        # Run with socketio instead of regular Flask run
        socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False)
        
    except Exception as e:
        logger.error(f"Error launching application: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
