"""
Location WebSocket Events

This module contains WebSocket event handlers for location-related operations including:
- Location updates
- Pickup point updates
- Geocoding operations
- Location search broadcasting
"""

from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room
from models import Location, PickupPoint, Permission
from extensions import db, socketio
from datetime import datetime
import logging
from services.connection_manager import ConnectionManager
from services.notification_service import NotificationService
from utils.validation import validate_coordinates
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

@socketio.on('join_location_updates')
def handle_join_location_updates():
    """Join the location updates room to receive real-time location updates."""
    try:
        if not check_auth():
            return
        
        client_id = request.sid
        join_room('location_updates')
        ConnectionManager.add_to_room(client_id, 'location_updates')
        
        emit('room_joined', {'room': 'location_updates'})
        logger.debug(f"Client {client_id} joined location_updates room")
        
    except Exception as e:
        logger.error(f"Error joining location_updates room: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('leave_location_updates')
def handle_leave_location_updates():
    """Leave the location updates room."""
    try:
        if not check_auth():
            return
        
        client_id = request.sid
        leave_room('location_updates')
        ConnectionManager.remove_from_room(client_id, 'location_updates')
        
        emit('room_left', {'room': 'location_updates'})
        logger.debug(f"Client {client_id} left location_updates room")
        
    except Exception as e:
        logger.error(f"Error leaving location_updates room: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_locations')
def handle_get_locations(data=None):
    """Get all locations with optional filtering."""
    try:
        if not check_auth():
            return
        
        if not check_permission(Permission.VIEW_LOCATIONS):
            return
            
        query = Location.query
        
        # Apply filters if provided
        if data:
            # Filter by active status
            if 'active_only' in data and data['active_only']:
                query = query.filter_by(is_active=True)
                
            # Filter by name
            if 'name' in data and data['name']:
                query = query.filter(Location.name.ilike(f"%{data['name']}%"))
                
            # Filter by type
            if 'location_type' in data and data['location_type']:
                query = query.filter_by(location_type=data['location_type'])
        
        # Get query results
        locations = query.all()
        
        # Convert to dictionary format for JSON response
        result = [location.to_dict() for location in locations]
        
        emit('locations_list', {'locations': result, 'count': len(result)})
        
    except Exception as e:
        logger.error(f"Error getting locations: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_location')
def handle_get_location(data):
    """Get a specific location by ID."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.VIEW_LOCATIONS):
            return
            
        if 'id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Location ID is required'})
            return
            
        location_id = data['id']
        location = Location.query.get(location_id)
        
        if not location:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Location with ID {location_id} not found'})
            return
            
        emit('location_details', {'location': location.to_dict()})
        
    except Exception as e:
        logger.error(f"Error getting location details: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('create_location')
def handle_create_location(data):
    """Create a new location."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.MANAGE_LOCATIONS):
            return
            
        # Validate required fields
        required_fields = ['name', 'address', 'location_type']
        if not all(field in data for field in required_fields):
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Missing required fields'})
            return
            
        # Validate coordinates if provided
        if 'latitude' in data and 'longitude' in data:
            lat = data.get('latitude')
            lng = data.get('longitude')
            if lat is not None and lng is not None:
                validation_result = validate_coordinates(lat, lng)
                if not validation_result['valid']:
                    emit('error', {'message': 'VALIDATION_ERROR', 'details': validation_result['message']})
                    return
        
        # Create new location
        new_location = Location(
            name=data['name'],
            address=data['address'],
            location_type=data['location_type'],
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            is_active=data.get('is_active', True),
            notes=data.get('notes'),
            phone=data.get('phone'),
            created_by_id=current_user.id
        )
        
        db.session.add(new_location)
        db.session.commit()
        
        # Create audit log
        create_audit_log(
            entity_type='location',
            entity_id=new_location.id,
            action='create',
            details=f"Created location: {new_location.name}"
        )
        
        # Broadcast to all clients in location_updates room
        socketio.emit('location_created', {'location': new_location.to_dict()}, room='location_updates')
        
        # Send response to the requesting client
        emit('location_created_confirm', {'location': new_location.to_dict(), 'message': 'Location created successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating location: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('update_location')
def handle_update_location(data):
    """Update an existing location."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.MANAGE_LOCATIONS):
            return
            
        if 'id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Location ID is required'})
            return
            
        location_id = data['id']
        location = Location.query.get(location_id)
        
        if not location:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Location with ID {location_id} not found'})
            return
            
        # Validate coordinates if provided
        if 'latitude' in data and 'longitude' in data:
            lat = data.get('latitude')
            lng = data.get('longitude')
            if lat is not None and lng is not None:
                validation_result = validate_coordinates(lat, lng)
                if not validation_result['valid']:
                    emit('error', {'message': 'VALIDATION_ERROR', 'details': validation_result['message']})
                    return
        
        # Update fields
        if 'name' in data:
            location.name = data['name']
        if 'address' in data:
            location.address = data['address']
        if 'location_type' in data:
            location.location_type = data['location_type']
        if 'latitude' in data:
            location.latitude = data['latitude']
        if 'longitude' in data:
            location.longitude = data['longitude']
        if 'is_active' in data:
            location.is_active = data['is_active']
        if 'notes' in data:
            location.notes = data['notes']
        if 'phone' in data:
            location.phone = data['phone']
            
        location.updated_at = datetime.utcnow()
        location.updated_by_id = current_user.id
        
        db.session.commit()
        
        # Create audit log
        create_audit_log(
            entity_type='location',
            entity_id=location.id,
            action='update',
            details=f"Updated location: {location.name}"
        )
        
        # Broadcast to all clients in location_updates room
        socketio.emit('location_updated', {'location': location.to_dict()}, room='location_updates')
        
        # Send response to the requesting client
        emit('location_updated_confirm', {'location': location.to_dict(), 'message': 'Location updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating location: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('delete_location')
def handle_delete_location(data):
    """Delete a location."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.MANAGE_LOCATIONS):
            return
            
        if 'id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Location ID is required'})
            return
            
        location_id = data['id']
        location = Location.query.get(location_id)
        
        if not location:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Location with ID {location_id} not found'})
            return
            
        # Store name for audit log
        location_name = location.name
        
        # Delete the location
        db.session.delete(location)
        db.session.commit()
        
        # Create audit log
        create_audit_log(
            entity_type='location',
            entity_id=location_id,
            action='delete',
            details=f"Deleted location: {location_name}"
        )
        
        # Broadcast to all clients in location_updates room
        socketio.emit('location_deleted', {'id': location_id, 'name': location_name}, room='location_updates')
        
        # Send response to the requesting client
        emit('location_deleted_confirm', {'id': location_id, 'message': 'Location deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting location: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_pickup_points')
def handle_get_pickup_points(data=None):
    """Get all pickup points with optional filtering."""
    try:
        if not check_auth():
            return
        
        if not check_permission(Permission.VIEW_LOCATIONS):
            return
            
        query = PickupPoint.query
        
        # Apply filters if provided
        if data:
            # Filter by active status
            if 'active_only' in data and data['active_only']:
                query = query.filter_by(is_active=True)
                
            # Filter by name
            if 'name' in data and data['name']:
                query = query.filter(PickupPoint.name.ilike(f"%{data['name']}%"))
                
            # Filter by location
            if 'location_id' in data and data['location_id']:
                query = query.filter_by(location_id=data['location_id'])
        
        # Get query results
        pickup_points = query.all()
        
        # Convert to dictionary format for JSON response
        result = [point.to_dict() for point in pickup_points]
        
        emit('pickup_points_list', {'pickup_points': result, 'count': len(result)})
        
    except Exception as e:
        logger.error(f"Error getting pickup points: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('get_pickup_point')
def handle_get_pickup_point(data):
    """Get a specific pickup point by ID."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.VIEW_LOCATIONS):
            return
            
        if 'id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Pickup point ID is required'})
            return
            
        pickup_point_id = data['id']
        pickup_point = PickupPoint.query.get(pickup_point_id)
        
        if not pickup_point:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Pickup point with ID {pickup_point_id} not found'})
            return
            
        emit('pickup_point_details', {'pickup_point': pickup_point.to_dict()})
        
    except Exception as e:
        logger.error(f"Error getting pickup point details: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('create_pickup_point')
def handle_create_pickup_point(data):
    """Create a new pickup point."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.MANAGE_LOCATIONS):
            return
            
        # Validate required fields
        required_fields = ['name', 'description', 'location_id']
        if not all(field in data for field in required_fields):
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Missing required fields'})
            return
            
        # Validate location exists
        location = Location.query.get(data['location_id'])
        if not location:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': f"Location with ID {data['location_id']} not found"})
            return
            
        # Validate coordinates if provided
        if 'latitude' in data and 'longitude' in data:
            lat = data.get('latitude')
            lng = data.get('longitude')
            if lat is not None and lng is not None:
                validation_result = validate_coordinates(lat, lng)
                if not validation_result['valid']:
                    emit('error', {'message': 'VALIDATION_ERROR', 'details': validation_result['message']})
                    return
        
        # Create new pickup point
        new_pickup_point = PickupPoint(
            name=data['name'],
            description=data['description'],
            location_id=data['location_id'],
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            is_active=data.get('is_active', True),
            notes=data.get('notes'),
            created_by_id=current_user.id
        )
        
        db.session.add(new_pickup_point)
        db.session.commit()
        
        # Create audit log
        create_audit_log(
            entity_type='pickup_point',
            entity_id=new_pickup_point.id,
            action='create',
            details=f"Created pickup point: {new_pickup_point.name} for location: {location.name}"
        )
        
        # Broadcast to all clients in location_updates room
        socketio.emit('pickup_point_created', {'pickup_point': new_pickup_point.to_dict()}, room='location_updates')
        
        # Send response to the requesting client
        emit('pickup_point_created_confirm', {'pickup_point': new_pickup_point.to_dict(), 'message': 'Pickup point created successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating pickup point: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('update_pickup_point')
def handle_update_pickup_point(data):
    """Update an existing pickup point."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.MANAGE_LOCATIONS):
            return
            
        if 'id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Pickup point ID is required'})
            return
            
        pickup_point_id = data['id']
        pickup_point = PickupPoint.query.get(pickup_point_id)
        
        if not pickup_point:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Pickup point with ID {pickup_point_id} not found'})
            return
            
        # Validate location exists if changing it
        if 'location_id' in data:
            location = Location.query.get(data['location_id'])
            if not location:
                emit('error', {'message': 'VALIDATION_ERROR', 'details': f"Location with ID {data['location_id']} not found"})
                return
            
        # Validate coordinates if provided
        if 'latitude' in data and 'longitude' in data:
            lat = data.get('latitude')
            lng = data.get('longitude')
            if lat is not None and lng is not None:
                validation_result = validate_coordinates(lat, lng)
                if not validation_result['valid']:
                    emit('error', {'message': 'VALIDATION_ERROR', 'details': validation_result['message']})
                    return
        
        # Update fields
        if 'name' in data:
            pickup_point.name = data['name']
        if 'description' in data:
            pickup_point.description = data['description']
        if 'location_id' in data:
            pickup_point.location_id = data['location_id']
        if 'latitude' in data:
            pickup_point.latitude = data['latitude']
        if 'longitude' in data:
            pickup_point.longitude = data['longitude']
        if 'is_active' in data:
            pickup_point.is_active = data['is_active']
        if 'notes' in data:
            pickup_point.notes = data['notes']
            
        pickup_point.updated_at = datetime.utcnow()
        pickup_point.updated_by_id = current_user.id
        
        db.session.commit()
        
        # Create audit log
        create_audit_log(
            entity_type='pickup_point',
            entity_id=pickup_point.id,
            action='update',
            details=f"Updated pickup point: {pickup_point.name}"
        )
        
        # Broadcast to all clients in location_updates room
        socketio.emit('pickup_point_updated', {'pickup_point': pickup_point.to_dict()}, room='location_updates')
        
        # Send response to the requesting client
        emit('pickup_point_updated_confirm', {'pickup_point': pickup_point.to_dict(), 'message': 'Pickup point updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating pickup point: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('delete_pickup_point')
def handle_delete_pickup_point(data):
    """Delete a pickup point."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.MANAGE_LOCATIONS):
            return
            
        if 'id' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Pickup point ID is required'})
            return
            
        pickup_point_id = data['id']
        pickup_point = PickupPoint.query.get(pickup_point_id)
        
        if not pickup_point:
            emit('error', {'message': 'NOT_FOUND', 'details': f'Pickup point with ID {pickup_point_id} not found'})
            return
            
        # Store name for audit log
        pickup_point_name = pickup_point.name
        
        # Delete the pickup point
        db.session.delete(pickup_point)
        db.session.commit()
        
        # Create audit log
        create_audit_log(
            entity_type='pickup_point',
            entity_id=pickup_point_id,
            action='delete',
            details=f"Deleted pickup point: {pickup_point_name}"
        )
        
        # Broadcast to all clients in location_updates room
        socketio.emit('pickup_point_deleted', {'id': pickup_point_id, 'name': pickup_point_name}, room='location_updates')
        
        # Send response to the requesting client
        emit('pickup_point_deleted_confirm', {'id': pickup_point_id, 'message': 'Pickup point deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting pickup point: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('geocode_address')
def handle_geocode_address(data):
    """Geocode an address to get coordinates."""
    try:
        if not check_auth():
            return
            
        if 'address' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Address is required'})
            return
            
        address = data['address']
        
        # Mock implementation - in real world, this would call an external geocoding service
        # For testing, generate plausible coordinates
        import hashlib
        import struct
        
        # Generate deterministic but random-looking coordinates based on address hash
        hash_obj = hashlib.md5(address.encode())
        hash_bytes = hash_obj.digest()
        
        # Use the hash to create coordinates
        lat_offset = struct.unpack('f', hash_bytes[0:4])[0] % 0.2
        lng_offset = struct.unpack('f', hash_bytes[4:8])[0] % 0.2
        
        # Base coordinates - central London
        base_lat = 51.5074
        base_lng = -0.1278
        
        # Add small offset to base coordinates
        latitude = base_lat + lat_offset
        longitude = base_lng + lng_offset
        
        # Response with geocoded coordinates
        emit('geocode_result', {
            'address': address,
            'latitude': latitude,
            'longitude': longitude,
            'accuracy': 'high',  # mock accuracy rating
            'source': 'mock-geocoder'
        })
        
    except Exception as e:
        logger.error(f"Error geocoding address: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('reverse_geocode')
def handle_reverse_geocode(data):
    """Reverse geocode coordinates to get address."""
    try:
        if not check_auth():
            return
            
        # Validate required fields
        if 'latitude' not in data or 'longitude' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Latitude and longitude are required'})
            return
            
        latitude = data['latitude']
        longitude = data['longitude']
        
        # Validate coordinates
        validation_result = validate_coordinates(latitude, longitude)
        if not validation_result['valid']:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': validation_result['message']})
            return
            
        # Mock implementation - in real world, this would call an external reverse geocoding service
        # For testing, generate a plausible address based on coordinates
        
        # Function to generate street name from coordinates
        def generate_street_name(lat, lng):
            import hashlib
            
            # Create a deterministic hash from coordinates
            hash_input = f"{lat},{lng}".encode()
            hash_obj = hashlib.md5(hash_input)
            hash_hex = hash_obj.hexdigest()
            
            # Street name prefixes and suffixes
            prefixes = ['North', 'South', 'East', 'West', 'Upper', 'Lower', 'Old', 'New']
            names = ['Park', 'Oak', 'Pine', 'Maple', 'Cedar', 'Elm', 'Main', 'High', 'Center']
            suffixes = ['Street', 'Road', 'Avenue', 'Lane', 'Drive', 'Boulevard', 'Way', 'Place']
            
            # Use hash to select street name components
            prefix_idx = int(hash_hex[0:2], 16) % len(prefixes)
            name_idx = int(hash_hex[2:4], 16) % len(names)
            suffix_idx = int(hash_hex[4:6], 16) % len(suffixes)
            
            # Generate street number (1-999)
            street_num = 1 + (int(hash_hex[6:9], 16) % 999)
            
            return f"{street_num} {prefixes[prefix_idx]} {names[name_idx]} {suffixes[suffix_idx]}"
        
        # Generate mock address
        street = generate_street_name(latitude, longitude)
        city = "London"  # Mock city
        postal_code = "SW1A 1AA"  # Mock postal code
        
        full_address = f"{street}, {city}, {postal_code}"
        
        # Response with reverse geocoded address
        emit('reverse_geocode_result', {
            'latitude': latitude,
            'longitude': longitude,
            'address': full_address,
            'street': street,
            'city': city,
            'postal_code': postal_code,
            'accuracy': 'high',  # mock accuracy rating
            'source': 'mock-geocoder'
        })
        
    except Exception as e:
        logger.error(f"Error reverse geocoding: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})

@socketio.on('search_locations')
def handle_search_locations(data):
    """Search for locations by name, address, or coordinates."""
    try:
        if not check_auth():
            return
            
        if not check_permission(Permission.VIEW_LOCATIONS):
            return
            
        if 'query' not in data:
            emit('error', {'message': 'VALIDATION_ERROR', 'details': 'Search query is required'})
            return
            
        query_string = data['query']
        search_type = data.get('type', 'all')  # all, locations, pickup_points
        
        results = {
            'locations': [],
            'pickup_points': [],
            'count': 0
        }
        
        # Search locations if requested
        if search_type in ['all', 'locations']:
            location_query = Location.query.filter(
                Location.name.ilike(f"%{query_string}%") | 
                Location.address.ilike(f"%{query_string}%")
            )
            
            # Apply active filter if specified
            if 'active_only' in data and data['active_only']:
                location_query = location_query.filter_by(is_active=True)
                
            locations = location_query.limit(50).all()
            results['locations'] = [location.to_dict() for location in locations]
            
        # Search pickup points if requested
        if search_type in ['all', 'pickup_points']:
            pickup_query = PickupPoint.query.filter(
                PickupPoint.name.ilike(f"%{query_string}%") | 
                PickupPoint.description.ilike(f"%{query_string}%")
            )
            
            # Apply active filter if specified
            if 'active_only' in data and data['active_only']:
                pickup_query = pickup_query.filter_by(is_active=True)
                
            pickup_points = pickup_query.limit(50).all()
            results['pickup_points'] = [point.to_dict() for point in pickup_points]
            
        # Calculate total count
        results['count'] = len(results['locations']) + len(results['pickup_points'])
        
        emit('search_results', results)
        
    except Exception as e:
        logger.error(f"Error searching locations: {str(e)}")
        emit('error', {'message': 'SERVER_ERROR', 'details': str(e)})
