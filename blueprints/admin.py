from flask import Blueprint, render_template, abort, redirect, url_for, flash, request, jsonify, current_app, make_response, send_file, Response
from flask_login import login_required, current_user
from models import Permission, User, Role, Location, Unit, UnitType, Incident, SystemSetting, PickupPoint, AMPDSProtocol, APIKey
from extensions import db, socketio
from functools import wraps
import logging
import json
import os
import secrets
import io
import csv
from datetime import datetime, timedelta
from sqlalchemy import func

# Create the admin blueprint
admin = Blueprint('admin', __name__, url_prefix='/admin')

@admin.context_processor
def inject_permissions():
    return dict(Permission=Permission)

def admin_required(f):
    """Decorator for routes that require admin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.can(Permission.ADMINISTRATOR):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def permission_required(permission):
    """Decorator for routes that require specific permissions."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.can(permission):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def permission_required_ajax(permission):
    """Decorator that checks if the current user has the specified permission.
    
    For API/AJAX routes that should return JSON instead of redirecting.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.can(permission):
                return jsonify({
                    'success': False,
                    'message': 'Permission denied. You do not have the required permission.',
                    'required_permission': str(permission)
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def role_required(role_name):
    """Decorator that checks if the current user has the specified role.
    
    Args:
        role_name: The name of the role required to access the route.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
                
            # Check if the user has the required role
            if not current_user.has_role(role_name):
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('pages.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def validate_request_data(data, required_fields):
    """Validate that the request contains all required fields.
    
    Args:
        data: The data to validate
        required_fields: List of required field names
        
    Returns:
        Tuple (is_valid, error_message)
    """
    if not data:
        return False, "No data provided"
        
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
        
    return True, None

@admin.route('/dashboard')
@login_required
@admin_required
def index():
    """Admin dashboard."""
    # Get system stats
    stats = {
        'total_users': User.query.count(),
        'active_units': Unit.query.filter(Unit.status != 'Out of Service').count(),
        'total_units': Unit.query.count(),
        'open_incidents': Incident.query.filter(Incident.status.in_(['active', 'pending'])).count(),
        'system_health': 'Good'  # You might want to implement actual health checks
    }
    
    # Get recent activity
    recent_incidents = Incident.query.order_by(Incident.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    return current_app.custom_render_template('admin/dashboard.html', 
                         stats=stats,
                         recent_incidents=recent_incidents,
                         recent_users=recent_users)

@admin.route('/logs')
@login_required
@admin_required
@permission_required(Permission.ADMIN)
def system_logs():
    """View system logs page."""
    return current_app.custom_render_template('admin/logs.html')

@admin.route('/logs/export', methods=['POST'])
@login_required
@admin_required
@permission_required(Permission.MANAGE_LOGS)
def export_logs():
    """Export system logs."""
    try:
        # Implementation for log export
        return send_file(
            'path_to_logs.csv',
            as_attachment=True,
            download_name='system_logs.csv'
        )
    except Exception as e:
        flash(f'Error exporting logs: {str(e)}', 'danger')
        return redirect(url_for('admin.system_logs'))

@admin.route('/users')
@login_required
@permission_required(Permission.VIEW_USERS)
def users():
    """Display user management page."""
    users = User.query.all()
    roles = Role.query.all()
    role_templates = {
        'Admin': 'Full system access',
        'Supervisor': 'Manage users and incidents',
        'Dispatcher': 'Handle incidents and units',
        'Basic': 'View-only access'
    }
    return current_app.custom_render_template('admin/users.html', users=users, roles=roles, role_templates=role_templates)

@admin.route('/users/<int:user_id>/permissions', methods=['GET'])
@login_required
@admin_required
@permission_required(Permission.MANAGE_USERS)
def get_user_permissions(user_id):
    """Get user permissions."""
    user = User.query.get_or_404(user_id)
    return jsonify({
        'success': True,
        'permissions': user.get_permissions()
    })

@admin.route('/users/<int:user_id>/permissions', methods=['POST'])
@login_required
@admin_required
@permission_required(Permission.MANAGE_USERS)
def update_user_permissions(user_id):
    """Update user permissions."""
    data = request.get_json()
    permissions = []
    
    # Convert permission values to Permission flags
    for perm_value in data.get('permissions', []):
        for perm in Permission.__members__.values():
            if perm.value == perm_value:
                permissions.append(perm)
                break
    
    try:
        PermissionManager.update_user_permissions(user_id, permissions)
        return jsonify({'message': 'Permissions updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@admin.route('/users/<int:user_id>/edit', methods=['POST'])
@login_required
@admin_required
@permission_required(Permission.MANAGE_USERS)
def edit_user(user_id):
    """Edit user."""
    user = User.query.get_or_404(user_id)
    
    # Update user fields
    user.username = request.form.get('username', user.username)
    user.email = request.form.get('email', user.email)
    user.first_name = request.form.get('first_name', user.first_name)
    user.last_name = request.form.get('last_name', user.last_name)
    user.active = request.form.get('active', user.active) == 'true'
    
    # Update role if provided
    role_id = request.form.get('role_id')
    if role_id:
        role = Role.query.get(role_id)
        if role:
            user.role = role
    
    try:
        db.session.commit()
        flash('User updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating user: {str(e)}', 'danger')
    
    return redirect(url_for('admin.users'))

@admin.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required(Permission.MANAGE_USERS)
def delete_user(user_id):
    """Delete user."""
    if current_user.id == user_id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin.users'))
    
    user = User.query.get_or_404(user_id)
    try:
        db.session.delete(user)
        db.session.commit()
        flash('User deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
    
    return redirect(url_for('admin.users'))

@admin.route('/roles')
@login_required
@admin_required
@permission_required(Permission.VIEW_USERS)
def roles():
    """Display role management page."""
    roles = Role.query.all()
    return current_app.custom_render_template('admin/roles.html', roles=roles)

@admin.route('/roles/<int:role_id>/edit', methods=['POST'])
@login_required
@admin_required
@permission_required(Permission.MANAGE_USERS)
def edit_role(role_id):
    """Edit role."""
    role = Role.query.get_or_404(role_id)
    
    # Update role fields
    role.name = request.form.get('name', role.name)
    role.description = request.form.get('description', role.description)
    
    # Update permissions
    permissions = request.form.getlist('permissions[]')
    role.permissions = sum(int(p) for p in permissions if p.isdigit())
    
    try:
        db.session.commit()
        flash('Role updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating role: {str(e)}', 'danger')
    
    return redirect(url_for('admin.roles'))

@admin.route('/locations')
@login_required
@admin_required
@permission_required(Permission.MANAGE_GEOSPATIAL)
def locations():
    """Location management page."""
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(url_for('admin.locations'))
            
        file = request.files['csv_file']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('admin.locations'))
            
        if not file.filename.endswith('.csv'):
            flash('File must be a CSV', 'danger')
            return redirect(url_for('admin.locations'))
            
        try:
            import csv
            import io
            
            # Read CSV file
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_data = csv.DictReader(stream)
            
            locations_added = 0
            locations_updated = 0
            
            for row in csv_data:
                # Check if location already exists
                location = Location.query.filter_by(name=row['name']).first()
                
                try:
                    latitude = float(row.get('latitude', 0))
                    longitude = float(row.get('longitude', 0))
                except ValueError:
                    continue
                    
                if location:
                    # Update existing location
                    location.latitude = latitude
                    location.longitude = longitude
                    locations_updated += 1
                else:
                    # Create new location
                    location = Location(
                        name=row['name'],
                        latitude=latitude,
                        longitude=longitude
                    )
                    db.session.add(location)
                    locations_added += 1
                    
            db.session.commit()
            
            flash(f'Successfully imported {locations_added} new locations and updated {locations_updated} existing locations.', 'success')
            
        except Exception as e:
            logging.error(f'Error importing locations: {str(e)}')
            flash('Error importing locations. Please check the file format and try again.', 'danger')
            
        return redirect(url_for('admin.locations'))
    
    # GET request
    locations = Location.query.order_by(Location.name).all()
    return current_app.custom_render_template('admin/locations.html', locations=locations)

@admin.route('/pickup-points')
@login_required
@admin_required
@permission_required(Permission.VIEW_PICKUP_POINTS)
def pickup_points():
    """Display pickup points management page."""
    pickup_points = PickupPoint.query.all()
    return current_app.custom_render_template('admin/pickup_points.html', pickup_points=pickup_points)

@admin.route('/reports')
@login_required
@admin_required
def reports():
    """Display reports dashboard."""
    return current_app.custom_render_template('admin/reports.html')

@admin.route('/reports/incidents')
@login_required
@admin_required
def incident_reports():
    """Display incident reports."""
    incidents = Incident.query.order_by(Incident.created_at.desc()).all()
    return current_app.custom_render_template('admin/reports/incidents.html', incidents=incidents)

@admin.route('/reports/units')
@login_required
@admin_required
def unit_reports():
    """Display unit reports."""
    units = Unit.query.order_by(Unit.unit_number).all()
    return current_app.custom_render_template('admin/reports/units.html', units=units)

@admin.route('/reports/system')
@login_required
@admin_required
def system_reports():
    """Display system reports."""
    return current_app.custom_render_template('admin/reports/system.html')

@admin.route('/import/<data_type>', methods=['POST'])
@login_required
@admin_required
def import_csv(data_type):
    """Handle CSV imports for various data types."""
    if 'csv_file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for(f'admin.{data_type}'))
        
    file = request.files['csv_file']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for(f'admin.{data_type}'))
        
    if not file.filename.endswith('.csv'):
        flash('File must be a CSV', 'danger')
        return redirect(url_for(f'admin.{data_type}'))
        
    try:
        # Read file content
        stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
        
        # Process based on data type
        if data_type == 'locations':
            result = CSVHandler.import_locations(stream)
        elif data_type == 'users':
            result = CSVHandler.import_users(stream)
        elif data_type == 'units':
            result = CSVHandler.import_units(stream)
        elif data_type == 'ampds':
            result = CSVHandler.import_ampds(stream)
        else:
            flash('Invalid data type', 'danger')
            return redirect(url_for('admin.index'))
            
        if 'error' in result:
            flash(f'Error importing data: {result["error"]}', 'danger')
        else:
            flash(f'Successfully imported {result["added"]} new records and updated {result["updated"]} existing records.', 'success')
            if result['errors']:
                flash(f'There were {len(result["errors"])} errors during import. Check the logs for details.', 'warning')
                for error in result['errors']:
                    logging.warning(f'CSV Import Error ({data_type}): {error}')
                    
    except Exception as e:
        flash(f'Error processing file: {str(e)}', 'danger')
        
    return redirect(url_for(f'admin.{data_type}'))

@admin.route('/export/<data_type>')
@login_required
@admin_required
def export_csv(data_type):
    """Handle CSV exports for various data types."""
    try:
        # Get CSV data based on type
        if data_type == 'locations':
            csv_data = CSVHandler.export_locations()
            filename = 'locations.csv'
        elif data_type == 'users':
            csv_data = CSVHandler.export_users()
            filename = 'users.csv'
        elif data_type == 'units':
            csv_data = CSVHandler.export_units()
            filename = 'units.csv'
        elif data_type == 'ampds':
            csv_data = CSVHandler.export_ampds()
            filename = 'ampds.csv'
        else:
            flash('Invalid data type', 'danger')
            return redirect(url_for('admin.index'))
            
        # Create response with CSV data
        response = make_response(csv_data)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'danger')
        return redirect(url_for('admin.index'))

@admin.route('/settings')
@login_required
@admin_required
@permission_required(Permission.VIEW_SETTINGS)
def settings():
    """Display and update system settings."""
    if request.method == 'POST':
        # Handle settings update
        try:
            setting_name = request.form.get('setting_name')
            setting_value = request.form.get('setting_value')
            
            # Update setting in database
            setting = SystemSetting.query.filter_by(name=setting_name).first()
            if setting:
                setting.value = setting_value
                db.session.commit()
                flash(f'Setting {setting_name} updated successfully.', 'success')
            else:
                flash(f'Setting {setting_name} not found.', 'error')
                
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating setting: {str(e)}")
            flash('An error occurred while updating the setting.', 'error')
            
    # Get all settings
    settings = SystemSetting.query.all()
    return current_app.custom_render_template('admin/settings.html', settings=settings)

@admin.route('/smtp', methods=['GET', 'POST'])
@login_required
@admin_required
def smtp_settings():
    """Display and update SMTP settings."""
    # Get current SMTP settings
    smtp_settings = {
        'smtp_server': current_app.config.get('MAIL_SERVER', ''),
        'smtp_port': current_app.config.get('MAIL_PORT', 587),
        'smtp_username': current_app.config.get('MAIL_USERNAME', ''),
        'smtp_password': '', # Don't expose the password
        'smtp_use_tls': current_app.config.get('MAIL_USE_TLS', True),
        'smtp_use_ssl': current_app.config.get('MAIL_USE_SSL', False),
        'smtp_default_sender': current_app.config.get('MAIL_DEFAULT_SENDER', '')
    }
    
    if request.method == 'POST':
        # Get form data
        mail_server = request.form.get('mail_server')
        mail_port = request.form.get('mail_port')
        mail_username = request.form.get('mail_username')
        mail_password = request.form.get('mail_password')
        mail_use_tls = 'mail_use_tls' in request.form
        mail_use_ssl = 'mail_use_ssl' in request.form
        mail_default_sender_name = request.form.get('mail_default_sender_name', 'CAD System')
        mail_default_sender = request.form.get('mail_default_sender')

        # Validate form data
        if not all([mail_server, mail_port, mail_username, mail_default_sender]):
            flash('Please fill out all required fields.', 'danger')
            return render_template('admin/smtp_settings.html', smtp_settings=smtp_settings)

        try:
            # Convert port to integer
            mail_port = int(mail_port)
        except ValueError:
            flash('Port must be a valid number.', 'danger')
            return render_template('admin/smtp_settings.html', smtp_settings=smtp_settings)

        # Update settings in SystemSettings table
        settings_to_update = {
            'MAIL_SERVER': mail_server,
            'MAIL_PORT': mail_port,
            'MAIL_USERNAME': mail_username,
            'MAIL_USE_TLS': mail_use_tls,
            'MAIL_USE_SSL': mail_use_ssl,
            'MAIL_DEFAULT_SENDER': mail_default_sender
        }

        # Only update password if provided
        if mail_password:
            settings_to_update['MAIL_PASSWORD'] = mail_password

        # Save sender name if provided
        if mail_default_sender_name:
            settings_to_update['MAIL_DEFAULT_SENDER_NAME'] = mail_default_sender_name

        # Update settings in database
        for key, value in settings_to_update.items():
            setting = SystemSetting.query.filter_by(name=key).first()
            if setting:
                setting.value = str(value)
            else:
                setting = SystemSetting(name=key, value=str(value), 
                                        description=f"SMTP configuration: {key}")
            db.session.add(setting)

        try:
            db.session.commit()
            
            # Update config in the current app
            for key, value in settings_to_update.items():
                current_app.config[key] = value
                
            flash('SMTP settings saved successfully.', 'success')
            
            # Log the configuration change
            logging.getLogger('admin').info(
                f"SMTP settings updated by {current_user.username}"
            )
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving settings: {str(e)}', 'danger')
            logging.getLogger('error').error(f"Error saving SMTP settings: {str(e)}")

        # Refresh settings
        smtp_settings = {
            'smtp_server': current_app.config.get('MAIL_SERVER', ''),
            'smtp_port': current_app.config.get('MAIL_PORT', 587),
            'smtp_username': current_app.config.get('MAIL_USERNAME', ''),
            'smtp_password': '', # Don't expose the password
            'smtp_use_tls': current_app.config.get('MAIL_USE_TLS', True),
            'smtp_use_ssl': current_app.config.get('MAIL_USE_SSL', False),
            'smtp_default_sender': current_app.config.get('MAIL_DEFAULT_SENDER', ''),
            'sender_name': current_app.config.get('MAIL_DEFAULT_SENDER_NAME', 'CAD System')
        }

    return render_template('admin/smtp_settings.html', smtp_settings=smtp_settings)

@admin.route('/settings/get/v2', methods=['GET'])
@login_required
@admin_required
def get_settings_v2():
    """Get system settings."""
    try:
        settings = SystemSetting.query.all()
        return jsonify({
            'status': 'success',
            'data': [{'id': s.id, 'name': s.name, 'value': s.value} for s in settings]
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@admin.route('/api/ampds', methods=['POST'])
@login_required
@permission_required_ajax(Permission.MANAGE_SETTINGS)
def add_ampds_protocol():
    """Add a new AMPDS protocol."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Validate required fields
    required_fields = ['code', 'description', 'category', 'priority']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    # Check if protocol already exists
    existing = AMPDSProtocol.query.filter_by(unique_id=data['code']).first()
    if existing:
        return jsonify({'error': f'Protocol with code {data["code"]} already exists'}), 400
    
    # Create new protocol
    protocol = AMPDSProtocol(
        unique_id=data['code'],
        category=data['category'],
        card_number=data['code'],  # Assuming code includes card number
        priority=data['priority'],
        subcategory=data['description'],
        dispatch_advice=data.get('advice', ''),
        prearrival_pdf=data.get('pdf', '')
    )
    
    try:
        db.session.add(protocol)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Protocol added successfully',
            'protocol': protocol.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error adding protocol: {str(e)}'}), 500

@admin.route('/api/ampds/<code>', methods=['GET'])
@login_required
@permission_required_ajax(Permission.VIEW_SETTINGS)
def get_ampds_protocol(code):
    """Get an AMPDS protocol by code."""
    protocol = AMPDSProtocol.query.filter_by(unique_id=code).first()
    if not protocol:
        return jsonify({'error': f'Protocol with code {code} not found'}), 404
    
    return jsonify(protocol.to_dict())

@admin.route('/api/ampds/<code>', methods=['PUT'])
@login_required
@permission_required_ajax(Permission.MANAGE_SETTINGS)
def update_ampds_protocol(code):
    """Update an existing AMPDS protocol."""
    protocol = AMPDSProtocol.query.filter_by(unique_id=code).first()
    if not protocol:
        return jsonify({'error': f'Protocol with code {code} not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Update protocol fields
    if 'description' in data:
        protocol.subcategory = data['description']
    if 'category' in data:
        protocol.category = data['category']
    if 'priority' in data:
        protocol.priority = data['priority']
    if 'advice' in data:
        protocol.dispatch_advice = data['advice']
    if 'pdf' in data:
        protocol.prearrival_pdf = data['pdf']
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Protocol updated successfully',
            'protocol': protocol.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error updating protocol: {str(e)}'}), 500

@admin.route('/api/ampds/<code>', methods=['DELETE'])
@login_required
@permission_required_ajax(Permission.MANAGE_SETTINGS)
def delete_ampds_protocol(code):
    """Delete an AMPDS protocol."""
    protocol = AMPDSProtocol.query.filter_by(unique_id=code).first()
    if not protocol:
        return jsonify({'error': f'Protocol with code {code} not found'}), 404
    
    try:
        db.session.delete(protocol)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Protocol {code} deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error deleting protocol: {str(e)}'}), 500

# WebSocket event handlers
@socketio.on('request_admin_stats')
@login_required
@admin_required
def handle_admin_stats_request():
    """Handle WebSocket request for admin stats."""
    stats = {
        'total_users': User.query.count(),
        'active_units': Unit.query.filter(Unit.status != 'Out of Service').count(),
        'total_units': Unit.query.count(),
        'open_incidents': Incident.query.filter(Incident.status.in_(['active', 'pending'])).count(),
        'system_health': 'Good'  # Implement actual health checks
    }
    emit('admin_stats_update', stats)

@socketio.on('request_settings')
@login_required
@admin_required
def handle_settings_request():
    """Handle WebSocket request for system settings."""
    settings = SystemSetting.query.all()
    settings_dict = {setting.name: setting.value for setting in settings}
    emit('settings_update', settings_dict)

@socketio.on('update_settings')
@login_required
@admin_required
def handle_settings_update(data):
    """Handle WebSocket request to update settings."""
    try:
        for key, value in data.items():
            setting = SystemSetting.query.filter_by(name=key).first()
            if setting:
                setting.value = value
            else:
                setting = SystemSetting(name=key, value=value)
                db.session.add(setting)
        db.session.commit()
        emit('settings_update_success', {'message': 'Settings updated successfully'})
        # Broadcast settings update to all admin users
        emit('settings_update', data, broadcast=True, include_self=False)
    except Exception as e:
        db.session.rollback()
        emit('settings_update_error', {'error': str(e)})

@admin.route('/units', endpoint='units')
@login_required
@admin_required
@permission_required(Permission.VIEW_UNITS)
def manage_units():
    """Unit management page."""
    try:
        units = Unit.query.order_by(Unit.unit_number).all()
        unit_types = UnitType.query.all()
        return current_app.custom_render_template('admin/units.html', units=units, unit_types=unit_types)
    except Exception as e:
        current_app.logger.error(f"Error in unit management: {str(e)}")
        flash('An error occurred while loading the unit management page. Please try again.', 'error')
        return redirect(url_for('admin.index'))

@admin.route('/units/add', methods=['POST'])
@login_required
@admin_required
@permission_required(Permission.MANAGE_UNITS)
def add_unit():
    """Add a new unit."""
    try:
        unit_number = request.form.get('unit_number')
        unit_type = request.form.get('unit_type')
        station = request.form.get('station')
        
        if not unit_number or not unit_type:
            flash('Unit number and type are required.', 'error')
            return redirect(url_for('admin.units'))
            
        # Check if unit number already exists
        if Unit.query.filter_by(unit_number=unit_number).first():
            flash('A unit with this number already exists.', 'error')
            return redirect(url_for('admin.units'))
            
        unit = Unit(
            unit_number=unit_number,
            unit_type=unit_type,
            station=station,
            status='available'
        )
        db.session.add(unit)
        db.session.commit()
        
        flash(f'Unit {unit_number} added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding unit: {str(e)}")
        flash('An error occurred while adding the unit. Please try again.', 'error')
        
    return redirect(url_for('admin.units'))

@admin.route('/units/<int:unit_id>/edit', methods=['POST'])
@login_required
@admin_required
@permission_required(Permission.MANAGE_UNITS)
def edit_unit(unit_id):
    """Edit an existing unit."""
    try:
        unit = Unit.query.get_or_404(unit_id)
        
        unit_type = request.form.get('unit_type')
        station = request.form.get('station')
        status = request.form.get('status')
        
        if unit_type:
            unit.unit_type = unit_type
        if station:
            unit.station = station
        if status:
            unit.status = status
            
        db.session.commit()
        flash(f'Unit {unit.unit_number} updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating unit: {str(e)}")
        flash('An error occurred while updating the unit. Please try again.', 'error')
        
    return redirect(url_for('admin.units'))

@admin.route('/units/<int:unit_id>/delete', methods=['POST'])
@login_required
@admin_required
@permission_required(Permission.MANAGE_UNITS)
def delete_unit(unit_id):
    """Delete a unit."""
    try:
        unit = Unit.query.get_or_404(unit_id)
        
        # Check if unit is currently assigned to any incidents
        if unit.current_incident_id:
            flash('Cannot delete unit while it is assigned to an incident.', 'error')
            return redirect(url_for('admin.units'))
            
        db.session.delete(unit)
        db.session.commit()
        flash(f'Unit {unit.unit_number} deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting unit: {str(e)}")
        flash('An error occurred while deleting the unit. Please try again.', 'error')
        
    return redirect(url_for('admin.units'))

@admin.route('/maps')
@login_required
@admin_required
def maps():
    """Display map configuration page."""
    return current_app.custom_render_template('admin/maps.html')

@admin.route('/permissions')
@login_required
@admin_required
@permission_required(Permission.MANAGE_USERS)
def permissions():
    """Display permissions management page."""
    users = User.query.all()
    return current_app.custom_render_template('admin/permissions.html', users=users, title='User Permissions')

@admin.route('/api-keys')
@login_required
@admin_required
@permission_required(Permission.MANAGE_SETTINGS)
def api_keys():
    """API key management page."""
    keys = APIKey.query.filter_by(user_id=current_user.id).all()
    return current_app.custom_render_template('admin/api_keys.html', api_keys=keys, title='API Keys Management')

@admin.route('/api/keys/generate', methods=['POST'])
@login_required
@admin_required
@permission_required_ajax(Permission.MANAGE_SETTINGS)
def generate_api_key():
    """Generate a new API key."""
    try:
        data = request.get_json()
        description = data.get('description', 'API Key')
        
        if not description:
            return jsonify({'error': 'Description is required'}), 400
            
        # Generate a new key
        key = APIKey.generate_key()
        
        # Create and save the API key record
        api_key = APIKey(description=description, key=key, user_id=current_user.id)
        db.session.add(api_key)
        db.session.commit()
        
        current_app.logger.info(f"User {current_user.username} generated a new API key: {description}")
        
        # Return the key (only shown once)
        return jsonify({
            'success': True,
            'message': 'API key generated successfully',
            'key': key,
            'key_id': api_key.id
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating API key: {str(e)}")
        return jsonify({'error': f'Error generating API key: {str(e)}'}), 500

@admin.route('/api/keys/<int:key_id>/toggle', methods=['POST'])
@login_required
@admin_required
@permission_required_ajax(Permission.MANAGE_SETTINGS)
def toggle_api_key(key_id):
    """Toggle API key active status."""
    try:
        api_key = APIKey.query.get_or_404(key_id)
        
        # Verify ownership
        if api_key.user_id != current_user.id and not current_user.can(Permission.ADMINISTRATOR):
            return jsonify({'error': 'Not authorized to modify this API key'}), 403
            
        data = request.get_json()
        active = data.get('active', None)
        
        if active is None:
            # Toggle current value
            api_key.active = not api_key.active
        else:
            # Set to requested value
            api_key.active = bool(active)
            
        db.session.commit()
        
        status = 'activated' if api_key.active else 'deactivated'
        current_app.logger.info(f"User {current_user.username} {status} API key {key_id}")
        
        return jsonify({
            'success': True,
            'message': f'API key {status} successfully',
            'active': api_key.active
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error toggling API key: {str(e)}")
        return jsonify({'error': f'Error toggling API key: {str(e)}'}), 500

@admin.route('/api/keys/<int:key_id>', methods=['DELETE'])
@login_required
@admin_required
@permission_required_ajax(Permission.MANAGE_SETTINGS)
def delete_api_key(key_id):
    """Delete an API key."""
    try:
        api_key = APIKey.query.get_or_404(key_id)
        
        # Verify ownership
        if api_key.user_id != current_user.id and not current_user.can(Permission.ADMINISTRATOR):
            return jsonify({'error': 'Not authorized to delete this API key'}), 403
            
        description = api_key.description
        db.session.delete(api_key)
        db.session.commit()
        
        current_app.logger.info(f"User {current_user.username} deleted API key {key_id}: {description}")
        
        return jsonify({
            'success': True,
            'message': 'API key deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting API key: {str(e)}")
        return jsonify({'error': f'Error deleting API key: {str(e)}'}), 500

# WebSocket event handlers
@socketio.on('get_permissions')
@login_required
def handle_get_permissions(data):
    """Handle WebSocket request for user permissions."""
    if not current_user.can(Permission.ADMINISTRATOR):
        emit('error', {'message': 'Unauthorized access'})
        return
    
    try:
        user_id = data.get('user_id')
        if not user_id:
            emit('error', {'message': 'No user ID provided'})
            return
            
        user = User.query.get(user_id)
        if not user:
            emit('error', {'message': 'User not found'})
            return
            
        # Get user's current permissions
        role = user.role
        if not role:
            emit('error', {'message': 'User has no role assigned'})
            return
            
        # Convert permissions to list of permission names
        user_perms = []
        for name, value in Permission.__dict__.items():
            if name.isupper() and isinstance(value, int) and role.has_permission(value):
                user_perms.append(name)
                
        emit('permissions_data', {
            'user_id': user.id,
            'username': user.username,
            'role': role.name,
            'permissions': user_perms
        })
    except Exception as e:
        current_app.logger.error(f"Error getting permissions: {str(e)}")
        emit('error', {'message': f'Error: {str(e)}'})

@socketio.on('update_permissions')
@login_required
def handle_update_permissions(data):
    """Handle WebSocket request to update user permissions."""
    if not current_user.can(Permission.ADMINISTRATOR):
        emit('error', {'message': 'Unauthorized access'})
        return
    
    try:
        user_id = data.get('user_id')
        permissions = data.get('permissions', [])
        
        if not user_id:
            emit('error', {'message': 'No user ID provided'})
            return
            
        user = User.query.get(user_id)
        if not user:
            emit('error', {'message': 'User not found'})
            return
            
        # Update user's role permissions
        role = user.role
        if not role:
            emit('error', {'message': 'User has no role assigned'})
            return
            
        # Reset permissions
        role.reset_permissions()
        
        # Add each permission
        for perm_name in permissions:
            if hasattr(Permission, perm_name):
                perm_value = getattr(Permission, perm_name)
                if isinstance(perm_value, int):
                    role.add_permission(perm_value)
        
        db.session.commit()
        
        # Log the change
        current_app.logger.info(f"User {current_user.username} updated permissions for {user.username}")
        
        # Send success response
        emit('permissions_updated', {
            'user_id': user.id,
            'message': f'Permissions updated for {user.username}'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating permissions: {str(e)}")
        emit('error', {'message': f'Error: {str(e)}'})

@admin.route('/ampds')
@login_required
@role_required('ADMIN')
def ampds_management():
    """Display AMPDS management page."""
    ampds_protocols = AMPDSProtocol.query.all()
    return current_app.custom_render_template('admin/ampds.html', ampds=ampds_protocols)

@admin.route('/export/ampds')
@login_required
@role_required('ADMIN')
def export_ampds():
    """Export AMPDS protocols as CSV."""
    try:
        # Query all AMPDS protocols ordered by category and card number
        protocols = AMPDSProtocol.query.order_by(AMPDSProtocol.category, AMPDSProtocol.card_number).all()
        
        # Create CSV in memory
        output = io.StringIO()
        csv_writer = csv.writer(output)
        
        # Write header
        header = ['Unique ID', 'Category', 'Card Number', 'Priority', 'Subcategory', 'Dispatch Advice', 'PreArrival PDF']
        csv_writer.writerow(header)
        
        # Write data rows
        for protocol in protocols:
            row = [
                protocol.unique_id,
                protocol.category,
                protocol.card_number,
                protocol.priority,
                protocol.subcategory,
                protocol.dispatch_advice,
                protocol.prearrival_pdf
            ]
            csv_writer.writerow(row)
        
        # Prepare response
        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=ampds_protocols_{timestamp}.csv"}
        )
        
    except Exception as e:
        current_app.logger.error(f"Error exporting AMPDS protocols: {str(e)}")
        flash(f"Error exporting AMPDS protocols: {str(e)}", "danger")
        return redirect(url_for('admin.ampds_management'))

@admin.route('/api/dashboard/charts')
@login_required
@permission_required(Permission.VIEW_REPORTS)
def dashboard_charts_api():
    """API endpoint to get chart data for admin dashboard."""
    try:
        # Get last 7 days of data
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        
        # Get incident data by day
        incidents_by_day = db.session.query(
            func.date(Incident.created_at).label('date'),
            func.count(Incident.id).label('count')
        ).filter(
            Incident.created_at >= start_date,
            Incident.created_at <= end_date
        ).group_by(
            func.date(Incident.created_at)
        ).all()
        
        # Get unit status data
        unit_statuses = db.session.query(
            Unit.status,
            func.count(Unit.id).label('count')
        ).group_by(Unit.status).all()
        
        # Get incident priority data
        incident_priorities = db.session.query(
            Incident.priority,
            func.count(Incident.id).label('count')
        ).group_by(Incident.priority).all()
        
        # Format data for charts
        incident_chart_data = {
            'labels': [i.date.strftime('%Y-%m-%d') for i in incidents_by_day],
            'datasets': [{
                'label': 'Incidents',
                'data': [i.count for i in incidents_by_day],
                'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                'borderColor': 'rgba(75, 192, 192, 1)',
                'borderWidth': 1
            }]
        }
        
        unit_status_data = {
            'labels': [u.status for u in unit_statuses],
            'datasets': [{
                'label': 'Units by Status',
                'data': [u.count for u in unit_statuses],
                'backgroundColor': [
                    'rgba(255, 99, 132, 0.5)',
                    'rgba(54, 162, 235, 0.5)',
                    'rgba(255, 206, 86, 0.5)',
                    'rgba(75, 192, 192, 0.5)',
                ]
            }]
        }
        
        incident_priority_data = {
            'labels': [i.priority for i in incident_priorities],
            'datasets': [{
                'label': 'Incidents by Priority',
                'data': [i.count for i in incident_priorities],
                'backgroundColor': [
                    'rgba(255, 99, 132, 0.5)',
                    'rgba(54, 162, 235, 0.5)',
                    'rgba(255, 206, 86, 0.5)',
                ]
            }]
        }
        
        return jsonify({
            'incident_chart': incident_chart_data,
            'unit_status_chart': unit_status_data,
            'incident_priority_chart': incident_priority_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting dashboard chart data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin.route('/api/permissions', methods=['GET'])
@login_required
@permission_required_ajax(Permission.MANAGE_USERS)
def get_all_permissions():
    """Get all available permissions."""
    try:
        permissions = [
            {
                'id': permission.value,
                'name': permission.name,
                'description': permission.description
            }
            for permission in Permission
        ]
        
        return jsonify({
            'success': True,
            'permissions': permissions
        })
    except Exception as e:
        current_app.logger.error(f"Error getting permissions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error getting permissions: {str(e)}"
        }), 500

@admin.route('/api/permissions/user/<int:user_id>', methods=['GET'])
@login_required
@permission_required_ajax(Permission.MANAGE_USERS)
def get_user_permissions_api(user_id):
    """Get a user's permissions."""
    try:
        user = User.query.get_or_404(user_id)
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'permissions': user.get_permissions()
        })
    except Exception as e:
        current_app.logger.error(f"Error getting user permissions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error getting user permissions: {str(e)}"
        }), 500

@admin.route('/api/permissions/user/<int:user_id>', methods=['PUT'])
@login_required
@permission_required_ajax(Permission.MANAGE_USERS)
def update_user_permissions_api(user_id):
    """Update a user's permissions."""
    try:
        data = request.get_json()
        
        is_valid, error_message = validate_request_data(data, ['permissions'])
        if not is_valid:
            return jsonify({
                'success': False,
                'message': error_message
            }), 400
            
        user = User.query.get_or_404(user_id)
        
        # Store the permission changes for logging
        old_permissions = user.get_permissions_dict()
        
        # Update permissions
        if 'permissions' in data:
            for perm_id, value in data['permissions'].items():
                try:
                    perm_id = int(perm_id)
                    user.set_permission(perm_id, value)
                except ValueError:
                    continue
        
        # Log changes
        new_permissions = user.get_permissions_dict()
        changes = []
        
        for perm_name, had_perm in old_permissions.items():
            now_has_perm = new_permissions.get(perm_name, False)
            if had_perm != now_has_perm:
                changes.append(f"{perm_name}: {'Granted' if now_has_perm else 'Revoked'}")
        
        if changes:
            current_app.logger.info(f"User permissions updated for {user.username} (ID: {user.id}) by {current_user.username}: {', '.join(changes)}")
            
        db.session.commit()
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'permissions': user.get_permissions()
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating user permissions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error updating user permissions: {str(e)}"
        }), 500

