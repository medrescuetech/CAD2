"""
Incident WebSocket Events

This module contains WebSocket event handlers for incident-related operations including:
- Real-time incident updates
- Incident status changes
- Unit assignments to incidents
- Incident notification broadcasting
"""

from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room
from models import Incident, IncidentType, IncidentLog, Unit, Permission
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

@socketio.on('join_incident_updates')
def handle_join_incident_updates():
    """Join the incident updates room to receive real-time incident updates."""
    try:
        if not check_auth():
            return
        
        client_id = request.sid
        join_room('incident_updates')
        ConnectionManager.add_to_room(client_id, 'incident_updates')
        
        emit('room_joined', {'room': 'incident_updates'})
        logger.debug(f"Client {client_id} joined incident_updates room")
        
    except Exception as e:
        logger.error(f"Error joining incident_updates room: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('leave_incident_updates')
def handle_leave_incident_updates():
    """Leave the incident updates room."""
    try:
        if not check_auth():
            return
        
        client_id = request.sid
        leave_room('incident_updates')
        ConnectionManager.remove_from_room(client_id, 'incident_updates')
        
        emit('room_left', {'room': 'incident_updates'})
        logger.debug(f"Client {client_id} left incident_updates room")
        
    except Exception as e:
        logger.error(f"Error leaving incident_updates room: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_active_incidents')
def handle_get_active_incidents():
    """Get all non-closed incidents."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.VIEW_INCIDENTS):
            return
            
        # Query all non-closed incidents
        incidents = Incident.query.filter(Incident.status != 'closed').all()
            
        # Convert to dictionary format for JSON response
        result = [incident.to_dict() for incident in incidents]
            
        emit('active_incidents', {'incidents': result, 'count': len(result)})
            
    except Exception as e:
        logger.error(f"Error getting active incidents: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_incident')
def handle_get_incident(data):
    """Get a specific incident by ID."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.VIEW_INCIDENTS):
            return
            
        if 'id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Incident ID is required'})
            return
            
        incident_id = data['id']
        incident = Incident.query.get(incident_id)
            
        if not incident:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Incident with ID {incident_id} not found'})
            return
            
        # Get detailed incident data including assigned units
        incident_data = incident.to_dict(include_units=True, include_logs=True)
            
        emit('incident_details', {'incident': incident_data})
            
    except Exception as e:
        logger.error(f"Error getting incident details: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('create_incident')
def handle_create_incident(data):
    """Create a new incident."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.CREATE_INCIDENTS):
            return
            
        # Validate required fields
        required_fields = ['incident_type_id', 'priority', 'location', 'description']
        if not all(field in data for field in required_fields):
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Missing required fields'})
            return
            
        # Create new incident
        incident = Incident(
            incident_type_id=data['incident_type_id'],
            priority=data['priority'],
            location=data['location'],
            description=data['description'],
            created_by_id=current_user.id,
            caller=data.get('caller'),
            callback_number=data.get('callback_number'),
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            location_id=data.get('location_id')
        )
            
        db.session.add(incident)
        db.session.commit()
            
        # Create initial log entry
        log_entry = IncidentLog(
            incident_id=incident.id,
            log_type='system',
            message='Incident created',
            created_by_id=current_user.id
        )
            
        db.session.add(log_entry)
        db.session.commit()
            
        # Create audit log
        create_audit_log(
            entity_type='incident',
            entity_id=incident.id,
            action='create',
            details=f"Created incident: #{incident.case_number} - {incident.description}"
        )
            
        # Get full incident data
        incident_data = incident.to_dict(include_units=False, include_logs=True)
            
        # Broadcast to all clients in incident_updates room
        socketio.emit('incident_created', {'incident': incident_data}, room='incident_updates')
            
        # Send response to the requesting client
        emit('incident_created_confirm', {'incident': incident_data, 'message': 'Incident created successfully'})
            
        # Send notifications to users with appropriate permissions
        from models import User, Role
        users_to_notify = User.query.join(Role).filter(
            Role.has_permission(Permission.RECEIVE_INCIDENT_NOTIFICATIONS)
        ).all()
            
        if users_to_notify:
            user_ids = [user.id for user in users_to_notify]
            incident_type = IncidentType.query.get(incident.incident_type_id)
            incident_type_name = incident_type.name if incident_type else "Unknown"
                
            NotificationService.create_bulk_notifications(
                user_ids=user_ids,
                title=f"New Incident #{incident.case_number}",
                message=f"New {incident.priority} priority {incident_type_name} incident at {incident.location}",
                notification_type='incident',
                reference_id=incident.id,
                reference_type='incident_created',
                broadcast=True,
                send_email=True
            )
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating incident: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('update_incident')
def handle_update_incident(data):
    """Update an existing incident."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.UPDATE_INCIDENTS):
            return
            
        if 'id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Incident ID is required'})
            return
            
        incident_id = data['id']
        incident = Incident.query.get(incident_id)
            
        if not incident:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Incident with ID {incident_id} not found'})
            return
            
        # Check what fields are being updated for audit trail
        updated_fields = []
            
        if 'incident_type_id' in data and data['incident_type_id'] != incident.incident_type_id:
            old_type = IncidentType.query.get(incident.incident_type_id)
            new_type = IncidentType.query.get(data['incident_type_id'])
            updated_fields.append(f"Type: {old_type.name if old_type else 'Unknown'} → {new_type.name if new_type else 'Unknown'}")
            incident.incident_type_id = data['incident_type_id']
            
        if 'priority' in data and data['priority'] != incident.priority:
            updated_fields.append(f"Priority: {incident.priority} → {data['priority']}")
            incident.priority = data['priority']
            
        if 'location' in data and data['location'] != incident.location:
            updated_fields.append(f"Location: {incident.location} → {data['location']}")
            incident.location = data['location']
            
        if 'description' in data and data['description'] != incident.description:
            updated_fields.append(f"Description updated")
            incident.description = data['description']
            
        if 'caller' in data and data['caller'] != incident.caller:
            updated_fields.append(f"Caller: {incident.caller or 'None'} → {data['caller'] or 'None'}")
            incident.caller = data['caller']
            
        if 'callback_number' in data and data['callback_number'] != incident.callback_number:
            updated_fields.append(f"Callback number updated")
            incident.callback_number = data['callback_number']
            
        if 'latitude' in data and data['latitude'] != incident.latitude:
            updated_fields.append(f"Coordinates updated")
            incident.latitude = data['latitude']
            
        if 'longitude' in data and data['longitude'] != incident.longitude:
            if 'latitude' not in updated_fields:
                updated_fields.append(f"Coordinates updated")
            incident.longitude = data['longitude']
            
        if 'location_id' in data and data['location_id'] != incident.location_id:
            updated_fields.append(f"Location ID updated")
            incident.location_id = data['location_id']
            
        if 'status' in data and data['status'] != incident.status:
            updated_fields.append(f"Status: {incident.status} → {data['status']}")
            incident.status = data['status']
            
        # Only update if there were changes
        if updated_fields:
            incident.updated_at = datetime.utcnow()
            incident.updated_by_id = current_user.id
                
            db.session.commit()
                
            # Create log entry for the update
            update_details = "; ".join(updated_fields)
            log_entry = IncidentLog(
                incident_id=incident.id,
                log_type='system',
                message=f"Incident updated: {update_details}",
                created_by_id=current_user.id
            )
                
            db.session.add(log_entry)
            db.session.commit()
                
            # Create audit log
            create_audit_log(
                entity_type='incident',
                entity_id=incident.id,
                action='update',
                details=f"Updated incident #{incident.case_number}: {update_details}"
            )
                
            # Get updated incident data
            incident_data = incident.to_dict(include_units=True, include_logs=True)
                
            # Broadcast to all clients in incident_updates room
            socketio.emit('incident_updated', {'incident': incident_data}, room='incident_updates')
                
            # Send response to the requesting client
            emit('incident_updated_confirm', {'incident': incident_data, 'message': 'Incident updated successfully'})
                
            # Send notifications to assigned units if status changed
            if 'status' in data and data['status'] != incident.status:
                # Get all units assigned to this incident
                assigned_units = Unit.query.filter_by(incident_id=incident.id).all()
                    
                if assigned_units:
                    # Get operators of these units
                    from models import User
                    user_ids = []
                    
                    for unit in assigned_units:
                        if unit.operator_id:
                            user_ids.append(unit.operator_id)
                    
                    if user_ids:
                        NotificationService.create_bulk_notifications(
                            user_ids=user_ids,
                            title=f"Incident #{incident.case_number} Status Changed",
                            message=f"Incident status changed to: {incident.status}",
                            notification_type='incident',
                            reference_id=incident.id,
                            reference_type='incident_status_changed',
                            broadcast=True,
                            send_email=True
                        )
        else:
            # No fields were updated
            emit('incident_updated_confirm', {
                'incident': incident.to_dict(include_units=True, include_logs=True),
                'message': 'No changes made to incident'
            })
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating incident: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('close_incident')
def handle_close_incident(data):
    """Close an incident."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.CLOSE_INCIDENTS):
            return
            
        if 'id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Incident ID is required'})
            return
            
        incident_id = data['id']
        incident = Incident.query.get(incident_id)
            
        if not incident:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Incident with ID {incident_id} not found'})
            return
            
        # Check if already closed
        if incident.status == 'closed':
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Incident is already closed'})
            return
            
        # Check if resolution is provided
        resolution = data.get('resolution', '')
        
        # Check if there are still assigned units
        assigned_units = Unit.query.filter_by(incident_id=incident.id).all()
        if assigned_units and not data.get('force_close', False):
            emit('error', {
                'message': 'VALIDATION_ERROR', 
                'details': 'Cannot close incident with assigned units. Clear units first or use force_close=true',
                'assigned_units': [unit.to_dict() for unit in assigned_units]
            })
            return
            
        # If force closing, clear all units
        if assigned_units and data.get('force_close', False):
            for unit in assigned_units:
                # Log that unit was auto-cleared
                log_entry = IncidentLog(
                    incident_id=incident.id,
                    log_type='system',
                    message=f"Unit {unit.name} auto-cleared due to incident closure",
                    created_by_id=current_user.id
                )
                db.session.add(log_entry)
                
                # Clear unit from incident
                unit.incident_id = None
                unit.status = 'available'
                unit.updated_at = datetime.utcnow()
                
                # Create audit log for unit
                create_audit_log(
                    entity_type='unit',
                    entity_id=unit.id,
                    action='clear',
                    details=f"Unit {unit.name} auto-cleared from incident #{incident.case_number} due to incident closure"
                )
            
        # Update incident
        incident.status = 'closed'
        incident.closed_at = datetime.utcnow()
        incident.closed_by_id = current_user.id
        incident.resolution = resolution
        incident.updated_at = datetime.utcnow()
        incident.updated_by_id = current_user.id
            
        db.session.commit()
            
        # Create log entry
        log_entry = IncidentLog(
            incident_id=incident.id,
            log_type='system',
            message=f"Incident closed. Resolution: {resolution}",
            created_by_id=current_user.id
        )
            
        db.session.add(log_entry)
        db.session.commit()
            
        # Create audit log
        create_audit_log(
            entity_type='incident',
            entity_id=incident.id,
            action='close',
            details=f"Closed incident #{incident.case_number}"
        )
            
        # Get updated incident data
        incident_data = incident.to_dict(include_units=True, include_logs=True)
            
        # Broadcast to all clients in incident_updates room
        socketio.emit('incident_closed', {'incident': incident_data}, room='incident_updates')
            
        # Send response to the requesting client
        emit('incident_closed_confirm', {'incident': incident_data, 'message': 'Incident closed successfully'})
            
        # Send notifications to users with appropriate permissions
        from models import User, Role
        users_to_notify = User.query.join(Role).filter(
            Role.has_permission(Permission.RECEIVE_INCIDENT_NOTIFICATIONS)
        ).all()
            
        if users_to_notify:
            user_ids = [user.id for user in users_to_notify]
            incident_type = IncidentType.query.get(incident.incident_type_id)
            incident_type_name = incident_type.name if incident_type else "Unknown"
                
            NotificationService.create_bulk_notifications(
                user_ids=user_ids,
                title=f"Incident #{incident.case_number} Closed",
                message=f"{incident.priority} priority {incident_type_name} incident at {incident.location} has been closed",
                notification_type='incident',
                reference_id=incident.id,
                reference_type='incident_closed',
                broadcast=True,
                send_email=True
            )
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error closing incident: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('add_incident_log')
def handle_add_incident_log(data):
    """Add a log entry to an incident."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.UPDATE_INCIDENTS):
            return
            
        # Validate required fields
        required_fields = ['incident_id', 'message']
        if not all(field in data for field in required_fields):
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Missing required fields'})
            return
            
        incident_id = data['incident_id']
        incident = Incident.query.get(incident_id)
            
        if not incident:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Incident with ID {incident_id} not found'})
            return
            
        # Create log entry
        log_entry = IncidentLog(
            incident_id=incident.id,
            log_type=data.get('log_type', 'user'),  # Default to user log if not specified
            message=data['message'],
            created_by_id=current_user.id
        )
            
        db.session.add(log_entry)
        db.session.commit()
            
        # Create audit log
        create_audit_log(
            entity_type='incident_log',
            entity_id=log_entry.id,
            action='create',
            details=f"Added log to incident #{incident.case_number}: {data['message'][:100]}"
        )
            
        # Get updated incident data with logs
        incident_data = incident.to_dict(include_logs=True)
            
        # Broadcast to all clients in incident_updates room
        socketio.emit('incident_log_added', {
            'incident_id': incident.id,
            'log': log_entry.to_dict(),
            'logs': incident_data['logs']
        }, room='incident_updates')
            
        # Send response to the requesting client
        emit('incident_log_added_confirm', {
            'log': log_entry.to_dict(),
            'message': 'Log entry added successfully'
        })
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding incident log: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('assign_unit')
def handle_assign_unit(data):
    """Assign a unit to an incident."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.ASSIGN_UNITS):
            return
            
        # Validate required fields
        required_fields = ['unit_id', 'incident_id']
        if not all(field in data for field in required_fields):
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Missing required fields'})
            return
            
        unit_id = data['unit_id']
        incident_id = data['incident_id']
            
        # Check if unit exists
        unit = Unit.query.get(unit_id)
        if not unit:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Unit with ID {unit_id} not found'})
            return
            
        # Check if incident exists
        incident = Incident.query.get(incident_id)
        if not incident:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Incident with ID {incident_id} not found'})
            return
            
        # Check if incident is closed
        if incident.status == 'closed':
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Cannot assign unit to closed incident'})
            return
            
        # Check if unit is already assigned to an incident
        if unit.incident_id is not None:
            emit('error', {
                'message': 'VALIDATION_ERROR', 
                'details': f'Unit {unit.name} is already assigned to incident #{Incident.query.get(unit.incident_id).case_number}'
            })
            return
            
        # Check if unit is available
        if unit.status != 'available' and not data.get('force_assign', False):
            emit('error', {
                'message': 'VALIDATION_ERROR',
                'details': f'Unit {unit.name} is not available (current status: {unit.status}). Use force_assign=true to override'
            })
            return
            
        # Assign unit to incident
        unit.incident_id = incident.id
        unit.status = 'assigned'
        unit.assigned_at = datetime.utcnow()
        unit.updated_at = datetime.utcnow()
            
        db.session.commit()
            
        # Create log entry for incident
        log_entry = IncidentLog(
            incident_id=incident.id,
            log_type='system',
            message=f"Unit {unit.name} assigned to incident",
            created_by_id=current_user.id
        )
            
        db.session.add(log_entry)
        db.session.commit()
            
        # Create audit log
        create_audit_log(
            entity_type='unit',
            entity_id=unit.id,
            action='assign',
            details=f"Unit {unit.name} assigned to incident #{incident.case_number}"
        )
            
        # Get updated data
        unit_data = unit.to_dict()
        incident_data = incident.to_dict(include_units=True, include_logs=True)
            
        # Broadcast to all clients in incident_updates room
        socketio.emit('unit_assigned', {
            'unit': unit_data,
            'incident': incident_data
        }, room='incident_updates')
            
        # Also broadcast to unit_updates room
        socketio.emit('unit_status_changed', {
            'unit': unit_data,
            'previous_status': 'available',
            'new_status': 'assigned'
        }, room='unit_updates')
            
        # Send response to the requesting client
        emit('unit_assigned_confirm', {
            'unit': unit_data,
            'incident': incident_data,
            'message': f'Unit {unit.name} assigned to incident #{incident.case_number}'
        })
            
        # Notify unit operator if one is assigned
        if unit.operator_id:
            NotificationService.create_notification(
                user_id=unit.operator_id,
                title=f"Unit {unit.name} Assigned",
                message=f"Your unit has been assigned to incident #{incident.case_number} at {incident.location}",
                notification_type='unit',
                reference_id=unit.id,
                reference_type='unit_assigned',
                broadcast=True,
                send_email=True
            )
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error assigning unit: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('clear_unit')
def handle_clear_unit(data):
    """Clear a unit from an incident."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.ASSIGN_UNITS):
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
            
        # Check if unit is assigned to an incident
        if unit.incident_id is None:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': f'Unit {unit.name} is not assigned to any incident'})
            return
            
        # Get incident before clearing for notifications
        incident = Incident.query.get(unit.incident_id)
        if not incident:
            # This shouldn't happen, but handle it gracefully
            emit('error', {'message': 'NOT_FOUND', 'details': f'Incident associated with unit {unit.name} not found'})
            return
            
        incident_id = incident.id
        case_number = incident.case_number
            
        # Clear unit from incident
        unit.incident_id = None
        unit.status = 'available'
        unit.updated_at = datetime.utcnow()
            
        db.session.commit()
            
        # Create log entry for incident
        log_entry = IncidentLog(
            incident_id=incident.id,
            log_type='system',
            message=f"Unit {unit.name} cleared from incident",
            created_by_id=current_user.id
        )
            
        db.session.add(log_entry)
        db.session.commit()
            
        # Create audit log
        create_audit_log(
            entity_type='unit',
            entity_id=unit.id,
            action='clear',
            details=f"Unit {unit.name} cleared from incident #{case_number}"
        )
            
        # Get updated data
        unit_data = unit.to_dict()
        incident_data = incident.to_dict(include_units=True, include_logs=True)
            
        # Broadcast to all clients in incident_updates room
        socketio.emit('unit_cleared', {
            'unit': unit_data,
            'incident': incident_data
        }, room='incident_updates')
            
        # Also broadcast to unit_updates room
        socketio.emit('unit_status_changed', {
            'unit': unit_data,
            'previous_status': 'assigned',
            'new_status': 'available'
        }, room='unit_updates')
            
        # Send response to the requesting client
        emit('unit_cleared_confirm', {
            'unit': unit_data,
            'incident': incident_data,
            'message': f'Unit {unit.name} cleared from incident #{case_number}'
        })
            
        # Notify unit operator if one is assigned
        if unit.operator_id:
            NotificationService.create_notification(
                user_id=unit.operator_id,
                title=f"Unit {unit.name} Cleared",
                message=f"Your unit has been cleared from incident #{case_number}",
                notification_type='unit',
                reference_id=unit.id,
                reference_type='unit_cleared',
                broadcast=True,
                send_email=True
            )
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error clearing unit: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})
