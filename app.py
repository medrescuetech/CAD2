"""
CAD System Application Module

This module contains core application functions and classes including:
- Application Factory (create_app)
- ServerManager for the GUI launcher
- Authentication and authorization handlers
- Logging setup

NOTE: Application entry point has been moved to run.py
      Please use 'python run.py' to start the application instead of this file.
"""

# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

import os
import secrets
import logging
import threading
import webbrowser
import socket
import functools
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

try:
    import tkinter as tk
except ImportError:  # Tk is only needed for the optional desktop launcher
    tk = None

from flask import Flask, render_template, request, jsonify, current_app, make_response, g, session
from flask_login import LoginManager, current_user, login_required
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_migrate import Migrate
from flask_mail import Mail
from flask_socketio import SocketIO
from flask_assets import Environment, Bundle
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import HTTPException, InternalServerError

# Import extensions
from extensions import db, migrate, csrf, mail, limiter, socketio, session_factory, Session, assets

# Import models
from models import User, Role, Permission, APIKey, AuditLog
import core.models  # Register ecosystem shared-core tables
import core.chronology  # Attach append-only chronology listeners
from blueprints.pages import pages
from blueprints.auth import auth
from blueprints.api import api
from blueprints.email_api import bp as email_api_bp
from blueprints.smtp_api import bp as smtp_api_bp
from blueprints.user import bp as user_bp
from blueprints.api_keys import bp as api_keys_bp
from blueprints.audit import bp as audit_bp
from blueprints.user_management import bp as user_management_bp
from blueprints.session_management import bp as session_management_bp
from blueprints.ip_access import bp as ip_access_bp
from blueprints.reporting import bp as reporting_bp
from blueprints.locations import bp as locations_bp
from blueprints.incidents import bp as incidents_bp
from blueprints.daily_log_api import daily_log_api
from blueprints.ampds_api import ampds_api
from blueprints.system_admin import system_admin_bp
from blueprints.data_management import data_mgmt_bp
from blueprints.core_api import core_api
from api.endpoints import api_endpoints
from utils.log_setup import setup_logger  # Changed from logging_config import
import websocket_events  # Import WebSocket event handlers
import websocket_init  # Import WebSocket initialization
from commands import init_db_command
from sqlalchemy.pool import StaticPool
from config import config as app_config
from flask_wtf.csrf import CSRFProtect, generate_csrf
from utils.security import get_csrf_token
from utils.middleware import setup_api_middleware
from utils.monitoring import monitor, init_app as init_monitoring
from utils.scheduler import scheduler, init_app as init_scheduler
from utils.asset_optimizer import init_asset_optimization

# Create logger for admin user creation
admin_logger = logging.getLogger('audit')
template_logger = logging.getLogger('template')
init_logger = logging.getLogger('init')
access_logger = logging.getLogger('access')

login_manager = LoginManager()
login_manager.login_view = 'auth.login'  # Must point to the blueprint name + route name
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"
csrf = CSRFProtect()  # Initialize CSRF protection

def log_template_render(template, context, app):
    """Log template rendering with context information."""
    try:
        template_logger.info(
            f"Rendering template: {template.name} | "
            f"User: {current_user.username if not current_user.is_anonymous else 'Anonymous'} | "
            f"URL: {request.url if request else 'No URL'} | "
            f"Context Keys: {list(context.keys())}"
        )
    except Exception as e:
        template_logger.error(f"Error logging template render: {str(e)}")
        logging.getLogger('error').error(f"Template error in {template.name if hasattr(template, 'name') else 'unknown'}: {str(e)}")