# Role API endpoints
@admin.route('/api/admin/roles', methods=['GET'])
@login_required
@permission_required_ajax(Permission.MANAGE_ROLES)
def get_roles():
    """Get all role templates."""
    try:
        roles = Role.query.all()
        role_templates = {}
        
        # Default role templates based on permission reference
        default_templates = {
            'Administrator': {
                'description': 'Full administrative access',
                'permissions': ['ADMIN']
            },
            'Dispatcher': {
                'description': 'Manage incidents and units',
                'permissions': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                              'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                              'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'SEND_EMAILS']
            },
            'Supervisor': {
                'description': 'Extended dispatcher capabilities',
                'permissions': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                              'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'DELETE_INCIDENT', 'EXPORT_INCIDENTS', 
                              'IMPORT_INCIDENTS', 'MANAGE_UNITS', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                              'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'MANAGE_NOTIFICATIONS', 'SEND_EMAILS']
            },
            'ReadOnly': {
                'description': 'View-only access',
                'permissions': ['VIEW_DASHBOARD', 'VIEW_INCIDENTS', 'VIEW_UNITS', 'VIEW_UNIT_LOCATIONS']
            }
        }
        
        # Add custom roles from database
        for role in roles:
            role_templates[role.name] = {
                'description': role.description,
                'permissions': role.get_permissions()
            }
        
        # Add default templates if not already in database
        for name, data in default_templates.items():
            if name not in role_templates:
                role_templates[name] = data
        
        return jsonify(role_templates)
    except Exception as e:
        current_app.logger.error(f"Error getting roles: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin.route('/api/admin/roles', methods=['POST'])
@login_required
@permission_required_ajax(Permission.MANAGE_ROLES)
def create_role():
    """Create a new role template."""
    try:
        data = request.get_json()
        
        is_valid, error_message = validate_request_data(data, ['name', 'description', 'permissions'])
        if not is_valid:
            return jsonify({'error': error_message}), 400
        
        # Check if role already exists
        existing_role = Role.query.filter_by(name=data['name']).first()
        if existing_role:
            return jsonify({'error': f"Role '{data['name']}' already exists"}), 400
        
        # Create new role
        new_role = Role(
            name=data['name'],
            description=data['description'],
            default=False
        )
        
        # Set permissions
        permission_value = 0
        for perm_name in data['permissions']:
            # Find permission by name
            for attr_name in dir(Permission):
                if attr_name.isupper() and attr_name == perm_name:
                    perm_value = getattr(Permission, attr_name)
                    permission_value |= perm_value
                    break
        
        new_role.permissions = permission_value
        
        db.session.add(new_role)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Role '{data['name']}' created successfully",
            'role': {
                'id': new_role.id,
                'name': new_role.name,
                'description': new_role.description,
                'permissions': new_role.get_permissions()
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating role: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin.route('/api/admin/roles/<string:role_name>', methods=['GET'])
@login_required
@permission_required_ajax(Permission.MANAGE_ROLES)
def get_role(role_name):
    """Get a specific role template by name."""
    try:
        # Try to find role in database
        role = Role.query.filter_by(name=role_name).first()
        
        if role:
            # Return database role
            return jsonify({
                'name': role.name,
                'description': role.description,
                'permissions': role.get_permissions()
            })
        else:
            # Check if it's a default template
            default_templates = {
                'Administrator': {
                    'description': 'Full administrative access',
                    'permissions': ['ADMIN']
                },
                'Dispatcher': {
                    'description': 'Manage incidents and units',
                    'permissions': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                                  'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                                  'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'SEND_EMAILS']
                },
                'Supervisor': {
                    'description': 'Extended dispatcher capabilities',
                    'permissions': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                                  'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'DELETE_INCIDENT', 'EXPORT_INCIDENTS', 
                                  'IMPORT_INCIDENTS', 'MANAGE_UNITS', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                                  'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'MANAGE_NOTIFICATIONS', 'SEND_EMAILS']
                },
                'ReadOnly': {
                    'description': 'View-only access',
                    'permissions': ['VIEW_DASHBOARD', 'VIEW_INCIDENTS', 'VIEW_UNITS', 'VIEW_UNIT_LOCATIONS']
                }
            }
            
            if role_name in default_templates:
                template = default_templates[role_name]
                return jsonify({
                    'name': role_name,
                    'description': template['description'],
                    'permissions': template['permissions']
                })
            
            return jsonify({'error': f"Role '{role_name}' not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Error getting role: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin.route('/api/admin/roles/<string:role_name>', methods=['PUT'])
@login_required
@permission_required_ajax(Permission.MANAGE_ROLES)
def update_role(role_name):
    """Update a role template."""
    try:
        data = request.get_json()
        
        is_valid, error_message = validate_request_data(data, ['description', 'permissions'])
        if not is_valid:
            return jsonify({'error': error_message}), 400
        
        # Find role
        role = Role.query.filter_by(name=role_name).first()
        
        # If role not in database but is a default template, create it first
        if not role and role_name in ['Administrator', 'Dispatcher', 'Supervisor', 'ReadOnly']:
            default_templates = {
                'Administrator': {
                    'description': 'Full administrative access',
                    'permissions': ['ADMIN']
                },
                'Dispatcher': {
                    'description': 'Manage incidents and units',
                    'permissions': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                                  'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                                  'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'SEND_EMAILS']
                },
                'Supervisor': {
                    'description': 'Extended dispatcher capabilities',
                    'permissions': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                                  'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'DELETE_INCIDENT', 'EXPORT_INCIDENTS', 
                                  'IMPORT_INCIDENTS', 'MANAGE_UNITS', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                                  'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'MANAGE_NOTIFICATIONS', 'SEND_EMAILS']
                },
                'ReadOnly': {
                    'description': 'View-only access',
                    'permissions': ['VIEW_DASHBOARD', 'VIEW_INCIDENTS', 'VIEW_UNITS', 'VIEW_UNIT_LOCATIONS']
                }
            }
            
            # Create role in database with default permissions
            role = Role(
                name=role_name,
                description=default_templates[role_name]['description'],
                permissions=getattr(Permission, 'ADMIN') if role_name == 'Administrator' else 0
            )
            db.session.add(role)
        
        if not role:
            return jsonify({'error': f"Role '{role_name}' not found"}), 404
        
        # Update role
        role.description = data['description']
        
        # Update permissions
        permission_value = 0
        for perm_name in data['permissions']:
            # Find permission by name
            for attr_name in dir(Permission):
                if attr_name.isupper() and attr_name == perm_name:
                    perm_value = getattr(Permission, attr_name)
                    permission_value |= perm_value
                    break
        
        role.permissions = permission_value
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Role '{role_name}' updated successfully",
            'role': {
                'id': role.id,
                'name': role.name,
                'description': role.description,
                'permissions': role.get_permissions()
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating role: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin.route('/api/admin/roles/<string:role_name>', methods=['DELETE'])
@login_required
@permission_required_ajax(Permission.MANAGE_ROLES)
def delete_role(role_name):
    """Delete a role template."""
    try:
        # Cannot delete default roles
        if role_name in ['Administrator', 'Dispatcher', 'Supervisor', 'ReadOnly']:
            return jsonify({'error': 'Cannot delete default role templates'}), 400
        
        # Find role
        role = Role.query.filter_by(name=role_name).first()
        
        if not role:
            return jsonify({'error': f"Role '{role_name}' not found"}), 404
        
        # Check if any users have this role
        users_with_role = User.query.filter_by(role_id=role.id).all()
        if users_with_role:
            user_count = len(users_with_role)
            return jsonify({
                'error': f"Cannot delete role '{role_name}' because it is assigned to {user_count} user(s)"
            }), 400
        
        # Delete role
        db.session.delete(role)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Role '{role_name}' deleted successfully"
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting role: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin.route('/api/admin/roles/permissions', methods=['GET'])
@login_required
@permission_required_ajax(Permission.MANAGE_ROLES)
def get_role_permissions():
    """Get permissions for all roles."""
    try:
        roles = Role.query.all()
        
        role_permissions = {}
        for role in roles:
            role_permissions[role.name] = role.get_permissions()
        
        # Add default templates
        default_templates = {
            'Administrator': ['ADMIN'],
            'Dispatcher': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                         'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                         'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'SEND_EMAILS'],
            'Supervisor': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                         'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'DELETE_INCIDENT', 'EXPORT_INCIDENTS', 
                         'IMPORT_INCIDENTS', 'MANAGE_UNITS', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                         'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'MANAGE_NOTIFICATIONS', 'SEND_EMAILS'],
            'ReadOnly': ['VIEW_DASHBOARD', 'VIEW_INCIDENTS', 'VIEW_UNITS', 'VIEW_UNIT_LOCATIONS']
        }
        
        # Add default templates if not already in database
        for name, permissions in default_templates.items():
            if name not in role_permissions:
                role_permissions[name] = permissions
        
        return jsonify(role_permissions)
    except Exception as e:
        current_app.logger.error(f"Error getting role permissions: {str(e)}")
        return jsonify({'error': str(e)}), 500

# User API endpoints
@admin.route('/api/admin/users', methods=['GET'])
@login_required
@permission_required_ajax(Permission.MANAGE_USERS)
def get_users():
    """Get all users."""
    try:
        users = User.query.all()
        
        user_list = []
        for user in users:
            user_list.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'active': user.active,
                'role': user.role.name if user.role else None,
                'permissions': user.get_permissions()
            })
        
        return jsonify(user_list)
    except Exception as e:
        current_app.logger.error(f"Error getting users: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin.route('/api/admin/users/<string:username>', methods=['GET'])
@login_required
@permission_required_ajax(Permission.MANAGE_USERS)
def get_user(username):
    """Get a specific user by username."""
    try:
        user = User.query.filter_by(username=username).first()
        
        if not user:
            return jsonify({'error': f"User '{username}' not found"}), 404
        
        return jsonify({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'active': user.active,
            'role': user.role.name if user.role else None,
            'permissions': user.get_permissions()
        })
    except Exception as e:
        current_app.logger.error(f"Error getting user: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin.route('/api/admin/users/<string:username>', methods=['PUT'])
@login_required
@permission_required_ajax(Permission.MANAGE_USERS)
def update_user(username):
    """Update a user."""
    try:
        data = request.get_json()
        
        # Find user
        user = User.query.filter_by(username=username).first()
        
        if not user:
            return jsonify({'error': f"User '{username}' not found"}), 404
        
        # Update user fields
        if 'email' in data:
            user.email = data['email']
        
        if 'active' in data:
            user.active = bool(data['active'])
        
        # Update permissions if provided
        if 'permissions' in data:
            # Calculate permission value
            permission_value = 0
            for perm_name in data['permissions']:
                # Find permission by name
                for attr_name in dir(Permission):
                    if attr_name.isupper() and attr_name == perm_name:
                        perm_value = getattr(Permission, attr_name)
                        permission_value |= perm_value
                        break
            
            # If they have ADMIN permission, assign the Administrator role
            if 'ADMIN' in data['permissions']:
                admin_role = Role.query.filter_by(name='Administrator').first()
                if not admin_role:
                    # Create Administrator role if it doesn't exist
                    admin_role = Role(name='Administrator', description='Full administrative access')
                    admin_role.permissions = getattr(Permission, 'ADMIN')
                    db.session.add(admin_role)
                    db.session.flush()
                
                user.role_id = admin_role.id
            else:
                # Find or create a role that matches these exact permissions
                matching_role = Role.query.filter_by(permissions=permission_value).first()
                
                if not matching_role:
                    # If no existing role matches, see if we can find a default template that matches
                    default_templates = {
                        'Dispatcher': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                                    'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                                    'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'SEND_EMAILS'],
                        'Supervisor': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                                    'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'DELETE_INCIDENT', 'EXPORT_INCIDENTS', 
                                    'IMPORT_INCIDENTS', 'MANAGE_UNITS', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                                    'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'MANAGE_NOTIFICATIONS', 'SEND_EMAILS'],
                        'ReadOnly': ['VIEW_DASHBOARD', 'VIEW_INCIDENTS', 'VIEW_UNITS', 'VIEW_UNIT_LOCATIONS']
                    }
                    
                    # Try to find a default template that matches
                    template_match = None
                    for template_name, template_perms in default_templates.items():
                        # Convert template permissions to value
                        template_value = 0
                        for perm_name in template_perms:
                            for attr_name in dir(Permission):
                                if attr_name.isupper() and attr_name == perm_name:
                                    template_value |= getattr(Permission, attr_name)
                        
                        if template_value == permission_value:
                            template_match = template_name
                            break
                    
                    if template_match:
                        # Find or create the template role
                        template_role = Role.query.filter_by(name=template_match).first()
                        if not template_role:
                            template_role = Role(
                                name=template_match,
                                description=f"{template_match} role template",
                                permissions=permission_value
                            )
                            db.session.add(template_role)
                            db.session.flush()
                        
                        user.role_id = template_role.id
                    else:
                        # Create a custom role
                        custom_role = Role(
                            name=f"Custom_{username}",
                            description=f"Custom role for {username}",
                            permissions=permission_value
                        )
                        db.session.add(custom_role)
                        db.session.flush()
                        
                        user.role_id = custom_role.id
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"User '{username}' updated successfully",
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'active': user.active,
                'role': user.role.name if user.role else None,
                'permissions': user.get_permissions()
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating user: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Unit API Endpoints for Admin
@admin.route('/api/units', methods=['GET'])
@login_required
@permission_required_ajax(Permission.VIEW_UNITS)
def get_units():
    """Get all units for admin management."""
    try:
        units = Unit.query.all()
        return jsonify({
            'success': True,
            'units': [unit.to_dict() for unit in units]
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving units: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Failed to retrieve units: {str(e)}"
        }), 500

@admin.route('/api/units/<int:unit_id>', methods=['GET'])
@login_required
@permission_required_ajax(Permission.VIEW_UNITS)
def get_unit(unit_id):
    """Get a specific unit by ID."""
    try:
        unit = Unit.query.get_or_404(unit_id)
        return jsonify({
            'success': True,
            'id': unit.id,
            'unit_id': unit.unit_number,
            'type': unit.type,
            'location': unit.station or '',
            'capacity': unit.capacity,
            'active': unit.status != 'Out of Service'
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving unit {unit_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Failed to retrieve unit: {str(e)}"
        }), 500

@admin.route('/api/units', methods=['POST'])
@login_required
@permission_required_ajax(Permission.MANAGE_UNITS)
def create_unit():
    """Create a new unit."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['unit_id', 'type', 'location']
        is_valid, error_message = validate_request_data(data, required_fields)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': error_message
            }), 400
        
        # Check if unit with same ID already exists
        existing_unit = Unit.query.filter_by(unit_number=data['unit_id']).first()
        if existing_unit:
            return jsonify({
                'success': False,
                'message': f"Unit with ID {data['unit_id']} already exists"
            }), 400
        
        # Create new unit
        unit = Unit(
            unit_number=data['unit_id'],
            type=data['type'],
            station=data['location'],
            capacity=data.get('capacity'),
            status='Available' if data.get('active', True) else 'Out of Service'
        )
        
        db.session.add(unit)
        db.session.commit()
        
        current_app.logger.info(f"Created new unit: {data['unit_id']}")
        
        return jsonify({
            'success': True,
            'message': 'Unit created successfully',
            'unit_id': unit.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating unit: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Failed to create unit: {str(e)}"
        }), 500

@admin.route('/api/units/<int:unit_id>', methods=['PUT'])
@login_required
@permission_required_ajax(Permission.MANAGE_UNITS)
def update_unit(unit_id):
    """Update an existing unit."""
    try:
        unit = Unit.query.get_or_404(unit_id)
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['unit_id', 'type', 'location']
        is_valid, error_message = validate_request_data(data, required_fields)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': error_message
            }), 400
        
        # Check if unit_id is being changed and if it conflicts with an existing unit
        if data['unit_id'] != unit.unit_number:
            existing_unit = Unit.query.filter_by(unit_number=data['unit_id']).first()
            if existing_unit and existing_unit.id != unit_id:
                return jsonify({
                    'success': False,
                    'message': f"Unit with ID {data['unit_id']} already exists"
                }), 400
        
        # Update unit fields
        unit.unit_number = data['unit_id']
        unit.type = data['type']
        unit.station = data['location']
        unit.capacity = data.get('capacity', unit.capacity)
        unit.status = 'Available' if data.get('active', True) else 'Out of Service'
        
        db.session.commit()
        
        current_app.logger.info(f"Updated unit: {unit.unit_number}")
        
        return jsonify({
            'success': True,
            'message': 'Unit updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating unit {unit_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Failed to update unit: {str(e)}"
        }), 500

@admin.route('/api/units/<int:unit_id>', methods=['DELETE'])
@login_required
@permission_required_ajax(Permission.MANAGE_UNITS)
def api_delete_unit(unit_id):
    """Delete a unit."""
    try:
        unit = Unit.query.get_or_404(unit_id)
        
        # Check if unit is currently assigned to an incident
        if unit.current_incident_id:
            return jsonify({
                'success': False,
                'message': 'Cannot delete unit that is currently assigned to an incident'
            }), 400
        
        unit_number = unit.unit_number
        db.session.delete(unit)
        db.session.commit()
        
        current_app.logger.info(f"Deleted unit: {unit_number}")
        
        return jsonify({
            'success': True,
            'message': 'Unit deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting unit {unit_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Failed to delete unit: {str(e)}"
        }), 500

@admin.route('/api/units/types', methods=['GET'])
@login_required
@permission_required_ajax(Permission.VIEW_UNITS)
def get_unit_types():
    """Get all unit types."""
    try:
        unit_types = UnitType.query.all()
        return jsonify({
            'success': True,
            'types': [type.to_dict() for type in unit_types]
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving unit types: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Failed to retrieve unit types: {str(e)}"
        }), 500

@admin.route('/api/units/types', methods=['POST'])
@login_required
@permission_required_ajax(Permission.MANAGE_UNITS)
def create_unit_type():
    """Create a new unit type."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'description']
        is_valid, error_message = validate_request_data(data, required_fields)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': error_message
            }), 400
        
        # Check if type with same name already exists
        existing_type = UnitType.query.filter_by(name=data['name']).first()
        if existing_type:
            return jsonify({
                'success': False,
                'message': f"Unit type '{data['name']}' already exists"
            }), 400
        
        # Create new unit type
        unit_type = UnitType(
            name=data['name'],
            description=data['description'],
            icon=data.get('icon', 'ambulance'),
            color=data.get('color', '#007bff')
        )
        
        db.session.add(unit_type)
        db.session.commit()
        
        current_app.logger.info(f"Created new unit type: {data['name']}")
        
        return jsonify({
            'success': True,
            'message': 'Unit type created successfully',
            'type_id': unit_type.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating unit type: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Failed to create unit type: {str(e)}"
        }), 500

