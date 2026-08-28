from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from models import Incident, Unit, IncidentLog, UnitAssignment, PickupPoint, DailyLog, Permission, Location, User, AMPDSProtocol
from extensions import db, socketio
from datetime import datetime
from blueprints.admin import permission_required
import json
import logging

logger = logging.getLogger(__name__)

pages = Blueprint('pages', __name__)

@pages.context_processor
def inject_permissions():
    return dict(Permission=Permission)

@pages.route('/')
@login_required
def index():
    """Main dashboard page."""
    try:
        logger.info(f"User {current_user.username} accessed index page")
        active_units = Unit.query.filter(Unit.status != 'Out of Service').all()
        
        # Modified to use a different query approach that explicitly selects columns
        # to avoid the missing incident_type_id column
        active_incidents = db.session.query(
            Incident.id,
            Incident.incident_number,
            Incident.priority,
            Incident.status,
            Incident.location,
            Incident.location_id,
            Incident.latitude,
            Incident.longitude,
            Incident.caller,
            Incident.callback_number,
            Incident.description,
            Incident.ampds_code,
            Incident.created_at,
            Incident.updated_at
        ).filter(
            Incident.status.in_(['active', 'pending'])
        ).order_by(Incident.priority.desc()).all()
        
        # Process units for template
        for unit in active_units:
            unit.status_class = {
                'Available': 'success',
                'Assigned': 'warning',
                'En Route': 'info',
                'On Scene': 'primary',
                'Busy': 'danger'
            }.get(unit.status, 'secondary')
        
        # Calculate stats
        stats = {
            'active_units': len(active_units),
            'available_units': len([u for u in active_units if u.status == 'Available']),
            'active_incidents': len(active_incidents),
            'total_units': Unit.query.count(),
            'total_incidents': Incident.query.count()
        }
        
        return current_app.custom_render_template('index.html', title='Dashboard', active_units=active_units, active_incidents=active_incidents, stats=stats)
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        return current_app.custom_render_template('errors/500.html'), 500

@pages.route('/dashboard')
@login_required
def dashboard():
    active_incidents = Incident.query.filter(
        Incident.status.in_(['active', 'pending'])
    ).order_by(Incident.priority.desc(), Incident.created_at.desc()).all()
    
    available_units = Unit.query.filter_by(status='Available').all()
    
    return current_app.custom_render_template('dashboard.html', title='Dashboard', incidents=active_incidents, units=available_units)

@pages.route('/incidents')
@login_required
def incidents():
    if not current_user.role.has_permission(Permission.VIEW_INCIDENTS):
        logger.warning(f"User {current_user.username} attempted to access incidents without permission")
        return current_app.custom_render_template('errors/403.html'), 403
    
    logger.info(f"User {current_user.username} accessed incidents page")
    incidents = Incident.query.order_by(Incident.created_at.desc()).all()
    return current_app.custom_render_template('view_incidents.html', title='Incidents', incidents=incidents)

@pages.route('/incident', defaults={'incident_id': None}, methods=['GET', 'POST'])
@pages.route('/incident/<int:incident_id>', methods=['GET', 'POST'])
@login_required
def incident(incident_id=None):
    """Create or edit an incident."""
    if incident_id:
        incident = Incident.query.get_or_404(incident_id)
        if not current_user.can(Permission.EDIT_INCIDENTS):
            flash('You do not have permission to edit incidents.', 'error')
            return redirect(url_for('pages.incidents'))
    else:
        if not current_user.can(Permission.CREATE_INCIDENTS):
            flash('You do not have permission to create incidents.', 'error')
            return redirect(url_for('pages.incidents'))
        incident = None

    if request.method == 'POST':
        if incident_id:
            # Update existing incident
            incident.incident_type = request.form.get('incident_type')
            incident.priority = request.form.get('priority')
            incident.status = request.form.get('status')
            incident.location = request.form.get('location')
            incident.description = request.form.get('description')
            incident.updated_at = datetime.utcnow()
            db.session.commit()
            flash('Incident updated successfully.', 'success')
        else:
            # Create new incident
            incident = Incident(
                incident_number=Incident.generate_incident_number(),
                incident_type=request.form.get('incident_type'),
                priority=request.form.get('priority'),
                status='pending',
                location=request.form.get('location'),
                description=request.form.get('description'),
                created_by_id=current_user.id,
                created_at=datetime.utcnow()
            )
            db.session.add(incident)
            db.session.commit()
            flash('Incident created successfully.', 'success')
        
        return redirect(url_for('pages.view_incident', incident_id=incident.id))
    
    return current_app.custom_render_template('incident.html', title='Incident', incident=incident)