def create_app(config_name=None):
    """Application factory.
    Accepts either a config name (str) or a dict of config overrides for testing.
    """
    import os  # Import os at the function level to ensure it's available
    
    overrides = None
    # Support passing a dict of overrides for tests
    if isinstance(config_name, dict):
        overrides = config_name
        if overrides.get('TESTING'):
            config_name = 'testing'
        else:
            config_name = os.environ.get('FLASK_ENV', 'production')
    
    # Determine config name if not provided
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'production')
    
    # Create the Flask application
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
        instance_relative_config=True
    )
    
    # Configure the application
    app.config.from_object(app_config[config_name])
    app.config.from_pyfile('config.py', silent=True)  # Load instance config if it exists
    
    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError as e:
        app.logger.error(f"Failed to create instance folder: {e}")
    # Initialize logging
    setup_logger(app)
    app.logger.info(f"Starting CAD System in {config_name} mode")
    
    # Load configuration
    config_obj = app_config[config_name]
    app.config.from_object(config_obj)
    
    # Apply any overrides (primarily used by tests)
    if overrides:
        app.config.update(overrides)
    
    # Initialize app-specific configuration
    config_obj.init_app(app)

    # For tests, prefer threading async mode to simplify Socket.IO test client behavior
    if app.config.get('TESTING'):
        app.config['SOCKETIO_ASYNC_MODE'] = 'threading'

    # Apply proxy fix if behind a reverse proxy
    if app.config.get('BEHIND_PROXY', False):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=app.config.get('PROXY_FOR_HEADERS', 1),
            x_proto=1,
            x_host=1,
            x_port=1,
            x_prefix=1
        )
    
    # Initialize extensions with the app
    initialize_extensions(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Configure template filters and context processors
    configure_template_processors(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Setup request handlers
    setup_request_handlers(app)
    
    # Initialize monitoring and scheduling (skip during tests or when disabled)
    if not (app.config.get('TESTING') or app.config.get('DISABLE_BACKGROUND_TASKS')):
        init_monitoring(app)
        init_scheduler(app)
        # PCR integration sender: delivers queued outbound messages to PCR
        from core import pcr
        if pcr.config()['enabled']:
            threading.Thread(target=pcr.run_worker, args=(app,),
                             daemon=True, name='pcr-delivery').start()

    # Seed ecosystem reference data if the tables exist but are empty
    with app.app_context():
        try:
            from core.models import CodeSet
            from core.reference_data import insert_defaults
            if CodeSet.query.count() == 0:
                insert_defaults()
        except Exception as exc:
            app.logger.warning(f'Core reference-data seed skipped: {exc}')

    # Initialize asset optimization
    init_asset_optimization(app)
    
    # Initialize middleware (skip during tests to avoid external request_logging side-effects)
    if not app.config.get('TESTING'):
        try:
            from middleware import init_app as init_middleware
            init_middleware(app)
            app.logger.info("Middleware initialized successfully")
        except ImportError as e:
            app.logger.error(f"Failed to initialize middleware: {e}")
        except Exception as e:
            app.logger.error(f"Error initializing middleware: {e}", exc_info=True)
    
    # Only initialize websocket event handlers if not being called from main.py
    # This prevents double initialization of WebSockets
    import os
    if not os.environ.get('SKIP_WEBSOCKET_INIT'):
        from websocket_init import init_socketio
        init_socketio(app)
    
    # Return the configured Flask application
    return app
    
def _sanitize_engine_options(app):
    """Drop connection-pool options that SQLite's pool classes do not accept."""
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not uri.startswith('sqlite'):
        return

    options = dict(app.config.get('SQLALCHEMY_ENGINE_OPTIONS') or {})
    for option in ('pool_size', 'max_overflow', 'pool_timeout'):
        options.pop(option, None)
    options.pop('poolclass', None)
    options.setdefault('connect_args', {'check_same_thread': False})
    options['poolclass'] = StaticPool
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = options


def initialize_extensions(app):
    """Initialize Flask extensions."""
    # SQLAlchemy
    _sanitize_engine_options(app)
    db.init_app(app)
    
    # Flask-Migrate
    migrate.init_app(app, db)
    
    # Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'
    login_manager.refresh_view = 'auth.reauthenticate'
    login_manager.needs_refresh_message = 'Please reauthenticate to access this page.'
    login_manager.needs_refresh_message_category = 'info'
    login_manager.session_protection = 'strong'
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login."""
        if user_id is None:
            return None
        return User.query.get(int(user_id))
    
    # Flask-WTF CSRF Protection
    csrf.init_app(app)
    
    # Flask-Mail
    mail.init_app(app)
    
    # Flask-Limiter
    from utils.rate_limiting import get_limiter_key
    limiter.key_func = get_limiter_key
    limiter.init_app(app)
    
    # Flask-SocketIO
    socketio.init_app(
        app,
        async_mode=app.config.get('SOCKETIO_ASYNC_MODE', 'eventlet'),
        cors_allowed_origins=app.config.get('CORS_ORIGINS', []),
        message_queue=app.config.get('CELERY_BROKER_URL') if app.config.get('USE_CELERY', False) else None,
        logger=app.logger.getChild('socketio'),
        engineio_logger=app.config.get('ENGINEIO_LOGGER', False)
    )
    
    # Flask-Assets
    assets.init_app(app)
    from utils.asset_optimizer import configure_assets
    configure_assets(assets)
    
    # Initialize API middleware (skip during tests)
    if not app.config.get('TESTING'):
        from utils.middleware import setup_api_middleware
        setup_api_middleware(app)

def configure_template_processors(app):
    """Configure template context processors and filters."""
    from datetime import datetime
    import os
    
    @app.context_processor
    def inject_now():
        """Inject 'now' variable into all templates."""
        return {'now': datetime.utcnow()}
    
    @app.context_processor
    def inject_debug():
        """Inject debug flag into all templates."""
        return {'debug': app.debug}
    
    @app.template_filter('format_datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M:%S'):
        """Format a datetime object to a string."""
        if value is None:
            return ''
        return value.strftime(format)
    
    @app.template_filter('filesize')
    def format_filesize(value):
        """Format a file size in bytes to a human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if value < 1024.0:
                return f"{value:.1f} {unit}"
            value /= 1024.0
        return f"{value:.1f} PB"

def register_blueprints(app):
    """Register Flask blueprints."""
    # API Blueprints
    app.register_blueprint(api, url_prefix='/api')
    app.register_blueprint(email_api_bp, url_prefix='/api/email')
    app.register_blueprint(smtp_api_bp, url_prefix='/api/smtp')
    app.register_blueprint(daily_log_api, url_prefix='/api/daily-log')
    # ampds_api defines absolute '/api/ampds/...' routes; do not add a prefix
    app.register_blueprint(ampds_api)
    app.register_blueprint(reporting_bp, url_prefix='/api/reports')
    # locations blueprint defines absolute '/locations/...'; do not add extra prefix
    app.register_blueprint(locations_bp)
    # incidents blueprint defines '/incidents/...' API routes; mount under /api
    # so the frontend's /api/incidents* calls resolve
    app.register_blueprint(incidents_bp, url_prefix='/api')
    app.register_blueprint(core_api, url_prefix='/api/core')
    from blueprints.calltaker import bp as calltaker_bp
    app.register_blueprint(calltaker_bp)
    from blueprints.eventcad import bp as eventcad_bp
    app.register_blueprint(eventcad_bp)
    from blueprints.cadmain import bp as cadmain_bp
    app.register_blueprint(cadmain_bp)
    
    # Web Interface Blueprints
    app.register_blueprint(pages, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(api_keys_bp, url_prefix='/api-keys')
    app.register_blueprint(audit_bp, url_prefix='/audit')
    app.register_blueprint(user_management_bp, url_prefix='/users')
    app.register_blueprint(session_management_bp, url_prefix='/sessions')
    app.register_blueprint(ip_access_bp, url_prefix='/ip-access')
    
    # Admin Blueprints
    from blueprints.admin import admin as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # Development/Testing Blueprints (optional)
    if app.config.get('DEBUG'):
        try:
            from blueprints.test_email import bp as test_email_bp
            app.register_blueprint(test_email_bp, url_prefix='/test-email')
        except Exception as e:
            app.logger.warning(f"Optional test_email blueprint not available: {e}")
    
    # WebSocket initialization
    if not os.environ.get('SKIP_WEBSOCKET_INIT'):
        from websocket_init import init_socketio
        init_socketio(app)
    # Removed duplicate api_endpoints registration - it conflicts with notification_api
    # app.register_blueprint(api_endpoints, url_prefix='/api/notifications')
    
    # Note: system_admin_bp is registered twice - once with '/api/system' prefix in the blueprint definition
    # and once here with '/system-admin' prefix. Commenting out the second registration to avoid conflicts.
    # app.register_blueprint(system_admin_bp, url_prefix='/system-admin')
    
    # Note: data_mgmt_bp is registered twice - once with '/api/data' prefix in the blueprint definition
    # and once here with '/data-management' prefix. Commenting out the second registration to avoid conflicts.
    # app.register_blueprint(data_mgmt_bp, url_prefix='/data-management')
    
    # Initialize blueprint-specific components
    from blueprints.daily_log_api import init_daily_log_api
    init_daily_log_api(app)
    
    # Setup API middleware for authentication and logging (skip during tests)
    if not app.config.get('TESTING'):
        from utils.middleware import setup_api_middleware as _setup_api_mw
        _setup_api_mw(app)
    
    # Setup request logging
    @app.before_request
    def before_request():
        # Store request start time for performance logging
        request.start_time = time.time()
        
        # Get username for logging
        username = getattr(current_user, 'username', 'anonymous') if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated else 'anonymous'
        
        # Log request details
        extra = {
            'username': username,
            'ip': request.remote_addr,
            'session': request.cookies.get('session', '-')
        }
        try:
            logging.getLogger('access').info(f"Request: {request.method} {request.path} - Params: {dict(request.args)}", extra=extra)
        except Exception as e:
            logging.getLogger('error').error(f"Error logging request: {str(e)}")
    
    # Add CSRF token to all responses
    @app.after_request
    def add_csrf_token(response):
        # Only add CSRF token to JSON responses and HTML pages
        if response.content_type.startswith(('application/json', 'text/html')):
            if response.content_type.startswith('application/json'):
                # For API responses, add CSRF token to the response headers
                response.headers['X-CSRF-Token'] = generate_csrf()
            elif response.content_type.startswith('text/html'):
                # For HTML pages, make sure the token is available in JavaScript
                if not hasattr(g, 'csrf_token'):
                    g.csrf_token = generate_csrf()
        
        # Add security headers to all responses
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        return response
    
    # Add route to get CSRF token for AJAX requests
    @app.route('/api/csrf-token', methods=['GET'])
    def get_csrf_token_route():
        return jsonify({
            'success': True,
            'csrf_token': get_csrf_token()
        })
    
    # Add health check endpoint for testing
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint that doesn't require authentication."""
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.utcnow().isoformat(),
            'version': app.config.get('VERSION', '1.0.0')
        }), 200

    # Internal shutdown endpoint (localhost only, token protected)
    @app.route('/__shutdown', methods=['POST'])
    def __shutdown():
        try:
            # Only allow local requests
            if request.remote_addr not in ('127.0.0.1', '::1'):
                return jsonify({'success': False, 'message': 'Forbidden'}), 403
            token = request.headers.get('X-Shutdown-Token', '')
            if token != app.config.get('SHUTDOWN_TOKEN'):
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401

            # Attempt to shutdown Socket.IO and background tasks
            try:
                from websocket_init import shutdown_socketio
                shutdown_socketio()
            except Exception as e:
                app.logger.warning(f"SocketIO shutdown warning: {e}")

            # Werkzeug server shutdown
            shutdown_func = request.environ.get('werkzeug.server.shutdown')
            if shutdown_func is None:
                app.logger.warning('Werkzeug shutdown function not available')
            else:
                shutdown_func()
            return jsonify({'success': True}), 200
        except Exception as e:
            app.logger.error(f"Shutdown error: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500

def setup_request_handlers(app):
    """Setup request handlers for logging and timing."""
    import time
    from flask import g, request, jsonify
    from datetime import datetime
    
    @app.before_request
    def before_request():
        """Store the start time for the request."""
        g.start = time.time()
        g.request_id = os.urandom(16).hex()
        
        # Log the request
        app.logger.debug(
            f"Request: {request.method} {request.path}"
            f" - IP: {request.remote_addr}"
            f" - ID: {g.request_id}"
        )
    
    @app.after_request
    def after_request(response):
        """Log request completion and add timing headers."""
        # Calculate request duration
        duration = time.time() - g.get('start', time.time())
        
        # Add timing header
        response.headers['X-Request-Duration'] = f"{duration:.3f}s"
        
        # Log the response
        log_level = logging.INFO
        if response.status_code >= 400:
            log_level = logging.ERROR
        elif duration > 1.0:  # Log slow requests
            log_level = logging.WARNING
            
        app.logger.log(
            log_level,
            f"Response: {request.method} {request.path}"
            f" - Status: {response.status_code}"
            f" - Duration: {duration:.3f}s"
            f" - ID: {g.get('request_id', 'unknown')}"
        )
        
        return response

def register_error_handlers(app):
    """Register error handlers for common HTTP errors."""
    from flask import render_template, jsonify, request
    import werkzeug
    from datetime import datetime

    @app.errorhandler(400)
    def bad_request_error(error):
        app.logger.warning(f'Bad request: {error}')
        if request.is_json:
            return jsonify({'error': 'Bad request', 'message': str(error)}), 400
        return render_template('errors/400.html', error=error), 400

    @app.errorhandler(401)
    def unauthorized_error(error):
        app.logger.warning(f'Unauthorized access: {error}')
        if request.is_json:
            return jsonify({'error': 'Unauthorized', 'message': str(error)}), 401
        return render_template('errors/401.html', error=error), 401

    @app.errorhandler(403)
    def forbidden_error(error):
        app.logger.warning(f'Forbidden: {error}')
        if request.is_json:
            return jsonify({'error': 'Forbidden', 'message': str(error)}), 403
        return render_template('errors/403.html', error=error), 403

    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.warning(f'Not found: {request.url}')
        if request.is_json:
            return jsonify({'error': 'Not found', 'message': str(error)}), 404
        return render_template('errors/404.html', error=error), 404

    @app.errorhandler(405)
    def method_not_allowed_error(error):
        app.logger.warning(f'Method not allowed: {request.method} {request.url}')
        if request.is_json:
            return jsonify({'error': 'Method not allowed', 'message': str(error)}), 405
        return render_template('errors/405.html', error=error), 405

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f'Internal server error: {error}', exc_info=True)
        if request.is_json:
            return jsonify({'error': 'Internal server error', 'message': str(error)}), 500
        return render_template('errors/500.html', error=error), 500

    # Handle other werkzeug HTTP exceptions
    @app.errorhandler(werkzeug.exceptions.HTTPException)
    def handle_http_exception(error):
        app.logger.warning(f'HTTP Exception: {error}')
        if request.is_json:
            return jsonify({
                'error': error.name.lower().replace(' ', '_'),
                'message': error.description
            }), error.code
        return render_template(
            'errors/generic.html',
            error=error,
            title=error.name,
            message=error.description
        ), error.code
    
    # Register commands
    app.cli.add_command(init_db_command)
    
    # Setup logging for the application
    # Using the enhanced logger setup function with app context
    setup_logger(app)
    init_logger.info("Logging configured")
    
    # Set up template logging
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    template_handler = RotatingFileHandler(
        'logs/templates.log',
        maxBytes=10240,
        backupCount=5,
        delay=True
    )
    template_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s'
    ))
    template_logger.addHandler(template_handler)
    template_logger.setLevel(logging.INFO)
    
    access_handler = RotatingFileHandler(
        'logs/access.log',
        maxBytes=10240,
        backupCount=5,
        delay=True
    )
    access_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s'
    ))
    access_logger.addHandler(access_handler)
    access_logger.setLevel(logging.INFO)
    
    # Override Flask's render_template
    def custom_render_template(*args, **kwargs):
        """Custom render_template that logs template rendering."""
        try:
            template = app.jinja_env.get_template(args[0])
            context = dict(*args[1:], **kwargs) if len(args) > 1 else kwargs
            log_template_render(template, context, app)
            return render_template(*args, **kwargs)
        except Exception as e:
            app.logger.error(f"Error rendering template {args[0]}: {str(e)}")
            # Fallback to standard render_template if custom one fails
            return render_template(*args, **kwargs)
    
    app.custom_render_template = custom_render_template
    
    # Initialize roles
    with app.app_context():
        db.create_all()
        
        # Create roles if they don't exist
        roles = {
            'administrator': Permission.ADMINISTRATOR,
            'supervisor': (
                Permission.VIEW_INCIDENTS | Permission.CREATE_INCIDENTS |
                Permission.UPDATE_INCIDENTS | Permission.VIEW_UNITS |
                Permission.MANAGE_UNITS | Permission.VIEW_LOGS |
                Permission.VIEW_SETTINGS | Permission.VIEW_LOCATIONS |
                Permission.VIEW_PICKUP_POINTS
            ),
            'dispatcher': (
                Permission.VIEW_INCIDENTS | Permission.CREATE_INCIDENTS |
                Permission.UPDATE_INCIDENTS | Permission.VIEW_UNITS |
                Permission.VIEW_LOCATIONS | Permission.VIEW_PICKUP_POINTS
            ),
            'readonly': Permission.READ_ONLY
        }
        
        for role_name, permissions in roles.items():
            role = Role.query.filter_by(name=role_name).first()
            if role is None:
                role = Role(name=role_name, permissions=permissions)
                db.session.add(role)
                app.logger.info(f"Created role: {role_name}")
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error creating roles: {str(e)}")
            
        # Create default admin user if it doesn't exist
        admin_role = Role.query.filter_by(name='administrator').first()
        if admin_role:
            admin = User.query.filter_by(username='admin').first()
            if admin is None:
                admin = User(
                    username='admin',
                    email='admin@example.com',
                    first_name='Admin',
                    last_name='User',
                    role=admin_role,
                    active=True
                )
                admin.set_password('admin')  # Set default password
                db.session.add(admin)
                try:
                    db.session.commit()
                    app.logger.info("Created default admin user")
                except Exception as e:
                    db.session.rollback()
                    app.logger.error(f"Error creating admin user: {str(e)}")
        else:
            app.logger.error("Administrator role not found")
    
    # Initialize monitoring and scheduler (skip during tests or when disabled)
    if not (app.config.get('TESTING') or app.config.get('DISABLE_BACKGROUND_TASKS')):
        init_monitoring(app)
        init_scheduler(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID."""
        return db.session.get(User, int(user_id))
    
    @login_manager.unauthorized_handler
    def unauthorized():
        template_logger.warning("Unauthorized access attempt")
        return app.custom_render_template('auth/login.html'), 401
    
    @app.before_request
    def before_request():
        if current_user.is_authenticated:
            current_user.last_seen = datetime.utcnow()
            try:
                db.session.commit()
            except Exception as e:
                app.logger.error(f"Error updating last_seen: {str(e)}")
    
    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.error(f"404 error for URL: {request.url}")
        template_logger.error(f"404 error for URL: {request.url}")
        if request.is_json:
            return jsonify({'error': 'Not found'}), 404
        return custom_render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.error(f"500 error for URL: {request.url}, Error: {str(error)}")
        template_logger.error(f"500 error for URL: {request.url}, Error: {str(error)}")
        if request.is_json:
            return jsonify({'error': 'Internal server error'}), 500
        return custom_render_template('errors/500.html', error=str(error)), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        template_logger.error(f"403 error for URL: {request.url}, User: {current_user.username if not current_user.is_anonymous else 'Anonymous'}")
        return custom_render_template('errors/403.html'), 403
    
    @app.context_processor
    def inject_globals():
        """Inject global variables and utilities into all templates."""
        def format_datetime(value, format='%Y-%m-%d %H:%M:%S'):
            if value is None:
                return ""
            if isinstance(value, str):
                from datetime import datetime
                try:
                    value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    return value
            return value.strftime(format)
            
        return {
            'format_datetime': format_datetime,
            'Permission': Permission,
            'config': app.config,
            'current_user': current_user
        }
    
    def custom_render_template(template_name, **context):
        """Custom render_template that ensures all required context is available."""
        # Add any default context variables here
        default_context = {
            'current_user': current_user,
            'config': app.config,
            'request': request
        }
        # Update with any context passed in
        default_context.update(context)
        
        # Log template rendering for debugging
        template_logger.info(f"Rendering template: {template_name}")
        
        # Ensure we have a valid template name
        if not template_name or not isinstance(template_name, str):
            app.logger.error(f"Invalid template name: {template_name}")
            return "Error: Invalid template"
            
        # Render the template
        try:
            return render_template(template_name, **default_context)
        except Exception as e:
            app.logger.error(f"Error rendering template {template_name}: {str(e)}")
            # Try to render error template, but don't fail if that fails too
            try:
                return render_template('errors/500.html', error=str(e)), 500
            except:
                return f"Error rendering template: {str(e)}", 500
    
    app.logger.info('CAD System startup')
    
    # Initialize Socket.IO event handlers
    with app.app_context():
        websocket_init.init_socketio()
    
    return app

class ServerManager:
    def __init__(self, app):
        self.app = app
        self.server_running = False
        self.server_thread = None
        self.root = None
        self.status_label = None
        self.start_btn = None
        self.stop_btn = None
        # Server network config
        self.host = '0.0.0.0'
        try:
            # Prefer explicit APP_PORT env, then app config PORT, fallback 5000
            self.port = int(os.environ.get('APP_PORT') or app.config.get('PORT', 5000))
        except Exception:
            self.port = 5000
        # Generate a shutdown token and store in app config for validation
        self.shutdown_token = secrets.token_urlsafe(16)
        self.app.config['SHUTDOWN_TOKEN'] = self.shutdown_token
        
        # Initialize database
        with self.app.app_context():
            db.create_all()

    def create_gui(self):
        """Create the GUI window."""
        if tk is None:
            raise RuntimeError(
                'tkinter is not available; install python3-tk to use the desktop launcher'
            )
        self.root = tk.Tk()
        self.root.title("CAD System Server Manager")
        self.root.geometry("300x200")

        # Status label
        self.status_label = tk.Label(self.root, text="Server Status: Stopped")
        self.status_label.pack(pady=20)

        # Start button
        self.start_btn = tk.Button(self.root, text="Start Server", command=self.start_server)
        self.start_btn.pack(pady=10)

        # Stop button
        self.stop_btn = tk.Button(self.root, text="Stop Server", command=self.stop_server, state=tk.DISABLED)
        self.stop_btn.pack(pady=10)

        # Open browser button
        self.browser_btn = tk.Button(self.root, text="Open in Browser", command=self.open_browser)
        self.browser_btn.pack(pady=10)

    def start_server(self):
        """Start the server in a new thread."""
        if not self.server_running:
            self.server_thread = threading.Thread(target=self.run_server)
            self.server_thread.daemon = True
            self.server_running = True
            self.server_thread.start()
            self.status_label.config(text="Server Status: Starting...")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.root.after(1000, self.check_server_status)

    def check_server_status(self):
        """Check if server is running by attempting to connect to it."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('localhost', self.port))
            s.close()
            self.status_label.config(text="Server Status: Running")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
        except:
            self.status_label.config(text="Server Status: Stopped")
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.server_running = False
        
        if self.server_running:
            self.root.after(1000, self.check_server_status)

    def open_browser(self):
        """Open the application in default web browser."""
        webbrowser.open(f'http://localhost:{self.port}')

    def stop_server(self):
        """Stop the server."""
        if self.server_running:
            self.status_label.config(text="Server Status: Stopping...")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.DISABLED)
            # Call internal shutdown endpoint with token
            try:
                import urllib.request
                req = urllib.request.Request(
                    url=f"http://localhost:{self.port}/__shutdown",
                    method='POST',
                    headers={'X-Shutdown-Token': self.shutdown_token}
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    resp.read()
            except Exception as e:
                # Log but continue; the server thread should exit if running
                self.app.logger.warning(f"Shutdown request warning: {e}")
            finally:
                self.server_running = False
                # Allow some time for shutdown, then update status
                self.root.after(1000, self.check_server_status)

    def run_server(self):
        """Run the Flask-SocketIO server (supports WebSockets)."""
        try:
            # Use Flask-SocketIO's run to serve the app with WebSocket support
            # Avoid auto-reloader inside thread
            socketio.run(
                self.app,
                host=self.host,
                port=self.port,
                debug=self.app.config.get('DEBUG', False),
                use_reloader=False
            )
        except Exception as e:
            self.app.logger.error(f"Failed to start server: {e}")

    def run(self):
        """Start the GUI main loop."""
        self.create_gui()
        self.root.mainloop()

# Only create the application instance when running directly
if __name__ == '__main__':
    app = create_app()
    manager = ServerManager(app)
    manager.run()