@admin.route('/api/units/types/<int:type_id>', methods=['GET'])
@login_required
@permission_required_ajax(Permission.VIEW_UNITS)
def get_unit_type(type_id):
    """Get a specific unit type by ID."""
    try:
        unit_type = UnitType.query.get_or_404(type_id)
        return jsonify({
            'success': True,
            'id': unit_type.id,
            'name': unit_type.name,
            'description': unit_type.description,
            'icon': unit_type.icon,
            'color': unit_type.color
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving unit type {type_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Failed to retrieve unit type: {str(e)}"
        }), 500

@admin.route('/api/units/types/<int:type_id>', methods=['PUT'])
@login_required
@permission_required_ajax(Permission.MANAGE_UNITS)
def update_unit_type(type_id):
    """Update an existing unit type."""
    try:
        unit_type = UnitType.query.get_or_404(type_id)
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'description']
        is_valid, error_message = validate_request_data(data, required_fields)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': error_message
            }), 400
        
        # Check if name is being changed and if it conflicts with an existing type
        if data['name'] != unit_type.name:
            existing_type = UnitType.query.filter_by(name=data['name']).first()
            if existing_type and existing_type.id != type_id:
                return jsonify({
                    'success': False,
                    'message': f"Unit type '{data['name']}' already exists"
                }), 400
        
        # Update unit type fields
        unit_type.name = data['name']
        unit_type.description = data['description']
        unit_type.icon = data.get('icon', unit_type.icon)
        unit_type.color = data.get('color', unit_type.color)
        
        db.session.commit()
        
        current_app.logger.info(f"Updated unit type: {unit_type.name}")
        
        return jsonify({
            'success': True,
            'message': 'Unit type updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating unit type {type_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Failed to update unit type: {str(e)}"
        }), 500