@pages.route('/incidents/new', methods=['GET', 'POST'])
@login_required
def new_incident():
    """Create a new incident."""
    if request.method == 'POST':
        # Get form data
        incident_type = request.form.get('incident_type')
        priority = request.form.get('priority')
        location = request.form.get('location')
        location_id = request.form.get('location_id')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        description = request.form.get('description')
        
        # Create new incident
        incident = Incident(
            incident_number=Incident.generate_incident_number(),
            incident_type=incident_type,
            priority=int(priority),
            status='pending',
            location=location,
            location_id=location_id if location_id else None,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            description=description,
            created_by_id=current_user.id,
            created_at=datetime.utcnow()
        )
        
        db.session.add(incident)
        db.session.commit()
        
        # If this was an AJAX request, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'incident': incident.to_dict()
            })
            
        # For regular form submit, redirect to the incident view
        flash('Incident created successfully.', 'success')
        return redirect(url_for('pages.view_incident', incident_id=incident.id))
        
    # GET request - render the incident form
    return current_app.custom_render_template('incidents/create.html', title='New Incident')

@pages.route('/incidents/<int:incident_id>')
@login_required
def view_incident(incident_id):
    """View a single incident."""
    incident = Incident.query.get_or_404(incident_id)
    
    if request.method == 'POST':
        # Update incident fields
        incident.incident_type = request.form.get('incident_type')
        incident.priority = int(request.form.get('priority'))
        incident.status = request.form.get('status')
        incident.location = request.form.get('location')
        incident.location_id = request.form.get('location_id')
        incident.latitude = float(request.form.get('latitude')) if request.form.get('latitude') else None
        incident.longitude = float(request.form.get('longitude')) if request.form.get('longitude') else None
        incident.description = request.form.get('description')
        incident.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # If this was an AJAX request, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True})
        
        # Otherwise redirect back to the incident page
        return redirect(url_for('pages.view_incident', incident_id=incident_id))
    
    # GET request - render the incident form with existing data
    return current_app.custom_render_template('incidents/view.html', title='Incident', incident=incident)

