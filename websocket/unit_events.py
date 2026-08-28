"""
Unit WebSocket Events

This module contains WebSocket event handlers for unit-related operations including:
- Real-time unit status updates
- Unit location tracking
- Unit assignment to incidents
- Unit availability broadcasting
"""

from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room
from models import Unit, UnitType, UnitStatus, Permission
from extensions import db, socketio
from datetime import datetime
import logging
from services.connection_manager import ConnectionManager
from services.notification_service import NotificationService
from utils.audit import create_audit_log

logger = logging.getLogger(__name__)

def check_auth():
    """Check if user is authenticated."""
    if not current_user.is_authenticated:
        emit('error', {'message': 'AUTH_REQUIRED', 'details': 'Authentication required'})
        return False
    return True

def check_permission(permission):
    """Check if user has required permission."""
    if not current_user.is_authenticated or not current_user.role.has_permission(permission):
        emit('error', {'message': 'PERMISSION_DENIED', 'details': 'Insufficient permissions'})
        return False
    return True

@socketio.on('join_unit_updates')
def handle_join_unit_updates():
    """Join the unit updates room to receive real-time unit updates."""
    try:
        if not check_auth():
            return
        
        client_id = request.sid
        join_room('unit_updates')
        ConnectionManager.add_to_room(client_id, 'unit_updates')
        
        emit('room_joined', {'room': 'unit_updates'})
        logger.debug(f"Client {client_id} joined unit_updates room")
        
    except Exception as e:
        logger.error(f"Error joining unit_updates room: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('leave_unit_updates')
def handle_leave_unit_updates():
    """Leave the unit updates room."""
    try:
        if not check_auth():
            return
        
        client_id = request.sid
        leave_room('unit_updates')
        ConnectionManager.remove_from_room(client_id, 'unit_updates')
        
        emit('room_left', {'room': 'unit_updates'})
        logger.debug(f"Client {client_id} left unit_updates room")
        
    except Exception as e:
        logger.error(f"Error leaving unit_updates room: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_units')
def handle_get_units(data=None):
    """Get all units, optionally filtered by status, type, or availability."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.VIEW_UNITS):
            return
            
        # Initialize query
        query = Unit.query
        
        # Apply filters if provided
        if data:
            if 'status' in data:
                query = query.filter(Unit.status == data['status'])
                
            if 'type_id' in data:
                query = query.filter(Unit.unit_type_id == data['type_id'])
                
            if 'available' in data and data['available']:
                query = query.filter(Unit.incident_id == None)
                
            if 'assigned' in data and data['assigned']:
                query = query.filter(Unit.incident_id != None)
        
        # Execute query
        units = query.all()
        
        # Convert to dictionary format for JSON response
        result = [unit.to_dict() for unit in units]
        
        emit('units', {'units': result, 'count': len(result)})
        
    except Exception as e:
        logger.error(f"Error getting units: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_unit')
def handle_get_unit(data):
    """Get a specific unit by ID."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.VIEW_UNITS):
            return
            
        if 'id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Unit ID is required'})
            return
            
        unit_id = data['id']
        unit = Unit.query.get(unit_id)
            
        if not unit:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Unit with ID {unit_id} not found'})
            return
            
        # Get detailed unit data
        unit_data = unit.to_dict(include_incident=True)
            
        emit('unit_details', {'unit': unit_data})
            
    except Exception as e:
        logger.error(f"Error getting unit details: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('update_unit_status')
def handle_update_unit_status(data):
    """Update a unit's status."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.UPDATE_UNITS):
            return
            
        # Validate required fields
        required_fields = ['unit_id', 'status']
        if not all(field in data for field in required_fields):
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Missing required fields'})
            return
            
        unit_id = data['unit_id']
        new_status = data['status']
            
        # Check if unit exists
        unit = Unit.query.get(unit_id)
        if not unit:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Unit with ID {unit_id} not found'})
            return
            
        # Check if status is valid
        valid_statuses = UnitStatus.get_valid_statuses()
        if new_status not in valid_statuses:
            emit('error', {
                'message': 'VALIDATION_ERROR', 
                'details': f'Invalid status. Valid statuses are: {", ".join(valid_statuses)}'
            })
            return
            
        # Store previous status for notifications and audit
        previous_status = unit.status
            
        # Check if we're trying to set unit to available while assigned to an incident
        if new_status == 'available' and unit.incident_id is not None and not data.get('force_update', False):
            emit('error', {
                'message': 'VALIDATION_ERROR',
                'details': f'Unit {unit.name} is assigned to an incident. Clear unit from incident first or use force_update=true'
            })
            return
            
        # Clear incident if force_update and setting to available
        if new_status == 'available' and unit.incident_id is not None and data.get('force_update', False):
            # Get incident before clearing for logging
            from models import Incident
            incident = Incident.query.get(unit.incident_id)
            if incident:
                # Create log entry for incident
                from models import IncidentLog
                log_entry = IncidentLog(
                    incident_id=incident.id,
                    log_type='system',
                    message=f"Unit {unit.name} force-cleared from incident due to status change to available",
                    created_by_id=current_user.id
                )
                db.session.add(log_entry)
                
            # Clear the incident assignment
            unit.incident_id = None
            
        # Update status
        unit.status = new_status
        unit.updated_at = datetime.utcnow()
            
        db.session.commit()
            
        # Create audit log
        create_audit_log(
            entity_type='unit',
            entity_id=unit.id,
            action='update_status',
            details=f"Unit {unit.name} status changed from {previous_status} to {new_status}"
        )
            
        # Get updated unit data
        unit_data = unit.to_dict(include_incident=True)
            
        # Broadcast to all clients in unit_updates room
        socketio.emit('unit_status_changed', {
            'unit': unit_data,
            'previous_status': previous_status,
            'new_status': new_status
        }, room='unit_updates')
            
        # Send response to the requesting client
        emit('unit_status_updated_confirm', {
            'unit': unit_data,
            'message': f'Unit status updated from {previous_status} to {new_status}'
        })
            
        # Notify unit operator if one is assigned
        if unit.operator_id:
            NotificationService.create_notification(
                user_id=unit.operator_id,
                title=f"Unit {unit.name} Status Changed",
                message=f"Your unit status has been changed from {previous_status} to {new_status}",
                notification_type='unit',
                reference_id=unit.id,
                reference_type='unit_status_changed',
                broadcast=True,
                send_email=False  # Don't email for status changes
            )
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating unit status: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('update_unit_location')
def handle_update_unit_location(data):
    """Update a unit's location."""
    try:
        if not check_auth():
            return
            
        # Validate required fields
        required_fields = ['unit_id', 'latitude', 'longitude']
        if not all(field in data for field in required_fields):
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Missing required fields'})
            return
            
        unit_id = data['unit_id']
        latitude = data['latitude']
        longitude = data['longitude']
            
        # Check if unit exists
        unit = Unit.query.get(unit_id)
        if not unit:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Unit with ID {unit_id} not found'})
            return
            
        # Check if user has permission to update this unit
        is_operator = current_user.id == unit.operator_id
        has_update_permission = check_permission(Permission.UPDATE_UNITS)
            
        if not (is_operator or has_update_permission):
            emit('error', {'message': 'PERMISSION_DENIED', 'details': 'You do not have permission to update this unit\'s location'})
            return
            
        # Update location
        unit.latitude = latitude
        unit.longitude = longitude
        unit.last_location_update = datetime.utcnow()
            
        # Optionally update location name and address if provided
        if 'location_name' in data:
            unit.location_name = data['location_name']
            
        if 'location_address' in data:
            unit.location_address = data['location_address']
            
        db.session.commit()
            
        # Get updated unit data
        unit_data = unit.to_dict()
            
        # Broadcast to all clients in unit_updates room
        socketio.emit('unit_location_updated', {
            'unit': unit_data,
            'latitude': latitude,
            'longitude': longitude
        }, room='unit_updates')
            
        # Send response to the requesting client
        emit('unit_location_updated_confirm', {
            'unit': unit_data,
            'message': f'Unit location updated'
        })
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating unit location: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('update_unit_operator')
def handle_update_unit_operator(data):
    """Update a unit's operator."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.ASSIGN_UNIT_OPERATORS):
            return
            
        # Validate required fields
        if 'unit_id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Unit ID is required'})
            return
            
        unit_id = data['unit_id']
            
        # Check if unit exists
        unit = Unit.query.get(unit_id)
        if not unit:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Unit with ID {unit_id} not found'})
            return
            
        # Store previous operator for notifications and audit
        previous_operator_id = unit.operator_id
            
        # Update operator (can be null to clear operator)
        unit.operator_id = data.get('operator_id')
        unit.updated_at = datetime.utcnow()
            
        db.session.commit()
            
        # Get user info for audit trail
        previous_operator_name = "None"
        new_operator_name = "None"
            
        if previous_operator_id:
            from models import User
            previous_user = User.query.get(previous_operator_id)
            if previous_user:
                previous_operator_name = previous_user.username
                
        if unit.operator_id:
            from models import User
            new_user = User.query.get(unit.operator_id)
            if new_user:
                new_operator_name = new_user.username
                
        # Create audit log
        create_audit_log(
            entity_type='unit',
            entity_id=unit.id,
            action='update_operator',
            details=f"Unit {unit.name} operator changed from {previous_operator_name} to {new_operator_name}"
        )
            
        # Get updated unit data
        unit_data = unit.to_dict(include_incident=True)
            
        # Broadcast to all clients in unit_updates room
        socketio.emit('unit_operator_changed', {
            'unit': unit_data,
            'previous_operator_id': previous_operator_id,
            'new_operator_id': unit.operator_id
        }, room='unit_updates')
            
        # Send response to the requesting client
        emit('unit_operator_updated_confirm', {
            'unit': unit_data,
            'message': f'Unit operator updated'
        })
            
        # Notify previous operator if there was one
        if previous_operator_id:
            NotificationService.create_notification(
                user_id=previous_operator_id,
                title=f"Unit Assignment Removed",
                message=f"You have been removed as the operator of unit {unit.name}",
                notification_type='unit',
                reference_id=unit.id,
                reference_type='unit_operator_removed',
                broadcast=True,
                send_email=True
            )
            
        # Notify new operator if there is one
        if unit.operator_id:
            NotificationService.create_notification(
                user_id=unit.operator_id,
                title=f"Unit Assignment",
                message=f"You have been assigned as the operator of unit {unit.name}",
                notification_type='unit',
                reference_id=unit.id,
                reference_type='unit_operator_assigned',
                broadcast=True,
                send_email=True
            )
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating unit operator: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('assign_unit_to_incident')
def handle_assign_unit_to_incident(data):
    """Assign a unit to an incident (redirects to incident_events.assign_unit)."""
    try:
        # Import the function from incident_events
        from .incident_events import handle_assign_unit
        
        # Call the function from incident_events
        handle_assign_unit(data)
        
    except Exception as e:
        logger.error(f"Error in assign_unit_to_incident redirect: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('clear_unit_from_incident')
def handle_clear_unit_from_incident(data):
    """Clear a unit from an incident (redirects to incident_events.clear_unit)."""
    try:
        # Import the function from incident_events
        from .incident_events import handle_clear_unit
        
        # Call the function from incident_events
        handle_clear_unit(data)
        
    except Exception as e:
        logger.error(f"Error in clear_unit_from_incident redirect: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_unit_types')
def handle_get_unit_types():
    """Get all unit types."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.VIEW_UNITS):
            return
            
        # Get all unit types
        unit_types = UnitType.query.all()
            
        # Convert to dictionary format for JSON response
        result = [unit_type.to_dict() for unit_type in unit_types]
            
        emit('unit_types', {'unit_types': result, 'count': len(result)})
            
    except Exception as e:
        logger.error(f"Error getting unit types: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_unit_statuses')
def handle_get_unit_statuses():
    """Get all valid unit statuses."""
    try:
        if not check_auth():
            return
            
        # Get all valid statuses
        statuses = UnitStatus.get_valid_statuses()
            
        emit('unit_statuses', {'statuses': statuses, 'count': len(statuses)})
            
    except Exception as e:
        logger.error(f"Error getting unit statuses: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})
