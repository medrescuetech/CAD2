"""
Application Configuration Module

This module defines configuration classes for different environments.
"""

import os
import secrets
from datetime import timedelta
from sqlalchemy.pool import StaticPool, QueuePool

class Config:
    """Base configuration class."""
    # Security Settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(16)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    
    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour in seconds
    
    # Database Settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'check_same_thread': False},  # Allow SQLite to be used with multiple threads
        'poolclass': StaticPool  # Use a single connection for all threads
    }
    
    # Application Base URL
    BASE_URL = os.environ.get('BASE_URL') or 'http://localhost:5000'
    
    # Logging Settings
    LOG_LEVEL = 'INFO'
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT = 10
    
    # SMTP Email Settings
    SMTP_SERVER = os.environ.get('SMTP_SERVER') or 'smtp.example.com'
    SMTP_PORT = int(os.environ.get('SMTP_PORT') or 587)
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME') or 'user@example.com'
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD') or 'password'
    SMTP_SENDER = os.environ.get('SMTP_SENDER') or 'cad-system@example.com'
    SMTP_USE_TLS = True
    SMTP_USE_SSL = False
    
    # Email Template Settings
    EMAIL_TEMPLATE_DIR = 'templates/email'
    
    # Notification Settings
    NOTIFICATIONS_ENABLED = True
    
    # Security Settings for Password Reset
    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT') or secrets.token_hex(16)
    PASSWORD_RESET_TIMEOUT = 3600  # 1 hour in seconds
    
    # CORS Configuration
    CORS_ORIGINS = [
        'http://localhost:5000',
        'http://127.0.0.1:5000',
        'http://localhost:3000',
        'http://127.0.0.1:3000',
    ]
    
    # Content Security Policy Report URI (for reporting CSP violations)
    CSP_REPORT_URI = os.environ.get('CSP_REPORT_URI')  # e.g., 'https://your-domain.report-uri.com/r/d/csp/enforce'
    
    # Email Settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'cad@example.com'
    
    # Session Settings
    SESSION_LIFETIME = int(os.environ.get('SESSION_LIFETIME') or 1440)  # 24 hours, in minutes
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = os.environ.get('SESSION_FILE_DIR') or 'session_files'
    
    # Rate Limiting
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"
    RATELIMIT_STRATEGY = "fixed-window"
    
    # Geospatial Settings
    DEFAULT_LATITUDE = -20.7256  # Port Hedland, WA
    DEFAULT_LONGITUDE = 116.8464
    MAX_DISTANCE_KM = 100
    
    # Feature Flags
    ENABLE_WEBSOCKET = True
    ENABLE_REAL_TIME_NOTIFICATIONS = True
    ENABLE_EMAIL_NOTIFICATIONS = True
    
    # IP Access Control Settings
    ENABLE_IP_RESTRICTIONS = True
    IP_ALLOWLIST_ONLY = False  # False = blacklist mode (block specific IPs), True = allowlist mode (only allow specific IPs)
    
    @staticmethod
    def init_app(app):
        """Initialize application with this configuration."""
        pass


class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    EMAIL_TESTING = True  # Don't actually send emails in development
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        app.logger.info('Development configuration initialized')


class TestingConfig(Config):
    """Testing environment configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    EMAIL_TESTING = True  # Don't actually send emails in testing
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        app.logger.info('Testing configuration initialized')


class ProductionConfig(Config):
    """Production environment configuration."""
    LOG_LEVEL = 'ERROR'
    
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,  # 30 seconds
        'poolclass': QueuePool
    }
    
    # Configure production-specific handlers
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Check for SECRET_KEY only when this config is actually being used
        if os.environ.get('SECRET_KEY') is None:
            raise RuntimeError('SECRET_KEY environment variable is not set')
        
        # Configure production-specific handlers
        import logging
        from logging.handlers import RotatingFileHandler
        os.makedirs('logs', exist_ok=True)
        file_handler = RotatingFileHandler(
            'logs/error.log',
            maxBytes=Config.LOG_MAX_BYTES,
            backupCount=Config.LOG_BACKUP_COUNT
        )
        file_handler.setLevel(logging.ERROR)
        app.logger.addHandler(file_handler)
        app.logger.info('Production configuration initialized')


# Configuration dictionary for easy access
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
