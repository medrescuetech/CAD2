import psutil
import logging
import threading
import time
from datetime import datetime, timedelta
import json
import sqlite3
import os
from flask import current_app
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from extensions import db
from models import SystemSetting

# Setup logger
logger = logging.getLogger('monitoring')

# Base class for ORM models
Base = declarative_base()

class SystemMetric(Base):
    """Model for system performance metrics."""
    __tablename__ = 'system_metrics'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    cpu_usage = Column(Float)
    memory_usage = Column(Float)
    memory_available = Column(Float)
    disk_usage = Column(Float)
    disk_free = Column(Float)
    process_memory = Column(Float)
    process_cpu = Column(Float)
    active_sessions = Column(Integer)
    response_time_avg = Column(Float)
    request_count = Column(Integer)
    error_count = Column(Integer)
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'cpu_usage': self.cpu_usage,
            'memory_usage': self.memory_usage,
            'memory_available': self.memory_available,
            'disk_usage': self.disk_usage,
            'disk_free': self.disk_free,
            'process_memory': self.process_memory,
            'process_cpu': self.process_cpu,
            'active_sessions': self.active_sessions,
            'response_time_avg': self.response_time_avg,
            'request_count': self.request_count,
            'error_count': self.error_count
        }


class SystemAlert(Base):
    """Model for system alerts and notifications."""
    __tablename__ = 'system_alerts'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    alert_type = Column(String(50), nullable=False)  # 'cpu', 'memory', 'disk', 'error', etc.
    severity = Column(String(20), nullable=False)  # 'info', 'warning', 'critical'
    message = Column(Text, nullable=False)
    value = Column(Float, nullable=True)  # The actual metric value
    threshold = Column(Float, nullable=True)  # The threshold that was exceeded
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'alert_type': self.alert_type,
            'severity': self.severity,
            'message': self.message,
            'value': self.value,
            'threshold': self.threshold,
            'acknowledged': self.acknowledged,
            'acknowledged_by': self.acknowledged_by,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }


