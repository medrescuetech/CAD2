"""
Incident Management Blueprint

This module provides endpoints for managing incidents including:
- Creating new incidents
- Updating incident details
- Changing incident status
- Assigning units to incidents
- Managing incident logs
"""

from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required, current_user
from models import db, Incident, IncidentType, IncidentLog, UnitAssignment, Unit, Location, Permission
from utils.decorators import permission_required
from utils.security import secure_endpoint
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
from sqlalchemy import desc, or_
import datetime
import json

bp = Blueprint('incidents', __name__)

# Incident CRUD operations
@bp.route('/incidents', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def get_incidents():
    """
    Get all incidents with optional filtering.
    
    Query Parameters:
    - status: Filter by incident status (pending, open, closed)
    - priority: Filter by priority level
    - type: Filter by incident type ID
    - start_date: Filter incidents created after this date
    - end_date: Filter incidents created before this date
    - q: Text search in incident number, location, and description
    """
    # Parse query parameters
    status = request.args.get('status')
    priority = request.args.get('priority')
    incident_type_id = request.args.get('type')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    search_query = request.args.get('q', '')
    
    # Build base query
    query = Incident.query
    
    # Apply filters
    if status:
        query = query.filter(Incident.status == status)
    
    if priority:
        try:
            priority_value = int(priority)
            query = query.filter(Incident.priority == priority_value)
        except ValueError:
            pass
    
    if incident_type_id:
        try:
            type_id = int(incident_type_id)
            query = query.filter(Incident.incident_type_id == type_id)
        except ValueError:
            pass
    
    # Date filtering
    if start_date:
        try:
            start = datetime.datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(Incident.created_at >= start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.datetime.strptime(end_date, '%Y-%m-%d')
            # Set end to end of day
            end = end.replace(hour=23, minute=59, second=59)
            query = query.filter(Incident.created_at <= end)
        except ValueError:
            pass
    
    # Text search
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            or_(
                Incident.incident_number.ilike(search_term),
                Incident.location.ilike(search_term),
                Incident.description.ilike(search_term)
            )
        )
    
    # Order by latest incidents first
    query = query.order_by(desc(Incident.created_at))
    
    # Execute query and convert to dict
    incidents = query.all()
    result = [incident.to_dict() for incident in incidents]
    
    return jsonify({
        'success': True,
        'incidents': result
    })

@bp.route('/incidents/<int:incident_id>', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def get_incident(incident_id):
    """Get details of a specific incident."""
    incident = Incident.query.get_or_404(incident_id)
    
    # Include related data
    incident_data = incident.to_dict(include_logs=True, include_units=True)
    
    return jsonify({
        'success': True,
        'incident': incident_data
    })

@bp.route('/incidents', methods=['POST'])
@login_required
@permission_required(Permission.CREATE_INCIDENT)
@secure_endpoint(limit="20/minute")
def create_incident():
    """Create a new incident."""
    data = request.get_json()
    
    # Validate required fields
    if not data or not data.get('incident_type_id'):
        return jsonify({
            'success': False,
            'message': 'Incident type is required'
        }), 400
    
    try:
        # Create new incident
        incident = Incident(
            incident_type_id=data.get('incident_type_id'),
            priority=data.get('priority', Incident.PRIORITY_MEDIUM),
            status=Incident.STATUS_PENDING,
            location=data.get('location'),
            location_id=data.get('location_id'),
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            caller=data.get('caller'),
            callback_number=data.get('callback_number'),
            description=data.get('description'),
            ampds_code=data.get('ampds_code'),
            ampds_data=data.get('ampds_data'),
            created_by_id=current_user.id
        )
        
        db.session.add(incident)
        db.session.commit()
        
        # Create initial log entry
        log_entry = IncidentLog(
            incident_id=incident.id,
            user_id=current_user.id,
            message="Incident created",
            action="create",
            data=json.dumps(incident.to_dict())
        )
        db.session.add(log_entry)
        db.session.commit()
        
        # Audit log
        log_audit_event(
            user_id=current_user.id,
            category=AuditCategory.INCIDENT,
            action="create",
            resource_id=str(incident.id),
            resource_type="Incident",
            severity=AuditSeverity.INFO,
            details=f"Created incident {incident.incident_number}"
        )
        
        return jsonify({
            'success': True,
            'message': 'Incident created successfully',
            'incident': incident.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating incident: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error creating incident'
        }), 500

@bp.route('/incidents/<int:incident_id>', methods=['PUT'])
@login_required
@permission_required(Permission.EDIT_INCIDENTS)
@secure_endpoint(limit="20/minute")
def update_incident(incident_id):
    """Update an existing incident."""
    incident = Incident.query.get_or_404(incident_id)
    data = request.get_json()
    
    try:
        # Save original state for logging
        original_data = incident.to_dict()
        
        # Update fields
        if 'incident_type_id' in data:
            incident.incident_type_id = data['incident_type_id']
        
        if 'priority' in data:
            incident.set_priority(data['priority'])
        
        if 'status' in data:
            incident.status = data['status']
        
        if 'location' in data:
            incident.location = data['location']
        
        if 'location_id' in data:
            incident.location_id = data['location_id']
            
        if 'latitude' in data:
            incident.latitude = data['latitude']
            
        if 'longitude' in data:
            incident.longitude = data['longitude']
            
        if 'caller' in data:
            incident.caller = data['caller']
            
        if 'callback_number' in data:
            incident.callback_number = data['callback_number']
            
        if 'description' in data:
            incident.description = data['description']
            
        if 'ampds_code' in data:
            incident.ampds_code = data['ampds_code']
            
        if 'ampds_data' in data:
            incident.ampds_data = data['ampds_data']
            
        if 'resolution' in data and incident.status == Incident.STATUS_CLOSED:
            incident.resolution = data['resolution']
        
        # Track who updated it
        incident.updated_by_id = current_user.id
        
        db.session.commit()
        
        # Create log entry for update
        log_entry = IncidentLog(
            incident_id=incident.id,
            user_id=current_user.id,
            message="Incident updated",
            action="update",
            data=json.dumps({
                'before': original_data,
                'after': incident.to_dict()
            })
        )
        db.session.add(log_entry)
        db.session.commit()
        
        # Audit log
        log_audit_event(
            user_id=current_user.id,
            category=AuditCategory.INCIDENT,
            action="update",
            resource_id=str(incident.id),
            resource_type="Incident",
            severity=AuditSeverity.INFO,
            details=f"Updated incident {incident.incident_number}"
        )
        
        return jsonify({
            'success': True,
            'message': 'Incident updated successfully',
            'incident': incident.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating incident: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error updating incident: {str(e)}'
        }), 500

@bp.route('/incidents/<int:incident_id>/status', methods=['PUT'])
@login_required
@permission_required(Permission.EDIT_INCIDENTS)
@secure_endpoint(limit="30/minute")
def update_incident_status(incident_id):
    """Update the status of an incident."""
    incident = Incident.query.get_or_404(incident_id)
    data = request.get_json()
    
    if not data or 'status' not in data:
        return jsonify({
            'success': False,
            'message': 'Status is required'
        }), 400
    
    new_status = data['status']
    old_status = incident.status
    
    # Validate status
    if new_status not in [Incident.STATUS_PENDING, Incident.STATUS_OPEN, Incident.STATUS_CLOSED]:
        return jsonify({
            'success': False,
            'message': 'Invalid status'
        }), 400
    
    try:
        # Update status
        incident.status = new_status
        
        # If closing, require resolution
        if new_status == Incident.STATUS_CLOSED:
            if not data.get('resolution'):
                return jsonify({
                    'success': False,
                    'message': 'Resolution is required when closing an incident'
                }), 400
            incident.resolution = data['resolution']
        
        incident.updated_by_id = current_user.id
        db.session.commit()
        
        # Create log entry
        log_entry = IncidentLog(
            incident_id=incident.id,
            user_id=current_user.id,
            message=f"Status changed from {old_status} to {new_status}",
            action="status_change",
            data=json.dumps({
                'from': old_status,
                'to': new_status,
                'resolution': data.get('resolution') if new_status == Incident.STATUS_CLOSED else None
            })
        )
        db.session.add(log_entry)
        db.session.commit()
        
        # Audit log
        log_audit_event(
            user_id=current_user.id,
            category=AuditCategory.INCIDENT,
            action="status_change",
            resource_id=str(incident.id),
            resource_type="Incident",
            severity=AuditSeverity.INFO,
            details=f"Changed status of incident {incident.incident_number} from {old_status} to {new_status}"
        )
        
        return jsonify({
            'success': True,
            'message': 'Incident status updated successfully',
            'incident': incident.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating incident status: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error updating incident status'
        }), 500

# Incident Types
@bp.route('/incident-types', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def get_incident_types():
    """Get all incident types."""
    incident_types = IncidentType.query.all()
    result = [incident_type.to_dict() for incident_type in incident_types]
    
    return jsonify({
        'success': True,
        'incident_types': result
    })

# Unit Assignment Endpoints
@bp.route('/incidents/<int:incident_id>/units', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def get_incident_units(incident_id):
    """Get all units assigned to an incident."""
    incident = Incident.query.get_or_404(incident_id)
    
    assignments = UnitAssignment.query.filter_by(incident_id=incident.id).all()
    result = [assignment.to_dict() for assignment in assignments]
    
    return jsonify({
        'success': True,
        'incident_id': incident.id,
        'units': result
    })

@bp.route('/incidents/<int:incident_id>/units', methods=['POST'])
@login_required
@permission_required(Permission.ASSIGN_UNITS)
@secure_endpoint(limit="20/minute")
def assign_unit(incident_id):
    """Assign a unit to an incident."""
    incident = Incident.query.get_or_404(incident_id)
    data = request.get_json()
    
    if not data or 'unit_id' not in data:
        return jsonify({
            'success': False,
            'message': 'Unit ID is required'
        }), 400
    
    unit_id = data['unit_id']
    unit = Unit.query.get_or_404(unit_id)
    
    # Check if unit is already assigned to this incident
    existing = UnitAssignment.query.filter_by(
        incident_id=incident.id,
        unit_id=unit.id,
        end_time=None
    ).first()
    
    if existing:
        return jsonify({
            'success': False,
            'message': 'Unit is already assigned to this incident'
        }), 400
    
    try:
        # Create new assignment
        assignment = UnitAssignment(
            incident_id=incident.id,
            unit_id=unit.id,
            start_time=datetime.datetime.utcnow(),
            notes=data.get('notes', ''),
            assigned_by_id=current_user.id
        )
        
        db.session.add(assignment)
        db.session.commit()
        
        # Create log entry
        log_entry = IncidentLog(
            incident_id=incident.id,
            user_id=current_user.id,
            message=f"Unit {unit.name} assigned to incident",
            action="unit_assigned",
            data=json.dumps(assignment.to_dict())
        )
        db.session.add(log_entry)
        db.session.commit()
        
        # Audit log
        log_audit_event(
            user_id=current_user.id,
            category=AuditCategory.INCIDENT,
            action="unit_assigned",
            resource_id=str(incident.id),
            resource_type="Incident",
            severity=AuditSeverity.INFO,
            details=f"Assigned unit {unit.name} to incident {incident.incident_number}"
        )
        
        return jsonify({
            'success': True,
            'message': 'Unit assigned successfully',
            'assignment': assignment.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error assigning unit: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error assigning unit'
        }), 500

@bp.route('/incidents/<int:incident_id>/units/<int:unit_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.ASSIGN_UNITS)
@secure_endpoint(limit="20/minute")
def unassign_unit(incident_id, unit_id):
    """Unassign a unit from an incident."""
    # Find the active assignment
    assignment = UnitAssignment.query.filter_by(
        incident_id=incident_id,
        unit_id=unit_id,
        end_time=None
    ).first_or_404()
    
    try:
        # Set end time
        assignment.end_time = datetime.datetime.utcnow()
        assignment.completed_by_id = current_user.id
        db.session.commit()
        
        # Get unit and incident for logging
        unit = Unit.query.get(unit_id)
        incident = Incident.query.get(incident_id)
        
        # Create log entry
        log_entry = IncidentLog(
            incident_id=incident_id,
            user_id=current_user.id,
            message=f"Unit {unit.name} unassigned from incident",
            action="unit_unassigned",
            data=json.dumps(assignment.to_dict())
        )
        db.session.add(log_entry)
        db.session.commit()
        
        # Audit log
        log_audit_event(
            user_id=current_user.id,
            category=AuditCategory.INCIDENT,
            action="unit_unassigned",
            resource_id=str(incident_id),
            resource_type="Incident",
            severity=AuditSeverity.INFO,
            details=f"Unassigned unit {unit.name} from incident {incident.incident_number}"
        )
        
        return jsonify({
            'success': True,
            'message': 'Unit unassigned successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error unassigning unit: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error unassigning unit'
        }), 500

# Incident Log Endpoints
@bp.route('/incidents/<int:incident_id>/logs', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def get_incident_logs(incident_id):
    """Get logs for an incident."""
    Incident.query.get_or_404(incident_id)  # Verify incident exists
    
    logs = IncidentLog.query.filter_by(incident_id=incident_id).order_by(IncidentLog.timestamp.desc()).all()
    result = [log.to_dict() for log in logs]
    
    return jsonify({
        'success': True,
        'incident_id': incident_id,
        'logs': result
    })

@bp.route('/incidents/<int:incident_id>/logs', methods=['POST'])
@login_required
@secure_endpoint(limit="30/minute")
def add_incident_log(incident_id):
    """Add a log entry to an incident."""
    incident = Incident.query.get_or_404(incident_id)
    data = request.get_json()
    
    if not data or 'message' not in data:
        return jsonify({
            'success': False,
            'message': 'Log message is required'
        }), 400
    
    try:
        # Create log entry
        log_entry = IncidentLog(
            incident_id=incident.id,
            user_id=current_user.id,
            message=data['message'],
            action=data.get('action', 'comment'),
            data=json.dumps(data.get('data', {}))
        )
        
        db.session.add(log_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Log entry added successfully',
            'log': log_entry.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding log entry: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error adding log entry'
        }), 500

# Incident Report Endpoints
@bp.route('/incidents/<int:incident_id>/report', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_INCIDENTS)
@secure_endpoint(limit="10/minute")
def generate_incident_report(incident_id):
    """Generate a report for an incident."""
    incident = Incident.query.get_or_404(incident_id)
    
    # Get incident details, logs, and unit assignments
    incident_data = incident.to_dict(include_logs=True, include_units=True)
    
    # Render the incident report template
    return render_template('incident_report.html', incident=incident_data)

# Frontend route
@bp.route('/', methods=['GET'])
@login_required
def incident_dashboard():
    """Render the incident dashboard page."""
    return render_template('incident.html')
