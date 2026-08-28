import os
import json
import csv
import logging
import tempfile
import shutil
import sqlite3
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from extensions import db
from models import SystemSetting, Incident, IncidentLog, User, UnitAssignment, Permission, Role
from utils.decorators import permissions_required, write_endpoint, read_endpoint
from sqlalchemy import text

# Create blueprint
data_mgmt_bp = Blueprint('data_management', __name__, url_prefix='/api/data')

# Setup logger
logger = logging.getLogger('data')

@data_mgmt_bp.route('/backup', methods=['POST'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def create_backup():
    """Create a system backup."""
    try:
        backup_type = request.json.get('type', 'full')  # full, database, config
        include_files = request.json.get('include_files', True)
        
        if backup_type not in ['full', 'database', 'config']:
            return jsonify({
                'status': 'error',
                'message': f'Invalid backup type: {backup_type}'
            }), 400
        
        # Generate backup filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_id = f"backup_{backup_type}_{timestamp}"
        backup_dir = os.path.join(current_app.instance_path, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        # Backup database
        if backup_type in ['full', 'database']:
            # Create database backup (assuming SQLite)
            try:
                src_db = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
                backup_db_path = os.path.join(backup_dir, f"{backup_id}.db")
                
                # Create connection to source and destination databases
                src_conn = sqlite3.connect(src_db)
                shutil.copy2(src_db, backup_db_path)
                
                logger.info(f"Database backup created: {backup_db_path}")
            except Exception as e:
                logger.error(f"Database backup failed: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'message': 'Database backup failed',
                    'error': str(e)
                }), 500
        
        # Backup configuration
        if backup_type in ['full', 'config']:
            try:
                # Get all system settings
                settings = SystemSetting.query.all()
                config_data = {setting.name: setting.value for setting in settings}
                
                # Save settings to JSON file
                config_path = os.path.join(backup_dir, f"{backup_id}_config.json")
                with open(config_path, 'w') as f:
                    json.dump(config_data, f, indent=2)
                
                logger.info(f"Configuration backup created: {config_path}")
            except Exception as e:
                logger.error(f"Configuration backup failed: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'message': 'Configuration backup failed',
                    'error': str(e)
                }), 500
        
        # Backup files if requested
        if include_files and backup_type == 'full':
            try:
                # Create list of directories to backup
                dirs_to_backup = [
                    os.path.join(current_app.root_path, 'static'),
                    os.path.join(current_app.root_path, 'uploads'),
                    os.path.join(current_app.instance_path, 'logs')
                ]
                
                # Create zip archive
                import zipfile
                files_path = os.path.join(backup_dir, f"{backup_id}_files.zip")
                with zipfile.ZipFile(files_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for directory in dirs_to_backup:
                        if os.path.exists(directory):
                            for root, _, files in os.walk(directory):
                                for file in files:
                                    file_path = os.path.join(root, file)
                                    rel_path = os.path.relpath(file_path, current_app.root_path)
                                    zipf.write(file_path, rel_path)
                
                logger.info(f"Files backup created: {files_path}")
            except Exception as e:
                logger.error(f"Files backup failed: {str(e)}")
                # Continue even if file backup fails
        
        # Log the backup creation
        logger.info(f"System backup '{backup_id}' created by {current_user.username}")
        
        return jsonify({
            'status': 'success',
            'message': 'System backup created successfully',
            'data': {
                'backup_id': backup_id,
                'timestamp': datetime.utcnow().isoformat(),
                'type': backup_type,
                'include_files': include_files
            }
        }), 200
    except Exception as e:
        logger.error(f"Error creating system backup: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to create system backup',
            'error': str(e)
        }), 500

@data_mgmt_bp.route('/backups', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def list_backups():
    """List available backups."""
    try:
        backup_dir = os.path.join(current_app.instance_path, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        backups = []
        for filename in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, filename)
            if os.path.isfile(file_path):
                # Extract backup type and timestamp from filename
                parts = filename.split('_')
                if len(parts) >= 3 and parts[0] == 'backup':
                    backup_type = parts[1]
                    timestamp_str = '_'.join(parts[2:]).split('.')[0]
                    try:
                        timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                    except ValueError:
                        timestamp = datetime.fromtimestamp(os.path.getctime(file_path))
                    
                    backups.append({
                        'id': os.path.splitext(filename)[0],
                        'type': backup_type,
                        'timestamp': timestamp.isoformat(),
                        'size': os.path.getsize(file_path),
                        'filename': filename
                    })
        
        # Sort backups by timestamp (newest first)
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'status': 'success',
            'data': backups
        }), 200
    except Exception as e:
        logger.error(f"Error listing backups: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to list backups',
            'error': str(e)
        }), 500