class SystemMonitor:
    """System monitoring class that collects performance metrics."""
    
    def __init__(self, app=None, interval=60):
        """
        Initialize the system monitor.
        
        Args:
            app: Flask application instance
            interval: Monitoring interval in seconds (default: 60)
        """
        self.app = app
        self.interval = interval
        self.monitoring_thread = None
        self.stop_event = threading.Event()
        self.metrics_history = []
        self.max_history_size = 1440  # Store 24 hours of metrics (at 1-minute intervals)
        self.db_connection = None
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask application."""
        self.app = app
        
        # Create metrics table if it doesn't exist
        with app.app_context():
            engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
            Base.metadata.create_all(engine)
        
        # Register extension with app
        app.system_monitor = self
        
        # Create alert thresholds from system settings or use defaults
        self.update_alert_thresholds()
    
    def start_monitoring(self):
        """Start the monitoring thread."""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            logger.warning("Monitoring thread is already running")
            return
        
        logger.info("Starting system monitoring")
        self.stop_event.clear()
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
    
    def stop_monitoring(self):
        """Stop the monitoring thread."""
        logger.info("Stopping system monitoring")
        self.stop_event.set()
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
    
    def _monitoring_loop(self):
        """Main monitoring loop that collects metrics at specified intervals."""
        while not self.stop_event.is_set():
            try:
                metrics = self.collect_metrics()
                self._store_metrics(metrics)
                
                # Sleep for the specified interval
                # Use stop_event.wait() instead of time.sleep() to allow for clean shutdown
                self.stop_event.wait(self.interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                # Sleep a bit before retrying
                time.sleep(5)
    
    def collect_metrics(self):
        """
        Collect current system performance metrics.
        
        Returns:
            dict: Dictionary of collected metrics
        """
        try:
            # CPU metrics
            cpu_usage = psutil.cpu_percent(interval=1)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            memory_used_percent = memory.percent
            memory_available = memory.available
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            disk_free = disk.free
            
            # Process metrics
            process = psutil.Process(os.getpid())
            process_memory = process.memory_info().rss
            process_cpu = process.cpu_percent(interval=1.0)
            
            # Application metrics (placeholder values)
            # In a real implementation, these would be collected from the application
            active_sessions = 0
            response_time_avg = 0.0
            request_count = 0
            error_count = 0
            
            with self.app.app_context():
                # Get actual metrics from the application if available
                pass
            
            metrics = {
                'timestamp': datetime.utcnow(),
                'cpu_usage': cpu_usage,
                'memory_usage': memory_used_percent,
                'memory_available': memory_available,
                'disk_usage': disk_percent,
                'disk_free': disk_free,
                'process_memory': process_memory,
                'process_cpu': process_cpu,
                'active_sessions': active_sessions,
                'response_time_avg': response_time_avg,
                'request_count': request_count,
                'error_count': error_count
            }
            
            # Add to in-memory history (for quick access)
            self.metrics_history.append(metrics)
            
            # Trim history if it exceeds max size
            if len(self.metrics_history) > self.max_history_size:
                self.metrics_history = self.metrics_history[-self.max_history_size:]
            
            # Check thresholds and generate alerts
            self.check_thresholds(metrics)
            
            return metrics
        except Exception as e:
            logger.error(f"Error collecting metrics: {str(e)}")
            return None
    
    def _store_metrics(self, metrics):
        """
        Store metrics in the database.
        
        Args:
            metrics: Dictionary of metrics to store
        """
        if not metrics:
            return
        
        try:
            with self.app.app_context():
                engine = create_engine(self.app.config['SQLALCHEMY_DATABASE_URI'])
                Session = sessionmaker(bind=engine)
                session = Session()
                
                metric = SystemMetric(
                    timestamp=metrics['timestamp'],
                    cpu_usage=metrics['cpu_usage'],
                    memory_usage=metrics['memory_usage'],
                    memory_available=metrics['memory_available'],
                    disk_usage=metrics['disk_usage'],
                    disk_free=metrics['disk_free'],
                    process_memory=metrics['process_memory'],
                    process_cpu=metrics['process_cpu'],
                    active_sessions=metrics['active_sessions'],
                    response_time_avg=metrics['response_time_avg'],
                    request_count=metrics['request_count'],
                    error_count=metrics['error_count']
                )
                
                session.add(metric)
                session.commit()
                session.close()
        except Exception as e:
            logger.error(f"Error storing metrics: {str(e)}")
    
    def update_alert_thresholds(self):
        """Update alert thresholds from system settings."""
        try:
            with self.app.app_context():
                # Default thresholds
                self.thresholds = {
                    'cpu_usage_warning': 70.0,
                    'cpu_usage_critical': 90.0,
                    'memory_usage_warning': 75.0,
                    'memory_usage_critical': 90.0,
                    'disk_usage_warning': 80.0,
                    'disk_usage_critical': 95.0,
                    'disk_free_warning': 10 * 1024 * 1024 * 1024,  # 10 GB
                    'disk_free_critical': 5 * 1024 * 1024 * 1024,  # 5 GB
                    'error_count_warning': 10,
                    'error_count_critical': 50
                }
                
                # Update from database settings if they exist
                for key in self.thresholds.keys():
                    setting = SystemSetting.query.filter_by(name=key).first()
                    if setting and setting.value:
                        try:
                            self.thresholds[key] = float(setting.value)
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid threshold value for {key}: {setting.value}")
                
                logger.info("Updated monitoring alert thresholds")
        except Exception as e:
            logger.error(f"Error updating alert thresholds: {str(e)}")
    
    def check_thresholds(self, metrics):
        """
        Check if any metrics exceed defined thresholds and generate alerts.
        
        Args:
            metrics: Dictionary of collected metrics
        """
        if not hasattr(self, 'thresholds'):
            self.update_alert_thresholds()
            
        try:
            alerts = []
            
            # Check CPU usage
            if metrics['cpu_usage'] >= self.thresholds['cpu_usage_critical']:
                alerts.append({
                    'alert_type': 'cpu',
                    'severity': 'critical',
                    'message': f"CPU usage is critically high: {metrics['cpu_usage']}%",
                    'value': metrics['cpu_usage'],
                    'threshold': self.thresholds['cpu_usage_critical']
                })
            elif metrics['cpu_usage'] >= self.thresholds['cpu_usage_warning']:
                alerts.append({
                    'alert_type': 'cpu',
                    'severity': 'warning',
                    'message': f"CPU usage is high: {metrics['cpu_usage']}%",
                    'value': metrics['cpu_usage'],
                    'threshold': self.thresholds['cpu_usage_warning']
                })
            
            # Check memory usage
            if metrics['memory_usage'] >= self.thresholds['memory_usage_critical']:
                alerts.append({
                    'alert_type': 'memory',
                    'severity': 'critical',
                    'message': f"Memory usage is critically high: {metrics['memory_usage']}%",
                    'value': metrics['memory_usage'],
                    'threshold': self.thresholds['memory_usage_critical']
                })
            elif metrics['memory_usage'] >= self.thresholds['memory_usage_warning']:
                alerts.append({
                    'alert_type': 'memory',
                    'severity': 'warning',
                    'message': f"Memory usage is high: {metrics['memory_usage']}%",
                    'value': metrics['memory_usage'],
                    'threshold': self.thresholds['memory_usage_warning']
                })
            
            # Check disk usage
            if metrics['disk_usage'] >= self.thresholds['disk_usage_critical']:
                alerts.append({
                    'alert_type': 'disk',
                    'severity': 'critical',
                    'message': f"Disk usage is critically high: {metrics['disk_usage']}%",
                    'value': metrics['disk_usage'],
                    'threshold': self.thresholds['disk_usage_critical']
                })
            elif metrics['disk_usage'] >= self.thresholds['disk_usage_warning']:
                alerts.append({
                    'alert_type': 'disk',
                    'severity': 'warning',
                    'message': f"Disk usage is high: {metrics['disk_usage']}%",
                    'value': metrics['disk_usage'],
                    'threshold': self.thresholds['disk_usage_warning']
                })
            
            # Check disk free space
            if metrics['disk_free'] <= self.thresholds['disk_free_critical']:
                alerts.append({
                    'alert_type': 'disk_free',
                    'severity': 'critical',
                    'message': f"Disk free space is critically low: {metrics['disk_free'] / (1024*1024*1024):.1f} GB",
                    'value': metrics['disk_free'],
                    'threshold': self.thresholds['disk_free_critical']
                })
            elif metrics['disk_free'] <= self.thresholds['disk_free_warning']:
                alerts.append({
                    'alert_type': 'disk_free',
                    'severity': 'warning',
                    'message': f"Disk free space is low: {metrics['disk_free'] / (1024*1024*1024):.1f} GB",
                    'value': metrics['disk_free'],
                    'threshold': self.thresholds['disk_free_warning']
                })
            
            # Check error count
            if metrics['error_count'] >= self.thresholds['error_count_critical']:
                alerts.append({
                    'alert_type': 'error',
                    'severity': 'critical',
                    'message': f"Error count is critically high: {metrics['error_count']}",
                    'value': metrics['error_count'],
                    'threshold': self.thresholds['error_count_critical']
                })
            elif metrics['error_count'] >= self.thresholds['error_count_warning']:
                alerts.append({
                    'alert_type': 'error',
                    'severity': 'warning',
                    'message': f"Error count is high: {metrics['error_count']}",
                    'value': metrics['error_count'],
                    'threshold': self.thresholds['error_count_warning']
                })
            
            # Record alerts
            if alerts:
                self._store_alerts(alerts)
                
                # Notify administrators (stub for now)
                for alert in alerts:
                    if alert['severity'] == 'critical':
                        self._notify_alert(alert)
            
        except Exception as e:
            logger.error(f"Error checking thresholds: {str(e)}")
    
    def _store_alerts(self, alerts):
        """
        Store alerts in the database.
        
        Args:
            alerts: List of alert dictionaries
        """
        if not alerts:
            return
            
        try:
            # Create session
            engine = create_engine(self.app.config['SQLALCHEMY_DATABASE_URI'])
            Session = sessionmaker(bind=engine)
            session = Session()
            
            for alert_data in alerts:
                alert = SystemAlert(
                    alert_type=alert_data['alert_type'],
                    severity=alert_data['severity'],
                    message=alert_data['message'],
                    value=alert_data['value'],
                    threshold=alert_data['threshold']
                )
                session.add(alert)
            
            session.commit()
            session.close()
        except Exception as e:
            logger.error(f"Error storing alerts: {str(e)}")
    
    def _notify_alert(self, alert):
        """
        Send notification for critical alert.
        
        Args:
            alert: Alert dictionary
        """
        try:
            # This is a stub for notification delivery
            # In a real implementation, this would send an email, SMS, or other notification
            logger.warning(f"ALERT NOTIFICATION: {alert['message']}")
            
            # Check if email notifications are enabled
            with self.app.app_context():
                email_enabled = False
                email_setting = SystemSetting.query.filter_by(name='alert_email_enabled').first()
                if email_setting and email_setting.value.lower() == 'true':
                    email_enabled = True
                
                if email_enabled:
                    # Get email recipients
                    recipients = []
                    recipients_setting = SystemSetting.query.filter_by(name='alert_email_recipients').first()
                    if recipients_setting and recipients_setting.value:
                        recipients = recipients_setting.value.split(',')
                    
                    if recipients:
                        # Send email (placeholder)
                        logger.info(f"Would send email to: {', '.join(recipients)}")
                        logger.info(f"Email subject: CAD System Alert: {alert['severity'].upper()} - {alert['alert_type']}")
                        logger.info(f"Email body: {alert['message']}")
        except Exception as e:
            logger.error(f"Error sending alert notification: {str(e)}")
    
    def get_alerts(self, limit=100, severity=None, resolved=None):
        """
        Get recent system alerts.
        
        Args:
            limit: Maximum number of alerts to return
            severity: Filter by severity (info, warning, critical)
            resolved: Filter by resolved status (True/False)
            
        Returns:
            list: List of alert dictionaries
        """
        try:
            # Create session
            engine = create_engine(self.app.config['SQLALCHEMY_DATABASE_URI'])
            Session = sessionmaker(bind=engine)
            session = Session()
            
            # Build query
            query = session.query(SystemAlert).order_by(SystemAlert.timestamp.desc())
            
            if severity:
                query = query.filter(SystemAlert.severity == severity)
            
            if resolved is not None:
                query = query.filter(SystemAlert.resolved == resolved)
                
            alerts = query.limit(limit).all()
            result = [alert.to_dict() for alert in alerts]
            
            session.close()
            return result
        except Exception as e:
            logger.error(f"Error retrieving alerts: {str(e)}")
            return []
    
    def acknowledge_alert(self, alert_id, username):
        """
        Acknowledge an alert.
        
        Args:
            alert_id: ID of the alert to acknowledge
            username: Username of the user acknowledging the alert
            
        Returns:
            bool: Success status
        """
        try:
            # Create session
            engine = create_engine(self.app.config['SQLALCHEMY_DATABASE_URI'])
            Session = sessionmaker(bind=engine)
            session = Session()
            
            alert = session.query(SystemAlert).get(alert_id)
            if not alert:
                session.close()
                return False
                
            alert.acknowledged = True
            alert.acknowledged_by = username
            alert.acknowledged_at = datetime.utcnow()
            
            session.commit()
            session.close()
            return True
        except Exception as e:
            logger.error(f"Error acknowledging alert {alert_id}: {str(e)}")
            return False
    
    def resolve_alert(self, alert_id):
        """
        Mark an alert as resolved.
        
        Args:
            alert_id: ID of the alert to resolve
            
        Returns:
            bool: Success status
        """
        try:
            # Create session
            engine = create_engine(self.app.config['SQLALCHEMY_DATABASE_URI'])
            Session = sessionmaker(bind=engine)
            session = Session()
            
            alert = session.query(SystemAlert).get(alert_id)
            if not alert:
                session.close()
                return False
                
            alert.resolved = True
            alert.resolved_at = datetime.utcnow()
            
            session.commit()
            session.close()
            return True
        except Exception as e:
            logger.error(f"Error resolving alert {alert_id}: {str(e)}")
            return False
    
    def get_metrics(self, start_time=None, end_time=None, limit=100):
        """
        Get metrics from the database.
        
        Args:
            start_time: Start time for metrics query
            end_time: End time for metrics query
            limit: Maximum number of records to return
            
        Returns:
            list: List of metric dictionaries
        """
        try:
            with self.app.app_context():
                engine = create_engine(self.app.config['SQLALCHEMY_DATABASE_URI'])
                Session = sessionmaker(bind=engine)
                session = Session()
                
                query = session.query(SystemMetric).order_by(SystemMetric.timestamp.desc())
                
                if start_time:
                    query = query.filter(SystemMetric.timestamp >= start_time)
                if end_time:
                    query = query.filter(SystemMetric.timestamp <= end_time)
                
                metrics = query.limit(limit).all()
                result = [metric.to_dict() for metric in metrics]
                
                session.close()
                return result
        except Exception as e:
            logger.error(f"Error retrieving metrics: {str(e)}")
            return []
    
    def get_recent_metrics(self, minutes=60):
        """
        Get recent metrics from memory.
        
        Args:
            minutes: Number of minutes of history to return
            
        Returns:
            list: List of recent metrics
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        recent_metrics = [m for m in self.metrics_history if m['timestamp'] >= cutoff_time]
        return recent_metrics
    
    def get_system_status(self):
        """
        Get a summary of the current system status.
        
        Returns:
            dict: System status summary
        """
        if not self.metrics_history:
            return {
                'status': 'unknown',
                'message': 'No metrics available'
            }
        
        # Get latest metrics
        latest = self.metrics_history[-1]
        
        # Define thresholds for warnings
        cpu_warning = 80
        memory_warning = 80
        disk_warning = 80
        
        # Check for warning conditions
        warnings = []
        if latest['cpu_usage'] > cpu_warning:
            warnings.append(f"CPU usage is high: {latest['cpu_usage']}%")
        if latest['memory_usage'] > memory_warning:
            warnings.append(f"Memory usage is high: {latest['memory_usage']}%")
        if latest['disk_usage'] > disk_warning:
            warnings.append(f"Disk usage is high: {latest['disk_usage']}%")
        
        status = 'healthy'
        if warnings:
            status = 'warning'
        
        return {
            'status': status,
            'warnings': warnings,
            'last_update': latest['timestamp'].isoformat(),
            'metrics': {
                'cpu_usage': latest['cpu_usage'],
                'memory_usage': latest['memory_usage'],
                'disk_usage': latest['disk_usage']
            }
        }
    
    def cleanup_old_metrics(self, days=30):
        """
        Clean up metrics older than the specified number of days.
        
        Args:
            days: Number of days of metrics to keep
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            with self.app.app_context():
                engine = create_engine(self.app.config['SQLALCHEMY_DATABASE_URI'])
                Session = sessionmaker(bind=engine)
                session = Session()
                
                # Count records to be deleted
                count = session.query(SystemMetric).filter(
                    SystemMetric.timestamp < cutoff_date
                ).count()
                
                # Delete old records
                session.query(SystemMetric).filter(
                    SystemMetric.timestamp < cutoff_date
                ).delete()
                
                session.commit()
                session.close()
                
                logger.info(f"Cleaned up {count} metrics older than {days} days")
        except Exception as e:
            logger.error(f"Error cleaning up old metrics: {str(e)}")


# Global instance for the monitoring system
monitor = SystemMonitor()


def init_app(app):
    """Initialize the monitoring system with the Flask app."""
    global monitor
    
    # Initialize monitoring
    monitor.init_app(app)
    
    # Start monitoring if enabled in app config
    if app.config.get('ENABLE_SYSTEM_MONITORING', True):
        monitor.start_monitoring()
    
    # Clean up metrics older than 30 days on startup
    # This will run once when the application starts
    monitor.cleanup_old_metrics(days=30)