@admin.route('/api/units/types/<int:type_id>', methods=['DELETE'])
@login_required
@permission_required_ajax(Permission.MANAGE_UNITS)
def delete_unit_type(type_id):
    """Delete a unit type."""
    try:
        unit_type = UnitType.query.get_or_404(type_id)
        
        # Check if there are units using this type
        units_with_type = Unit.query.filter_by(type=unit_type.name).first()
        if units_with_type:
            return jsonify({
                'success': False,
                'message': 'Cannot delete unit type that is being used by units'
            }), 400
        
        type_name = unit_type.name
        db.session.delete(unit_type)
        db.session.commit()
        
        current_app.logger.info(f"Deleted unit type: {type_name}")
        
        return jsonify({
            'success': True,
            'message': 'Unit type deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting unit type {type_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Failed to delete unit type: {str(e)}"
        }), 500

# Unit Import/Export endpoints
@admin.route('/import/units', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_UNITS)
def import_units():
    """Import units from a CSV file."""
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('admin.manage_units'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('admin.manage_units'))
    
    if not file.filename.endswith('.csv'):
        flash('File must be a CSV', 'danger')
        return redirect(url_for('admin.manage_units'))
    
    try:
        # Process CSV file
        import csv
        from io import StringIO
        
        # Read the file
        csv_data = file.read().decode('utf-8')
        csv_file = StringIO(csv_data)
        reader = csv.DictReader(csv_file)
        
        units_added = 0
        errors = []
        
        for row in reader:
            try:
                # Check required fields
                if not row.get('unit_id') or not row.get('type'):
                    errors.append(f"Row missing required fields: {row}")
                    continue
                
                # Check if unit already exists
                existing_unit = Unit.query.filter_by(unit_number=row['unit_id']).first()
                if existing_unit:
                    errors.append(f"Unit with ID {row['unit_id']} already exists")
                    continue
                
                # Create new unit
                unit = Unit(
                    unit_number=row['unit_id'],
                    type=row['type'],
                    station=row.get('location', ''),
                    capacity=row.get('capacity', 0),
                    status='Available' if row.get('active', 'true').lower() == 'true' else 'Out of Service'
                )
                
                db.session.add(unit)
                units_added += 1
                
            except Exception as e:
                errors.append(f"Error processing row {row}: {str(e)}")
        
        db.session.commit()
        
        if errors:
            flash(f"Imported {units_added} units with {len(errors)} errors. See logs for details.", 'warning')
            for error in errors:
                current_app.logger.error(f"Import error: {error}")
        else:
            flash(f"Successfully imported {units_added} units", 'success')
        
        return redirect(url_for('admin.manage_units'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error importing units: {str(e)}")
        flash(f"Error importing units: {str(e)}", 'danger')
        return redirect(url_for('admin.manage_units'))

@admin.route('/export/units')
@login_required
@permission_required(Permission.VIEW_UNITS)
def export_units():
    """Export units to a CSV file."""
    try:
        import csv
        from io import StringIO
        
        # Create CSV file
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['unit_id', 'type', 'location', 'capacity', 'active'])
        
        # Get all units
        units = Unit.query.all()
        
        # Write unit data
        for unit in units:
            writer.writerow([
                unit.unit_number,
                unit.type,
                unit.station or '',
                unit.capacity or '',
                'true' if unit.status != 'Out of Service' else 'false'
            ])
        
        # Create response
        output.seek(0)
        return current_app.response_class(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=units.csv'}
        )
        
    except Exception as e:
        current_app.logger.error(f"Error exporting units: {str(e)}")
        flash(f"Error exporting units: {str(e)}", 'danger')
        return redirect(url_for('admin.manage_units'))

@admin.route('/api/admin/users', methods=['POST'])
@login_required
@permission_required_ajax(Permission.MANAGE_USERS)
def create_user():
    """Create a new user."""
    try:
        data = request.get_json()
        
        # Validate required fields
        valid, message = validate_request_data(data, ['username', 'email', 'password'])
        if not valid:
            return jsonify({'error': message}), 400
        
        # Check if username already exists
        existing_user = User.query.filter_by(username=data['username']).first()
        if existing_user:
            return jsonify({'error': f"Username '{data['username']}' is already taken"}), 400
        
        # Check if email already exists
        existing_email = User.query.filter_by(email=data['email']).first()
        if existing_email:
            return jsonify({'error': f"Email '{data['email']}' is already registered"}), 400
        
        # Create new user
        user = User(
            username=data['username'],
            email=data['email'],
            active=data.get('active', True)
        )
        user.set_password(data['password'])
        
        # Set permissions if provided
        if 'permissions' in data:
            # Calculate permission value
            permission_value = 0
            for perm_name in data['permissions']:
                # Find permission by name
                for attr_name in dir(Permission):
                    if attr_name.isupper() and attr_name == perm_name:
                        perm_value = getattr(Permission, attr_name)
                        permission_value |= perm_value
                        break
            
            # If they have ADMIN permission, assign the Administrator role
            if 'ADMIN' in data['permissions']:
                admin_role = Role.query.filter_by(name='Administrator').first()
                if not admin_role:
                    # Create Administrator role if it doesn't exist
                    admin_role = Role(name='Administrator', description='Full administrative access')
                    admin_role.permissions = getattr(Permission, 'ADMIN')
                    db.session.add(admin_role)
                    db.session.flush()
                
                user.role_id = admin_role.id
            else:
                # Find or create a role that matches these exact permissions
                matching_role = Role.query.filter_by(permissions=permission_value).first()
                
                if not matching_role:
                    # Try to match with predefined role templates
                    default_templates = {
                        'Dispatcher': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                                      'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                                      'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'SEND_EMAILS'],
                        'Supervisor': ['VIEW_DASHBOARD', 'ACCESS_API', 'CREATE_INCIDENT', 'EDIT_INCIDENT', 
                                      'VIEW_INCIDENTS', 'CLOSE_INCIDENT', 'DELETE_INCIDENT', 'EXPORT_INCIDENTS', 
                                      'IMPORT_INCIDENTS', 'MANAGE_UNITS', 'ASSIGN_UNITS', 'VIEW_UNITS', 
                                      'TRACK_UNITS', 'VIEW_UNIT_LOCATIONS', 'MANAGE_NOTIFICATIONS', 'SEND_EMAILS'],
                        'ReadOnly': ['VIEW_DASHBOARD', 'VIEW_INCIDENTS', 'VIEW_UNITS', 'VIEW_UNIT_LOCATIONS']
                    }
                    
                    # Try to find a default template that matches
                    template_match = None
                    for template_name, template_perms in default_templates.items():
                        # Convert template permissions to value
                        template_value = 0
                        for perm_name in template_perms:
                            for attr_name in dir(Permission):
                                if attr_name.isupper() and attr_name == perm_name:
                                    template_value |= getattr(Permission, attr_name)
                        
                        if template_value == permission_value:
                            template_match = template_name
                            break
                    
                    if template_match:
                        # Find or create the template role
                        template_role = Role.query.filter_by(name=template_match).first()
                        if not template_role:
                            template_role = Role(
                                name=template_match,
                                description=f"{template_match} role template",
                                permissions=permission_value
                            )
                            db.session.add(template_role)
                            db.session.flush()
                        
                        user.role_id = template_role.id
                    else:
                        # Create a custom role
                        custom_role = Role(
                            name=f"Custom_{data['username']}",
                            description=f"Custom role for {data['username']}",
                            permissions=permission_value
                        )
                        db.session.add(custom_role)
                        db.session.flush()
                        
                        user.role_id = custom_role.id
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"User '{data['username']}' created successfully",
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'active': user.active,
                'role': user.role.name if user.role else None,
                'permissions': user.get_permissions()
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin.route('/api/admin/users/import', methods=['POST'])
@login_required
@permission_required_ajax(Permission.MANAGE_USERS)
def import_users():
    """Import users from a CSV file."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'error': 'File must be a CSV file'}), 400
        
        # Read the CSV file
        csv_data = file.read().decode('utf-8').splitlines()
        csv_reader = csv.DictReader(csv_data)
        
        if not csv_reader.fieldnames:
            return jsonify({'error': 'CSV file is empty or invalid'}), 400
        
        required_fields = ['username', 'email', 'password']
        for field in required_fields:
            if field not in csv_reader.fieldnames:
                return jsonify({'error': f"Required field '{field}' is missing in CSV file"}), 400
        
        # Process each row
        created_users = []
        errors = []
        for row_num, row in enumerate(csv_reader, start=2):  # Start from 2 to account for header row
            try:
                # Check if user already exists
                existing_user = User.query.filter_by(username=row['username']).first()
                if existing_user:
                    errors.append(f"Row {row_num}: Username '{row['username']}' already exists")
                    continue
                
                # Check if email already exists
                existing_email = User.query.filter_by(email=row['email']).first()
                if existing_email:
                    errors.append(f"Row {row_num}: Email '{row['email']}' already registered")
                    continue
                
                # Create new user
                user = User(
                    username=row['username'],
                    email=row['email'],
                    active=row.get('active', 'true').lower() == 'true'
                )
                user.set_password(row['password'])
                
                # Set role if provided
                if 'role' in row and row['role']:
                    role = Role.query.filter_by(name=row['role']).first()
                    if role:
                        user.role_id = role.id
                    else:
                        errors.append(f"Row {row_num}: Role '{row['role']}' not found")
                
                db.session.add(user)
                created_users.append(user.username)
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Imported {len(created_users)} users",
            'created_users': created_users,
            'errors': errors
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error importing users: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin.route('/api/admin/users/export', methods=['GET'])
@login_required
@permission_required_ajax(Permission.MANAGE_USERS)
def export_users():
    """Export users to CSV format."""
    try:
        include_passwords = request.args.get('include_passwords', 'false').lower() == 'true'
        
        # Get all users
        users = User.query.all()
        
        if not users:
            return jsonify({'error': 'No users found'}), 404
        
        # Prepare CSV data
        output = StringIO()
        fieldnames = ['username', 'email', 'active', 'role']
        if include_passwords:
            fieldnames.append('password')
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for user in users:
            user_data = {
                'username': user.username,
                'email': user.email,
                'active': str(user.active).lower(),
                'role': user.role.name if user.role else ""
            }
            
            if include_passwords:
                # This is a placeholder. In a real system, we wouldn't export actual passwords
                user_data['password'] = "********"
            
            writer.writerow(user_data)
        
        # Create response
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=users.csv"
        response.headers["Content-type"] = "text/csv"
        
        return response
    except Exception as e:
        current_app.logger.error(f"Error exporting users: {str(e)}")
        return jsonify({'error': str(e)}), 500

@admin.route('/api/admin/users/<string:username>', methods=['DELETE'])
@login_required
@permission_required_ajax(Permission.MANAGE_USERS)
def delete_user_api(username):
    """Delete a user."""
    try:
        # Don't allow deletion of own account
        if current_user.username == username:
            return jsonify({'error': 'Cannot delete your own account'}), 403
        
        user = User.query.filter_by(username=username).first()
        
        if not user:
            return jsonify({'error': f"User '{username}' not found"}), 404
        
        # Check if user has a custom role that should be deleted
        custom_role = None
        if user.role and user.role.name.startswith(f"Custom_{user.username}"):
            custom_role = user.role
        
        db.session.delete(user)
        
        # Delete custom role if it exists
        if custom_role:
            db.session.delete(custom_role)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"User '{username}' deleted successfully"
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting user: {str(e)}")
        return jsonify({'error': str(e)}), 500

import csv
from io import StringIO

@admin.route('/admin/ampds/export', methods=['GET'])
@login_required
@role_required('ADMIN')
def export_ampds_protocols():
    """
    Export all AMPDS protocols to a CSV file.
    """
    try:
        # Get all protocols
        protocols = AMPDSProtocol.query.order_by(
            AMPDSProtocol.category, 
            AMPDSProtocol.subcategory
        ).all()

        # Create a StringIO object for the CSV data
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header row
        header = ['unique_id', 'category', 'subcategory', 'card_number', 
                  'priority', 'dispatch_advice']
        writer.writerow(header)
        
        # Write protocol data
        for protocol in protocols:
            writer.writerow([
                protocol.unique_id,
                protocol.category,
                protocol.subcategory,
                protocol.card_number,
                protocol.priority,
                protocol.dispatch_advice,
            ])
        
        # Prepare response
        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=ampds_protocols_{timestamp}.csv"}
        )
        
    except Exception as e:
        current_app.logger.error(f"Error exporting AMPDS protocols: {str(e)}")
        flash('An error occurred while exporting AMPDS protocols.', 'danger')
        return redirect(url_for('admin.ampds_management'))

@admin.route('/admin/ampds/import', methods=['POST'])
@login_required
@role_required('ADMIN')
def import_ampds_protocols():
    """
    Import AMPDS protocols from a CSV file.
    The CSV file should have the following columns:
    unique_id, category, subcategory, card_number, priority, dispatch_advice
    """
    try:
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(url_for('admin.ampds_management'))
        
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(url_for('admin.ampds_management'))
        
        if file and file.filename.endswith('.csv'):
            # Process CSV file
            csv_data = StringIO(file.read().decode('utf-8'))
            reader = csv.DictReader(csv_data)
            
            # Validate required columns
            required_columns = ['unique_id', 'category', 'subcategory', 'card_number', 'priority', 'dispatch_advice']
            if not all(col in reader.fieldnames for col in required_columns):
                flash('CSV file is missing required columns. Required columns: ' + ', '.join(required_columns), 'danger')
                return redirect(url_for('admin.ampds_management'))
            
            # Begin transaction
            db.session.begin_nested()
            
            # Track import statistics
            stats = {
                'imported': 0,
                'updated': 0,
                'skipped': 0,
                'errors': 0
            }
            
            # Process each row
            for row in reader:
                try:
                    # Check if protocol already exists
                    protocol = AMPDSProtocol.query.filter_by(unique_id=row['unique_id']).first()
                    
                    if protocol:
                        # Update existing protocol
                        protocol.category = row['category']
                        protocol.subcategory = row['subcategory']
                        protocol.card_number = row['card_number']
                        protocol.priority = row['priority']
                        protocol.dispatch_advice = row['dispatch_advice']
                        stats['updated'] += 1
                    else:
                        # Create new protocol
                        protocol = AMPDSProtocol(
                            unique_id=row['unique_id'],
                            category=row['category'],
                            subcategory=row['subcategory'],
                            card_number=row['card_number'],
                            priority=row['priority'],
                            dispatch_advice=row['dispatch_advice']
                        )
                        db.session.add(protocol)
                        stats['imported'] += 1
                        
                except Exception as e:
                    current_app.logger.error(f"Error importing protocol {row.get('unique_id')}: {str(e)}")
                    stats['errors'] += 1
            
            # Commit transaction if no errors
            if stats['errors'] == 0:
                db.session.commit()
                flash(f"Import completed: {stats['imported']} imported, {stats['updated']} updated.", 'success')
            else:
                db.session.rollback()
                flash(f"Import failed with {stats['errors']} errors.", 'danger')
            
            return redirect(url_for('admin.ampds_management'))
        else:
            flash('File must be a CSV', 'danger')
            return redirect(url_for('admin.ampds_management'))
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error importing AMPDS protocols: {str(e)}")
        flash('An error occurred while importing AMPDS protocols.', 'danger')
        return redirect(url_for('admin.ampds_management'))
