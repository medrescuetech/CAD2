from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from models import SystemSetting, Permission
from utils.decorators import permissions_required, write_endpoint, read_endpoint
from utils.validation import validate_json_schema, SYSTEM_SETTINGS_SCHEMA
import json
import logging
import psutil
import os
import platform
from datetime import datetime, timedelta
from utils.monitoring import monitor
from utils.scheduler import scheduler

# Create blueprint
system_admin_bp = Blueprint('system_admin', __name__, url_prefix='/api/system')

# Setup logger
logger = logging.getLogger('system')

@system_admin_bp.route('/settings', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_settings():
    """Get all system settings."""
    try:
        settings = SystemSetting.query.all()
        return jsonify({
            'status': 'success',
            'data': [
                {
                    'id': setting.id,
                    'name': setting.name,
                    'value': setting.value,
                    'description': setting.description,
                    'created_at': setting.created_at.isoformat() if setting.created_at else None,
                    'updated_at': setting.updated_at.isoformat() if setting.updated_at else None
                } for setting in settings
            ]
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving system settings: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve system settings',
            'error': str(e)
        }), 500

@system_admin_bp.route('/settings/<int:setting_id>', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_setting(setting_id):
    """Get a specific system setting by ID."""
    try:
        setting = SystemSetting.query.get(setting_id)
        if not setting:
            return jsonify({
                'status': 'error',
                'message': f'Setting with ID {setting_id} not found'
            }), 404
            
        return jsonify({
            'status': 'success',
            'data': {
                'id': setting.id,
                'name': setting.name,
                'value': setting.value,
                'description': setting.description,
                'created_at': setting.created_at.isoformat() if setting.created_at else None,
                'updated_at': setting.updated_at.isoformat() if setting.updated_at else None
            }
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving system setting {setting_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to retrieve system setting with ID {setting_id}',
            'error': str(e)
        }), 500

@system_admin_bp.route('/settings', methods=['POST'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def create_setting():
    """Create a new system setting."""
    try:
        # Validate request data
        data = request.get_json()
        validate_json_schema(data, SYSTEM_SETTINGS_SCHEMA)
        
        # Check if setting with the same name already exists
        existing_setting = SystemSetting.query.filter_by(name=data['name']).first()
        if existing_setting:
            return jsonify({
                'status': 'error',
                'message': f'Setting with name "{data["name"]}" already exists'
            }), 400
            
        # Create new setting
        new_setting = SystemSetting(
            name=data['name'],
            value=data['value'],
            description=data.get('description', '')
        )
        
        db.session.add(new_setting)
        db.session.commit()
        
        logger.info(f"System setting '{data['name']}' created by {current_user.username}")
        return jsonify({
            'status': 'success',
            'message': 'System setting created successfully',
            'data': {
                'id': new_setting.id,
                'name': new_setting.name,
                'value': new_setting.value,
                'description': new_setting.description,
                'created_at': new_setting.created_at.isoformat() if new_setting.created_at else None,
                'updated_at': new_setting.updated_at.isoformat() if new_setting.updated_at else None
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating system setting: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to create system setting',
            'error': str(e)
        }), 500

@system_admin_bp.route('/settings/<int:setting_id>', methods=['PUT'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def update_setting(setting_id):
    """Update an existing system setting."""
    try:
        # Validate request data
        data = request.get_json()
        validate_json_schema(data, SYSTEM_SETTINGS_SCHEMA)
        
        # Check if setting exists
        setting = SystemSetting.query.get(setting_id)
        if not setting:
            return jsonify({
                'status': 'error',
                'message': f'Setting with ID {setting_id} not found'
            }), 404
            
        # Check if name is being changed and if it conflicts with an existing setting
        if 'name' in data and data['name'] != setting.name:
            existing_setting = SystemSetting.query.filter_by(name=data['name']).first()
            if existing_setting and existing_setting.id != setting_id:
                return jsonify({
                    'status': 'error',
                    'message': f'Setting with name "{data["name"]}" already exists'
                }), 400
        
        # Update setting
        if 'name' in data:
            setting.name = data['name']
        if 'value' in data:
            setting.value = data['value']
        if 'description' in data:
            setting.description = data['description']
            
        db.session.commit()
        
        logger.info(f"System setting '{setting.name}' updated by {current_user.username}")
        return jsonify({
            'status': 'success',
            'message': 'System setting updated successfully',
            'data': {
                'id': setting.id,
                'name': setting.name,
                'value': setting.value,
                'description': setting.description,
                'created_at': setting.created_at.isoformat() if setting.created_at else None,
                'updated_at': setting.updated_at.isoformat() if setting.updated_at else None
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating system setting {setting_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to update system setting with ID {setting_id}',
            'error': str(e)
        }), 500

@system_admin_bp.route('/settings/<int:setting_id>', methods=['DELETE'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def delete_setting(setting_id):
    """Delete a system setting."""
    try:
        # Check if setting exists
        setting = SystemSetting.query.get(setting_id)
        if not setting:
            return jsonify({
                'status': 'error',
                'message': f'Setting with ID {setting_id} not found'
            }), 404
            
        setting_name = setting.name
        db.session.delete(setting)
        db.session.commit()
        
        logger.info(f"System setting '{setting_name}' deleted by {current_user.username}")
        return jsonify({
            'status': 'success',
            'message': f'System setting "{setting_name}" deleted successfully'
        }), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting system setting {setting_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to delete system setting with ID {setting_id}',
            'error': str(e)
        }), 500

@system_admin_bp.route('/health', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def system_health():
    """Get system health information."""
    try:
        # CPU usage
        cpu_usage = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_used_percent = memory.percent
        memory_total = memory.total
        memory_available = memory.available
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_total = disk.total
        disk_used = disk.used
        disk_free = disk.free
        disk_percent = disk.percent
        
        # Process info
        process = psutil.Process(os.getpid())
        process_memory = process.memory_info().rss
        process_create_time = datetime.fromtimestamp(process.create_time()).isoformat()
        process_cpu_percent = process.cpu_percent(interval=1.0)
        
        # System info
        uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
        uptime_hours = uptime.total_seconds() / 3600
        
        # Database connection status
        db_status = "Connected"
        try:
            db.session.execute("SELECT 1")
        except Exception as e:
            db_status = f"Disconnected: {str(e)}"
        
        # App info
        app_start_time = datetime.fromtimestamp(process.create_time())
        app_uptime = datetime.now() - app_start_time
        app_uptime_hours = app_uptime.total_seconds() / 3600
        
        return jsonify({
            'status': 'success',
            'data': {
                'system': {
                    'platform': platform.platform(),
                    'python_version': platform.python_version(),
                    'uptime_hours': round(uptime_hours, 2),
                    'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat()
                },
                'cpu': {
                    'usage_percent': cpu_usage,
                    'count': cpu_count
                },
                'memory': {
                    'total_bytes': memory_total,
                    'available_bytes': memory_available,
                    'used_percent': memory_used_percent
                },
                'disk': {
                    'total_bytes': disk_total,
                    'used_bytes': disk_used,
                    'free_bytes': disk_free,
                    'used_percent': disk_percent
                },
                'process': {
                    'memory_bytes': process_memory,
                    'cpu_percent': process_cpu_percent,
                    'start_time': process_create_time,
                    'uptime_hours': round(app_uptime_hours, 2)
                },
                'database': {
                    'status': db_status
                },
                'timestamp': datetime.utcnow().isoformat()
            }
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving system health information: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve system health information',
            'error': str(e)
        }), 500

@system_admin_bp.route('/backup', methods=['POST'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def create_backup():
    """Create a system backup."""
    try:
        # Placeholder for actual backup functionality
        # In a real implementation, this would create a database dump and/or file backup
        
        backup_time = datetime.utcnow()
        backup_id = f"backup_{backup_time.strftime('%Y%m%d_%H%M%S')}"
        
        # Log the backup creation
        logger.info(f"System backup '{backup_id}' initiated by {current_user.username}")
        
        return jsonify({
            'status': 'success',
            'message': 'System backup initiated successfully',
            'data': {
                'backup_id': backup_id,
                'timestamp': backup_time.isoformat(),
                'status': 'in_progress'
            }
        }), 202
    except Exception as e:
        logger.error(f"Error creating system backup: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to create system backup',
            'error': str(e)
        }), 500

@system_admin_bp.route('/logs', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_system_logs():
    """Get system logs."""
    try:
        # Parameters for filtering logs
        log_type = request.args.get('type', 'system')  # system, access, audit, error
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        # Placeholder for actual log retrieval
        # In a real implementation, this would query logs from the database or log files
        
        # Mock log data for demonstration
        logs = [
            {
                'timestamp': (datetime.utcnow() - timedelta(minutes=i)).isoformat(),
                'level': 'INFO',
                'message': f'Sample log message {i}',
                'source': log_type,
                'user': 'system'
            } for i in range(limit)
        ]
        
        return jsonify({
            'status': 'success',
            'data': {
                'logs': logs,
                'total': 1000,  # Total number of logs (mock value)
                'limit': limit,
                'offset': offset
            }
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving system logs: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve system logs',
            'error': str(e)
        }), 500

@system_admin_bp.route('/maintenance', methods=['POST'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def run_maintenance():
    """Run system maintenance tasks."""
    try:
        task_type = request.json.get('task', 'cleanup')  # cleanup, optimize, vacuum
        
        if task_type not in ['cleanup', 'optimize', 'vacuum']:
            return jsonify({
                'status': 'error',
                'message': f'Invalid maintenance task type: {task_type}'
            }), 400
        
        # Log the maintenance task
        logger.info(f"System maintenance task '{task_type}' initiated by {current_user.username}")
        
        # Placeholder for actual maintenance tasks
        # In a real implementation, this would run database optimization, cleanup old data, etc.
        
        return jsonify({
            'status': 'success',
            'message': f'System maintenance task "{task_type}" initiated successfully',
            'data': {
                'task': task_type,
                'timestamp': datetime.utcnow().isoformat(),
                'status': 'in_progress'
            }
        }), 202
    except Exception as e:
        logger.error(f"Error running system maintenance: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to run system maintenance',
            'error': str(e)
        }), 500

# Task Scheduler Endpoints

@system_admin_bp.route('/tasks', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_scheduled_tasks():
    """Get all scheduled tasks."""
    try:
        tasks = scheduler.get_task_status()
        return jsonify({
            'status': 'success',
            'data': tasks
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving scheduled tasks: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve scheduled tasks',
            'error': str(e)
        }), 500

@system_admin_bp.route('/tasks/<task_name>', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_scheduled_task(task_name):
    """Get a specific scheduled task."""
    try:
        task = scheduler.get_task_status(task_name)
        if not task:
            return jsonify({
                'status': 'error',
                'message': f'Task {task_name} not found'
            }), 404
        
        return jsonify({
            'status': 'success',
            'data': task
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving task {task_name}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to retrieve task {task_name}',
            'error': str(e)
        }), 500

@system_admin_bp.route('/tasks/<task_name>/run', methods=['POST'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def run_scheduled_task(task_name):
    """Run a scheduled task immediately."""
    try:
        success = scheduler.run_task_now(task_name)
        
        if not success:
            return jsonify({
                'status': 'error',
                'message': f'Failed to run task {task_name}'
            }), 400
        
        logger.info(f"Task {task_name} manually executed by {current_user.username}")
        return jsonify({
            'status': 'success',
            'message': f'Task {task_name} started successfully'
        }), 200
    except Exception as e:
        logger.error(f"Error running task {task_name}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to run task {task_name}',
            'error': str(e)
        }), 500

@system_admin_bp.route('/tasks/<task_name>/enable', methods=['POST'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def enable_task(task_name):
    """Enable a scheduled task."""
    try:
        # Get enabled status from request or default to true
        enabled = request.json.get('enabled', True) if request.json else True
        
        success = scheduler.enable_task(task_name, enabled)
        
        if not success:
            return jsonify({
                'status': 'error',
                'message': f'Task {task_name} not found'
            }), 404
        
        status = "enabled" if enabled else "disabled"
        logger.info(f"Task {task_name} {status} by {current_user.username}")
        
        return jsonify({
            'status': 'success',
            'message': f'Task {task_name} {status} successfully'
        }), 200
    except Exception as e:
        logger.error(f"Error enabling/disabling task {task_name}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to modify task {task_name}',
            'error': str(e)
        }), 500

@system_admin_bp.route('/tasks/<task_name>/config', methods=['PUT'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def update_task_config(task_name):
    """Update task configuration."""
    try:
        data = request.get_json()
        
        max_retries = data.get('max_retries')
        retry_delay = data.get('retry_delay')
        
        if max_retries is not None:
            try:
                max_retries = int(max_retries)
                if max_retries < 0:
                    return jsonify({
                        'status': 'error',
                        'message': 'max_retries must be a non-negative integer'
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'status': 'error',
                    'message': 'max_retries must be a non-negative integer'
                }), 400
        
        if retry_delay is not None:
            try:
                retry_delay = int(retry_delay)
                if retry_delay < 0:
                    return jsonify({
                        'status': 'error',
                        'message': 'retry_delay must be a non-negative integer'
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'status': 'error',
                    'message': 'retry_delay must be a non-negative integer'
                }), 400
        
        success = scheduler.update_task_config(task_name, max_retries, retry_delay)
        
        if not success:
            return jsonify({
                'status': 'error',
                'message': f'Task {task_name} not found'
            }), 404
        
        logger.info(f"Task {task_name} configuration updated by {current_user.username}")
        return jsonify({
            'status': 'success',
            'message': f'Task {task_name} configuration updated successfully'
        }), 200
    except Exception as e:
        logger.error(f"Error updating task {task_name} configuration: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to update task {task_name} configuration',
            'error': str(e)
        }), 500

@system_admin_bp.route('/tasks/<task_name>/history', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_task_history(task_name):
    """Get task execution history."""
    try:
        limit = request.args.get('limit', 100, type=int)
        status = request.args.get('status')
        
        if task_name == '_all':
            # Get history for all tasks
            task_name = None
        
        history = scheduler.get_task_history(task_name, limit, status)
        
        return jsonify({
            'status': 'success',
            'data': history
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving task history for {task_name}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve task history',
            'error': str(e)
        }), 500

@system_admin_bp.route('/tasks/<task_name>/stats', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_task_stats(task_name):
    """Get task execution statistics."""
    try:
        days = request.args.get('days', 7, type=int)
        
        if task_name == '_all':
            # Get stats for all tasks
            task_name = None
        
        stats = scheduler.get_task_stats(task_name, days)
        
        return jsonify({
            'status': 'success',
            'data': stats
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving task stats for {task_name}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve task statistics',
            'error': str(e)
        }), 500

# System Monitoring Endpoints

@system_admin_bp.route('/monitoring/metrics', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_system_metrics():
    """Get system metrics."""
    try:
        # Get query parameters
        minutes = request.args.get('minutes', type=int)
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        limit = request.args.get('limit', 100, type=int)
        
        if minutes:
            # Get recent metrics from memory
            metrics = monitor.get_recent_metrics(minutes=minutes)
            return jsonify({
                'status': 'success',
                'data': metrics
            }), 200
        else:
            # Get metrics from database with optional time range
            start = datetime.fromisoformat(start_time) if start_time else None
            end = datetime.fromisoformat(end_time) if end_time else None
            metrics = monitor.get_metrics(start_time=start, end_time=end, limit=limit)
            return jsonify({
                'status': 'success',
                'data': metrics
            }), 200
    except Exception as e:
        logger.error(f"Error retrieving system metrics: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve system metrics',
            'error': str(e)
        }), 500

@system_admin_bp.route('/monitoring/status', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_monitoring_status():
    """Get system monitoring status."""
    try:
        status = monitor.get_system_status()
        
        return jsonify({
            'status': 'success',
            'data': status
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving monitoring status: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve monitoring status',
            'error': str(e)
        }), 500

@system_admin_bp.route('/alerts', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_alerts():
    """Get system alerts."""
    try:
        limit = request.args.get('limit', 100, type=int)
        severity = request.args.get('severity', None)
        resolved = request.args.get('resolved', None)
        
        if resolved is not None:
            resolved = resolved.lower() == 'true'
        
        alerts = monitor.get_alerts(limit=limit, severity=severity, resolved=resolved)
        
        return jsonify({
            'status': 'success',
            'data': alerts
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving system alerts: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve system alerts',
            'error': str(e)
        }), 500

@system_admin_bp.route('/alerts/<int:alert_id>/acknowledge', methods=['POST'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def acknowledge_alert(alert_id):
    """Acknowledge a system alert."""
    try:
        success = monitor.acknowledge_alert(alert_id, current_user.username)
        
        if not success:
            return jsonify({
                'status': 'error',
                'message': f'Alert with ID {alert_id} not found'
            }), 404
        
        logger.info(f"Alert {alert_id} acknowledged by {current_user.username}")
        return jsonify({
            'status': 'success',
            'message': 'Alert acknowledged successfully'
        }), 200
    except Exception as e:
        logger.error(f"Error acknowledging alert {alert_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to acknowledge alert',
            'error': str(e)
        }), 500

@system_admin_bp.route('/alerts/<int:alert_id>/resolve', methods=['POST'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def resolve_alert(alert_id):
    """Mark a system alert as resolved."""
    try:
        success = monitor.resolve_alert(alert_id)
        
        if not success:
            return jsonify({
                'status': 'error',
                'message': f'Alert with ID {alert_id} not found'
            }), 404
        
        logger.info(f"Alert {alert_id} resolved by {current_user.username}")
        return jsonify({
            'status': 'success',
            'message': 'Alert resolved successfully'
        }), 200
    except Exception as e:
        logger.error(f"Error resolving alert {alert_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to resolve alert',
            'error': str(e)
        }), 500

@system_admin_bp.route('/alert-thresholds', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_alert_thresholds():
    """Get system alert thresholds."""
    try:
        # Ensure thresholds are up to date
        monitor.update_alert_thresholds()
        
        if not hasattr(monitor, 'thresholds'):
            return jsonify({
                'status': 'error',
                'message': 'Alert thresholds not initialized'
            }), 500
        
        return jsonify({
            'status': 'success',
            'data': monitor.thresholds
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving alert thresholds: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve alert thresholds',
            'error': str(e)
        }), 500

@system_admin_bp.route('/alert-thresholds', methods=['PUT'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def update_alert_thresholds():
    """Update system alert thresholds."""
    try:
        data = request.get_json()
        
        # Validate that the thresholds are numbers
        for key, value in data.items():
            try:
                float_value = float(value)
                
                # Create or update the system setting
                setting = SystemSetting.query.filter_by(name=key).first()
                if setting:
                    setting.value = str(float_value)
                else:
                    setting = SystemSetting(
                        name=key,
                        value=str(float_value),
                        description=f"Alert threshold for {key}"
                    )
                    db.session.add(setting)
            except (ValueError, TypeError):
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid value for {key}: {value}. Must be a number.'
                }), 400
        
        db.session.commit()
        
        # Update the monitor's thresholds
        monitor.update_alert_thresholds()
        
        logger.info(f"Alert thresholds updated by {current_user.username}")
        return jsonify({
            'status': 'success',
            'message': 'Alert thresholds updated successfully',
            'data': monitor.thresholds
        }), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating alert thresholds: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to update alert thresholds',
            'error': str(e)
        }), 500

@system_admin_bp.route('/alert-notifications', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_alert_notification_settings():
    """Get alert notification settings."""
    try:
        settings = {}
        
        # Get email notification settings
        email_enabled = SystemSetting.query.filter_by(name='alert_email_enabled').first()
        settings['email_enabled'] = email_enabled.value.lower() == 'true' if email_enabled else False
        
        email_recipients = SystemSetting.query.filter_by(name='alert_email_recipients').first()
        settings['email_recipients'] = email_recipients.value.split(',') if email_recipients and email_recipients.value else []
        
        return jsonify({
            'status': 'success',
            'data': settings
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving alert notification settings: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve alert notification settings',
            'error': str(e)
        }), 500

@system_admin_bp.route('/alert-notifications', methods=['PUT'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def update_alert_notification_settings():
    """Update alert notification settings."""
    try:
        data = request.get_json()
        
        # Update email notification settings
        if 'email_enabled' in data:
            email_enabled = 'true' if data['email_enabled'] else 'false'
            email_setting = SystemSetting.query.filter_by(name='alert_email_enabled').first()
            if email_setting:
                email_setting.value = email_enabled
            else:
                email_setting = SystemSetting(
                    name='alert_email_enabled',
                    value=email_enabled,
                    description="Enable email notifications for system alerts"
                )
                db.session.add(email_setting)
        
        if 'email_recipients' in data:
            recipients = ','.join(data['email_recipients']) if isinstance(data['email_recipients'], list) else data['email_recipients']
            recipients_setting = SystemSetting.query.filter_by(name='alert_email_recipients').first()
            if recipients_setting:
                recipients_setting.value = recipients
            else:
                recipients_setting = SystemSetting(
                    name='alert_email_recipients',
                    value=recipients,
                    description="Email recipients for system alert notifications"
                )
                db.session.add(recipients_setting)
        
        db.session.commit()
        logger.info(f"Alert notification settings updated by {current_user.username}")
        
        return jsonify({
            'status': 'success',
            'message': 'Alert notification settings updated successfully'
        }), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating alert notification settings: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to update alert notification settings',
            'error': str(e)
        }), 500