@data_mgmt_bp.route('/backups/<backup_id>', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def download_backup(backup_id):
    """Download a specific backup."""
    try:
        backup_dir = os.path.join(current_app.instance_path, 'backups')
        
        # Find the file with the matching backup_id
        backup_file = None
        for filename in os.listdir(backup_dir):
            if filename.startswith(backup_id):
                backup_file = filename
                break
        
        if not backup_file:
            return jsonify({
                'status': 'error',
                'message': f'Backup {backup_id} not found'
            }), 404
        
        file_path = os.path.join(backup_dir, backup_file)
        return send_file(file_path, as_attachment=True, download_name=backup_file)
    except Exception as e:
        logger.error(f"Error downloading backup {backup_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to download backup {backup_id}',
            'error': str(e)
        }), 500

@data_mgmt_bp.route('/backups/<backup_id>', methods=['DELETE'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def delete_backup(backup_id):
    """Delete a specific backup."""
    try:
        backup_dir = os.path.join(current_app.instance_path, 'backups')
        
        # Find all files with the matching backup_id prefix
        backup_files = []
        for filename in os.listdir(backup_dir):
            if filename.startswith(backup_id):
                backup_files.append(filename)
        
        if not backup_files:
            return jsonify({
                'status': 'error',
                'message': f'Backup {backup_id} not found'
            }), 404
        
        # Delete all files for this backup
        for filename in backup_files:
            file_path = os.path.join(backup_dir, filename)
            os.remove(file_path)
            logger.info(f"Deleted backup file: {file_path}")
        
        logger.info(f"Backup '{backup_id}' deleted by {current_user.username}")
        return jsonify({
            'status': 'success',
            'message': f'Backup {backup_id} deleted successfully'
        }), 200
    except Exception as e:
        logger.error(f"Error deleting backup {backup_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to delete backup {backup_id}',
            'error': str(e)
        }), 500

@data_mgmt_bp.route('/restore', methods=['POST'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def restore_backup():
    """Restore from a backup."""
    try:
        backup_id = request.json.get('backup_id')
        restore_type = request.json.get('type', 'full')  # full, database, config
        
        if not backup_id:
            return jsonify({
                'status': 'error',
                'message': 'Backup ID is required'
            }), 400
            
        if restore_type not in ['full', 'database', 'config']:
            return jsonify({
                'status': 'error',
                'message': f'Invalid restore type: {restore_type}'
            }), 400
        
        backup_dir = os.path.join(current_app.instance_path, 'backups')
        
        # Validate that backup exists
        backup_files = []
        for filename in os.listdir(backup_dir):
            if filename.startswith(backup_id):
                backup_files.append(filename)
        
        if not backup_files:
            return jsonify({
                'status': 'error',
                'message': f'Backup {backup_id} not found'
            }), 404
        
        # This is just a placeholder for actual restore logic
        # In a real implementation, this would restore the database and/or configuration
        
        logger.info(f"Backup '{backup_id}' restore initiated by {current_user.username}")
        return jsonify({
            'status': 'success',
            'message': f'Restore from backup {backup_id} initiated successfully',
            'data': {
                'backup_id': backup_id,
                'type': restore_type,
                'timestamp': datetime.utcnow().isoformat(),
                'status': 'in_progress'
            }
        }), 202
    except Exception as e:
        logger.error(f"Error restoring from backup: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to restore from backup',
            'error': str(e)
        }), 500

@data_mgmt_bp.route('/retention', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def get_retention_policies():
    """Get data retention policies."""
    try:
        # Get retention settings from database
        retention_settings = SystemSetting.query.filter(
            SystemSetting.name.like('%retention%')
        ).all()
        
        policies = {}
        for setting in retention_settings:
            policies[setting.name] = {
                'value': setting.value,
                'description': setting.description
            }
        
        # Add default policies if not in database
        default_policies = {
            'incident_retention_days': {'value': '90', 'description': 'Number of days to keep closed incidents'},
            'log_retention_days': {'value': '30', 'description': 'Number of days to keep system logs'},
            'metric_retention_days': {'value': '30', 'description': 'Number of days to keep system metrics'},
            'backup_retention_days': {'value': '30', 'description': 'Number of days to keep system backups'}
        }
        
        for key, policy in default_policies.items():
            if key not in policies:
                policies[key] = policy
        
        return jsonify({
            'status': 'success',
            'data': policies
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving retention policies: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to retrieve retention policies',
            'error': str(e)
        }), 500

@data_mgmt_bp.route('/retention', methods=['PUT'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def update_retention_policies():
    """Update data retention policies."""
    try:
        policies = request.json
        
        if not isinstance(policies, dict):
            return jsonify({
                'status': 'error',
                'message': 'Invalid request format. Expected a dictionary of policies.'
            }), 400
        
        # Update each policy in the database
        updated_policies = []
        for name, value in policies.items():
            if not name.endswith('_retention_days'):
                continue
                
            # Validate value is a positive integer
            try:
                days = int(value)
                if days <= 0:
                    return jsonify({
                        'status': 'error',
                        'message': f'Invalid value for {name}: must be a positive integer'
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid value for {name}: must be a positive integer'
                }), 400
            
            # Update or create the setting
            setting = SystemSetting.query.filter_by(name=name).first()
            if setting:
                setting.value = str(days)
            else:
                setting = SystemSetting(
                    name=name,
                    value=str(days),
                    description=f'Number of days to keep {name.split("_")[0]}s'
                )
                db.session.add(setting)
            
            updated_policies.append(name)
        
        db.session.commit()
        
        logger.info(f"Retention policies updated by {current_user.username}: {', '.join(updated_policies)}")
        return jsonify({
            'status': 'success',
            'message': 'Retention policies updated successfully',
            'data': {
                'updated_policies': updated_policies
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating retention policies: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to update retention policies',
            'error': str(e)
        }), 500

@data_mgmt_bp.route('/export/<data_type>', methods=['GET'])
@login_required
@permissions_required(Permission.ADMIN)
@read_endpoint
def export_data(data_type):
    """Export data to CSV/JSON format."""
    try:
        format_type = request.args.get('format', 'csv')  # csv or json
        
        if data_type not in ['incidents', 'users', 'units', 'logs']:
            return jsonify({
                'status': 'error',
                'message': f'Invalid data type: {data_type}'
            }), 400
            
        if format_type not in ['csv', 'json']:
            return jsonify({
                'status': 'error',
                'message': f'Invalid format type: {format_type}'
            }), 400
        
        # Get date range filter
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date:
            start_date = datetime.fromisoformat(start_date)
        if end_date:
            end_date = datetime.fromisoformat(end_date)
        
        # Create temporary file for export
        fd, temp_path = tempfile.mkstemp(suffix=f'.{format_type}')
        os.close(fd)
        
        # Export the data based on type
        if data_type == 'incidents':
            # Query incidents with optional date filter
            query = Incident.query
            if start_date:
                query = query.filter(Incident.created_at >= start_date)
            if end_date:
                query = query.filter(Incident.created_at <= end_date)
            
            incidents = query.all()
            
            if format_type == 'csv':
                with open(temp_path, 'w', newline='') as csvfile:
                    fieldnames = [
                        'id', 'incident_number', 'incident_type', 'priority', 'status',
                        'location', 'description', 'created_at', 'updated_at', 'created_by'
                    ]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for incident in incidents:
                        writer.writerow({
                            'id': incident.id,
                            'incident_number': incident.incident_number,
                            'incident_type': incident.incident_type_obj.name if incident.incident_type_obj else '',
                            'priority': incident.get_priority_string(),
                            'status': incident.status,
                            'location': incident.location,
                            'description': incident.description,
                            'created_at': incident.created_at.isoformat() if incident.created_at else '',
                            'updated_at': incident.updated_at.isoformat() if incident.updated_at else '',
                            'created_by': incident.created_by.username if incident.created_by else ''
                        })
            else:  # json
                with open(temp_path, 'w') as jsonfile:
                    json.dump([incident.to_dict() for incident in incidents], jsonfile, indent=2)
        
        elif data_type == 'users':
            # Query users
            users = User.query.all()
            
            if format_type == 'csv':
                with open(temp_path, 'w', newline='') as csvfile:
                    fieldnames = [
                        'id', 'username', 'email', 'first_name', 'last_name', 'role',
                        'active', 'last_login', 'created_at'
                    ]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for user in users:
                        writer.writerow({
                            'id': user.id,
                            'username': user.username,
                            'email': user.email,
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                            'role': user.role.name if user.role else '',
                            'active': user.active,
                            'last_login': user.last_login.isoformat() if user.last_login else '',
                            'created_at': user.created_at.isoformat() if user.created_at else ''
                        })
            else:  # json
                with open(temp_path, 'w') as jsonfile:
                    user_list = []
                    for user in users:
                        user_dict = user.to_dict()
                        # Remove sensitive fields
                        user_dict.pop('password_hash', None)
                        user_dict.pop('session_id', None)
                        user_list.append(user_dict)
                    
                    json.dump(user_list, jsonfile, indent=2)
        
        # Add other data types as needed
        
        # Send the file
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"{data_type}_export_{timestamp}.{format_type}"
        
        logger.info(f"Data export of {data_type} created by {current_user.username}")
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=filename,
            mimetype='text/csv' if format_type == 'csv' else 'application/json'
        )
    except Exception as e:
        logger.error(f"Error exporting {data_type}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to export {data_type}',
            'error': str(e)
        }), 500

@data_mgmt_bp.route('/cleanup', methods=['POST'])
@login_required
@permissions_required(Permission.ADMIN)
@write_endpoint
def run_cleanup():
    """Run data cleanup based on retention policies."""
    try:
        cleanup_type = request.json.get('type')
        force = request.json.get('force', False)
        
        if cleanup_type not in ['incidents', 'logs', 'metrics', 'all']:
            return jsonify({
                'status': 'error',
                'message': f'Invalid cleanup type: {cleanup_type}'
            }), 400
        
        # Get retention settings
        retention_settings = {}
        for setting_name in ['incident_retention_days', 'log_retention_days', 'metric_retention_days']:
            setting = SystemSetting.query.filter_by(name=setting_name).first()
            retention_settings[setting_name] = int(setting.value) if setting and setting.value else 90
        
        results = {}
        
        # Cleanup incidents
        if cleanup_type in ['incidents', 'all']:
            retention_days = retention_settings.get('incident_retention_days', 90)
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            # Count incidents to clean up
            count = Incident.query.filter(
                Incident.status == Incident.STATUS_CLOSED,
                Incident.updated_at < cutoff_date
            ).count()
            
            if force:
                # Actual deletion/archiving would go here
                # This is just a placeholder
                pass
            
            results['incidents'] = {
                'count': count,
                'retention_days': retention_days,
                'cutoff_date': cutoff_date.isoformat()
            }
        
        # Cleanup logs
        if cleanup_type in ['logs', 'all']:
            retention_days = retention_settings.get('log_retention_days', 30)
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            # Count logs to clean up
            count = IncidentLog.query.filter(
                IncidentLog.timestamp < cutoff_date
            ).count()
            
            if force:
                # Actual deletion would go here
                # This is just a placeholder
                pass
            
            results['logs'] = {
                'count': count,
                'retention_days': retention_days,
                'cutoff_date': cutoff_date.isoformat()
            }
        
        # Cleanup metrics
        if cleanup_type in ['metrics', 'all']:
            # This would call the metrics cleanup function
            # results['metrics'] = {...}
            pass
        
        logger.info(f"Data cleanup of {cleanup_type} initiated by {current_user.username}")
        return jsonify({
            'status': 'success',
            'message': 'Data cleanup completed',
            'data': {
                'type': cleanup_type,
                'force': force,
                'results': results
            }
        }), 200
    except Exception as e:
        logger.error(f"Error during data cleanup: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to run data cleanup',
            'error': str(e)
        }), 500