@pages.route('/incidents/<int:incident_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_incident(incident_id):
    """Edit an existing incident."""
    incident = Incident.query.get_or_404(incident_id)
    if not current_user.has_permission(Permission.EDIT_INCIDENTS):
        return jsonify({'error': 'Permission denied'}), 403
        
    try:
        data = request.get_json()
        
        # Update basic fields
        incident.incident_type = data.get('incident_type', incident.incident_type)
        incident.priority = int(data.get('priority', incident.priority))
        incident.description = data.get('description', incident.description)
        
        # Update location if provided
        if 'location' in data:
            incident.location = data['location']
            if 'location_id' in data:
                incident.location_id = data['location_id']
            if 'latitude' in data and 'longitude' in data:
                incident.latitude = float(data['latitude'])
                incident.longitude = float(data['longitude'])
        
        # Log the edit
        log = IncidentLog(
            incident_id=incident.id,
            user_id=current_user.id,
            action='EDIT',
            details=f'Incident updated by {current_user.username}'
        )
        db.session.add(log)
        
        db.session.commit()
        return jsonify({'success': True, 'incident': incident.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

    return current_app.custom_render_template('incidents/edit.html', title='Edit Incident', incident=incident)

@pages.route('/incident/<int:incident_id>/status', methods=['POST'])
@login_required
def update_incident_status(incident_id):
    """Update incident status."""
    incident = Incident.query.get_or_404(incident_id)
    
    if not current_user.has_permission(Permission.EDIT_INCIDENTS):
        return jsonify({'error': 'Permission denied'}), 403
        
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if not new_status:
            return jsonify({'error': 'Status is required'}), 400
            
        old_status = incident.status
        incident.status = new_status
        
        # Log the status change
        log = IncidentLog(
            incident_id=incident.id,
            user_id=current_user.id,
            action='STATUS_CHANGE',
            details=f'Status changed from {old_status} to {new_status}'
        )
        db.session.add(log)
        
        db.session.commit()
        
        # Notify via WebSocket
        socketio.emit('incident_update', {
            'incident_id': incident.id,
            'status': new_status
        })
        
        return jsonify({'success': True, 'status': new_status})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@pages.route('/incident/<int:incident_id>/log', methods=['POST'])
@login_required
def add_incident_log(incident_id):
    """Add a log entry to an incident."""
    incident = Incident.query.get_or_404(incident_id)
    
    try:
        data = request.get_json()
        message = data.get('message')
        log_type = data.get('type', 'NOTE')
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
            
        log = IncidentLog(
            incident_id=incident.id,
            user_id=current_user.id,
            action=log_type,
            details=message
        )
        db.session.add(log)
        db.session.commit()
        
        # Format for display
        formatted_log = {
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'user': current_user.username,
            'action': log_type,
            'details': message
        }
        
        # Notify via WebSocket
        socketio.emit('incident_log', {
            'incident_id': incident.id,
            'log': formatted_log
        })
        
        return jsonify({'success': True, 'log': formatted_log})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@pages.route('/incident/<int:incident_id>/logs')
@login_required
def get_incident_logs(incident_id):
    """Get all logs for an incident."""
    incident = Incident.query.get_or_404(incident_id)
    
    logs = IncidentLog.query.filter_by(incident_id=incident.id)\
        .order_by(IncidentLog.timestamp.desc()).all()
        
    return jsonify({
        'logs': [{
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'user': User.query.get(log.user_id).username,
            'action': log.action,
            'details': log.details
        } for log in logs]
    })

@pages.route('/incident/<int:incident_id>/close', methods=['POST'])
@login_required
def close_incident(incident_id):
    """Close an incident."""
    incident = Incident.query.get_or_404(incident_id)
    
    if not current_user.has_permission(Permission.EDIT_INCIDENTS):
        return jsonify({'error': 'Permission denied'}), 403
        
    try:
        # Update incident status
        incident.status = 'CLOSED'
        incident.updated_at = datetime.utcnow()
        
        # Log the closure
        log = IncidentLog(
            incident_id=incident.id,
            user_id=current_user.id,
            action='CLOSED',
            details=f'Incident closed by {current_user.username}'
        )
        db.session.add(log)
        
        # Release assigned units
        for assignment in incident.units:
            unit = Unit.query.get(assignment.unit_id)
            if unit and unit.current_incident_id == incident.id:
                unit.status = 'available'
                unit.current_incident_id = None
        
        db.session.commit()
        
        # Notify via WebSocket
        socketio.emit('incident_update', {
            'incident_id': incident.id,
            'status': 'CLOSED'
        })
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@pages.route('/incident/<int:incident_id>/assign_unit', methods=['POST'])
@login_required
def assign_unit_to_incident(incident_id):
    """Assign a unit to an incident."""
    incident = Incident.query.get_or_404(incident_id)
    
    if not current_user.has_permission(Permission.EDIT_INCIDENTS):
        return jsonify({'error': 'Permission denied'}), 403
        
    try:
        data = request.get_json()
        unit_id = data.get('unit_id')
        
        if not unit_id:
            return jsonify({'error': 'Unit ID is required'}), 400
            
        unit = Unit.query.get_or_404(unit_id)
        
        # Check if unit is available
        if unit.status != 'available':
            return jsonify({
                'error': f'Unit {unit.unit_number} is not available ({unit.status})'
            }), 400
            
        # Create assignment
        assignment = UnitAssignment(
            incident_id=incident.id,
            unit_id=unit.id,
            status='dispatched'
        )
        db.session.add(assignment)
        
        # Update unit status
        unit.status = 'dispatched'
        unit.current_incident_id = incident.id
        
        # Log the assignment
        log = IncidentLog(
            incident_id=incident.id,
            user_id=current_user.id,
            action='UNIT_ASSIGNED',
            details=f'Unit {unit.unit_number} assigned to incident'
        )
        db.session.add(log)
        
        db.session.commit()
        
        # Notify via WebSocket
        socketio.emit('unit_update', {
            'unit_id': unit.id,
            'status': 'dispatched',
            'incident_id': incident.id
        })
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@pages.route('/ampds')
@login_required
@permission_required(Permission.MANAGE_AMPDS)
def ampds_management():
    """AMPDS protocols management page."""
    ampds_protocols = AMPDSProtocol.query.order_by(AMPDSProtocol.category, AMPDSProtocol.card_number).all()
    return current_app.custom_render_template('admin/ampds.html', ampds=ampds_protocols, title='AMPDS Data Management')

@pages.route('/search_location', methods=['POST'])
@login_required
def search_location():
    query = request.form.get('query', '')
    
    if query:
        # Search for locations
        locations = Location.query.filter(
            Location.name.ilike(f'%{query}%')
        ).all()
        
        if locations:
            # Return first matching location
            location = locations[0]
            return current_app.custom_render_template('_location_data.html', 
                                location=location, 
                                default_location=None)
    
    # No location found, return default
    default_location = {
        'latitude': -20.7256,  # Port Hedland
        'longitude': 116.8464
    }
    return current_app.custom_render_template('_location_data.html', 
                         location=None, 
                         default_location=default_location)

@pages.route('/units')
@login_required
def units():
    if not current_user.role.has_permission(Permission.VIEW_UNITS):
        logger.warning(f"User {current_user.username} attempted to access units without permission")
        return current_app.custom_render_template('errors/403.html'), 403
    
    logger.info(f"User {current_user.username} accessed units page")
    units = Unit.query.all()
    return current_app.custom_render_template('units.html', title='Units', units=units)

@pages.route('/unit/<int:unit_id>')
@login_required
def unit_detail(unit_id):
    unit = Unit.query.get_or_404(unit_id)
    current_assignment = UnitAssignment.query.filter_by(
        unit_id=unit_id,
        status='assigned'
    ).first()
    return current_app.custom_render_template('units/unit.html', title='Unit', unit=unit, current_assignment=current_assignment)

@pages.route('/map')
@login_required
def map_view():
    """Display map view."""
    units = Unit.query.filter_by(active=True).all()
    incidents = Incident.query.filter(Incident.status != 'closed').all()
    pickup_points = PickupPoint.query.all()
    return current_app.custom_render_template('map.html', title='Map', units=units, incidents=incidents, pickup_points=pickup_points)

@pages.route('/daily_log')
@login_required
def daily_log():
    try:
        logs = DailyLog.query.order_by(DailyLog.date.desc(), DailyLog.created_at.desc()).all()
        return current_app.custom_render_template('daily_log.html', title='Daily Log', logs=logs)
    except Exception as e:
        current_app.logger.error(f"Error in daily_log route: {str(e)}")
        # Handle the specific database column error
        if "no such column" in str(e).lower():
            return current_app.custom_render_template('errors/database_column_error.html', 
                                                    error=str(e), 
                                                    title="Database Schema Error"), 500
        # For other errors
        return current_app.custom_render_template('errors/500.html', 
                                                error=str(e),
                                                title="Internal Server Error"), 500

@pages.route('/monitor')
@login_required
def monitor():
    """Display the monitor view."""
    # Get active incidents and units
    incidents = db.session.query(
        Incident.id,
        Incident.incident_number,
        Incident.priority,
        Incident.status,
        Incident.location,
        Incident.location_id,
        Incident.latitude,
        Incident.longitude,
        Incident.caller,
        Incident.callback_number,
        Incident.description,
        Incident.ampds_code,
        Incident.ampds_data,
        Incident.resolution,
        Incident.created_at,
        Incident.updated_at,
        Incident.created_by_id,
        Incident.updated_by_id
    ).filter(
        Incident.status.in_(['active', 'pending'])
    ).order_by(Incident.priority.desc(), Incident.created_at.desc()).all()
    
    units = Unit.query.filter(Unit.status != 'Out of Service').all()
    
    return current_app.custom_render_template('monitor.html', title='Monitor', incidents=incidents, units=units)

# API Routes
@pages.route('/api/units/assign', methods=['POST'])
@login_required
def assign_unit():
    data = request.json
    unit_id = data.get('unit_id')
    incident_id = data.get('incident_id')
    
    unit = Unit.query.get_or_404(unit_id)
    incident = Incident.query.get_or_404(incident_id)
    
    if unit.status != 'Available':
        return jsonify({'error': 'Unit is not available'}), 400
    
    assignment = UnitAssignment(
        incident_id=incident_id,
        unit_id=unit_id,
        status='assigned',
        dispatched_by_id=current_user.id
    )
    
    unit.status = 'Assigned'
    unit.current_incident_id = incident_id
    
    log = IncidentLog(
        incident_id=incident_id,
        user_id=current_user.id,
        action='unit_assigned',
        details=f'Unit {unit.unit_number} assigned to incident'
    )
    
    db.session.add(assignment)
    db.session.add(log)
    db.session.commit()
    
    # Emit socket event for real-time updates
    socketio.emit('unit_assigned', {
        'unit_id': unit_id,
        'incident_id': incident_id,
        'status': 'Assigned'
    })
    
    return jsonify({'success': True})

@pages.route('/api/units/status', methods=['POST'])
@login_required
def update_unit_status():
    data = request.json
    unit_id = data.get('unit_id')
    new_status = data.get('status')
    
    unit = Unit.query.get_or_404(unit_id)
    old_status = unit.status
    unit.status = new_status
    unit.last_status_change = datetime.utcnow()
    
    if new_status == 'Available':
        unit.current_incident_id = None
    
    if unit.current_incident_id:
        log = IncidentLog(
            incident_id=unit.current_incident_id,
            user_id=current_user.id,
            action='unit_status_changed',
            details=f'Unit {unit.unit_number} status changed from {old_status} to {new_status}'
        )
        db.session.add(log)
    
    db.session.commit()
    
    # Emit socket event for real-time updates
    socketio.emit('unit_status_changed', {
        'unit_id': unit_id,
        'status': new_status
    })
    
    return jsonify({'success': True})

@pages.route('/login')
def login_redirect():
    """Redirect /login to /auth/login for backward compatibility."""
    return redirect(url_for('auth.login'))
