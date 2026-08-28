from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import Location, PickupPoint, APIKey, Incident, IncidentType, Notification, NotificationPreference, Permission, AMPDSProtocol
from extensions import db, csrf, socketio
from utils.validation import validate_json_payload
from utils.decorators import role_required, rate_limit, read_endpoint, permission_required
from utils.security import secure_endpoint
from utils.logging import log_activity
from datetime import datetime, timedelta
from sqlalchemy import desc, and_, or_
from blueprints.admin import admin_required
import logging

# Create the blueprint for the API
api = Blueprint('api', __name__)

# ===== Client Logging Endpoint (Public) =====

@api.route('/client-logs', methods=['POST'])
@csrf.exempt
@read_endpoint(limit="240/minute")
def client_logs():
    """Accept client-side logs without requiring authentication.
    This prevents noisy 401s during early page loads and allows front-end to report errors.
    """
    try:
        payload = request.get_json(silent=True) or {}
        log_type = payload.get('type', 'CLIENT')
        level = (payload.get('level') or 'info').upper()
        message = payload.get('message') or 'client log'
        context = payload.get('context') or payload

        logger = current_app.logger.getChild('client')
        if level == 'ERROR':
            logger.error(f"[{log_type}] {message}", extra={'context': context})
        elif level == 'WARNING' or level == 'WARN':
            logger.warning(f"[{log_type}] {message}", extra={'context': context})
        else:
            logger.info(f"[{log_type}] {message}", extra={'context': context})

        return jsonify({'success': True}), 200
    except Exception as e:
        current_app.logger.error(f"Error handling client log: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to record log'}), 500

# ===== Location Services API Endpoints =====

@api.route('/locations', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def get_all_locations():
    """Get all locations with optional filtering."""
    try:
        # Check if we should filter active only
        active_only = request.args.get('active', 'true').lower() == 'true'
        query = Location.query
        
        if active_only:
            query = query.filter_by(active=True)
            
        # Filter by name search term if provided
        search_term = request.args.get('search', '')
        if search_term:
            query = query.filter(Location.name.ilike(f'%{search_term}%'))
            
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)  # Limit max per_page
        
        # Execute paginated query
        pagination = query.order_by(Location.name).paginate(page=page, per_page=per_page)
        locations = pagination.items
        
        # Convert to dictionary
        locations_dict = [loc.to_dict() for loc in locations]
        
        return jsonify({
            'success': True,
            'count': len(locations_dict),
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
            'locations': locations_dict
        })
    except Exception as e:
        current_app.logger.error(f"Error getting locations: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting locations: {str(e)}'}), 500

@api.route('/locations/<int:location_id>', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def get_location(location_id):
    """Get a specific location by ID."""
    try:
        location = Location.query.get(location_id)
        
        if not location:
            return jsonify({'success': False, 'message': 'Location not found'}), 404
            
        return jsonify({
            'success': True,
            'location': location.to_dict()
        })
    except Exception as e:
        current_app.logger.error(f"Error getting location: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting location: {str(e)}'}), 500

@api.route('/locations/search', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def search_locations():
    """Search for locations by name or proximity."""
    try:
        # Get search parameters
        search_term = request.args.get('q', '')
        latitude = request.args.get('lat', type=float)
        longitude = request.args.get('lng', type=float)
        max_distance = request.args.get('distance', 10, type=float)  # default 10km radius
        
        # If coordinates are provided, search by proximity
        if latitude is not None and longitude is not None:
            locations = Location.query.filter_by(active=True).all()
            
            # Filter and sort by distance
            filtered_locations = []
            for location in locations:
                distance = GeospatialService.calculate_distance(
                    latitude, longitude, location.latitude, location.longitude
                )
                if distance <= max_distance:
                    loc_dict = location.to_dict()
                    loc_dict['distance'] = round(distance, 2)
                    filtered_locations.append(loc_dict)
                    
            # Sort by distance
            filtered_locations.sort(key=lambda x: x['distance'])
            
            return jsonify({
                'success': True,
                'count': len(filtered_locations),
                'locations': filtered_locations
            })
        
        # Otherwise, search by name
        elif search_term:
            locations = Location.search(search_term)
            locations_dict = [loc.to_dict() for loc in locations]
            
            return jsonify({
                'success': True,
                'count': len(locations_dict),
                'locations': locations_dict
            })
        else:
            return jsonify({
                'success': False, 
                'message': 'Please provide either search term or coordinates'
            }), 400
            
    except Exception as e:
        current_app.logger.error(f"Error searching locations: {str(e)}")
        return jsonify({'success': False, 'message': f'Error searching locations: {str(e)}'}), 500

@api.route('/locations', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_GEOSPATIAL)
@secure_endpoint(limit="60/minute")
def create_location():
    """Create a new location."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'latitude', 'longitude']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
                
        # Check if location with same name already exists
        existing = Location.query.filter_by(name=data['name']).first()
        if existing:
            return jsonify({
                'success': False, 
                'message': f'Location with name "{data["name"]}" already exists'
            }), 409
            
        # Create new location
        location = Location(
            name=data['name'],
            latitude=data['latitude'],
            longitude=data['longitude'],
            active=data.get('active', True)
        )
        
        # Save to database
        db.session.add(location)
        db.session.commit()
        
        # Add log entry
        log_entry = AuditLog(
            category='Location Management',
            action='Create Location',
            severity='INFO',
            user_id=current_user.id,
            resource_type='Location',
            resource_id=str(location.id),
            details=f"Location '{location.name}' created"
        )
        db.session.add(log_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Location created successfully',
            'location': location.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating location: {str(e)}")
        return jsonify({'success': False, 'message': f'Error creating location: {str(e)}'}), 500

@api.route('/locations/<int:location_id>', methods=['PUT'])
@login_required
@permission_required(Permission.MANAGE_GEOSPATIAL)
@secure_endpoint(limit="60/minute")
def update_location(location_id):
    """Update an existing location."""
    try:
        location = Location.query.get(location_id)
        
        if not location:
            return jsonify({'success': False, 'message': 'Location not found'}), 404
            
        data = request.get_json()
        
        # Check name uniqueness if name is being changed
        if 'name' in data and data['name'] != location.name:
            existing = Location.query.filter_by(name=data['name']).first()
            if existing:
                return jsonify({
                    'success': False, 
                    'message': f'Location with name "{data["name"]}" already exists'
                }), 409
        
        # Update fields
        if 'name' in data:
            location.name = data['name']
            
        if 'latitude' in data:
            location.latitude = data['latitude']
            
        if 'longitude' in data:
            location.longitude = data['longitude']
            
        if 'active' in data:
            location.active = data['active']
            
        location.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Add log entry
        log_entry = AuditLog(
            category='Location Management',
            action='Update Location',
            severity='INFO',
            user_id=current_user.id,
            resource_type='Location',
            resource_id=str(location.id),
            details=f"Location '{location.name}' updated"
        )
        db.session.add(log_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Location updated successfully',
            'location': location.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating location: {str(e)}")
        return jsonify({'success': False, 'message': f'Error updating location: {str(e)}'}), 500

@api.route('/locations/<int:location_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.ADMIN)  # Only admins can delete locations
@secure_endpoint(limit="30/minute")
def delete_location(location_id):
    """Delete a location."""
    try:
        location = Location.query.get(location_id)
        
        if not location:
            return jsonify({'success': False, 'message': 'Location not found'}), 404
            
        # Check if location is used by any units
        if location.units and location.units.count() > 0:
            # Instead of deleting, just mark as inactive
            location.active = False
            db.session.commit()
            
            # Add log entry
            log_entry = AuditLog(
                category='Location Management',
                action='Deactivate Location',
                severity='WARNING',
                user_id=current_user.id,
                resource_type='Location',
                resource_id=str(location.id),
                details=f"Location '{location.name}' deactivated (has units assigned)"
            )
            db.session.add(log_entry)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Location "{location.name}" has units assigned and cannot be deleted. It has been deactivated instead.'
            })
        
        # Store name for logging
        location_name = location.name
        
        # Delete the location
        db.session.delete(location)
        db.session.commit()
        
        # Add log entry
        log_entry = AuditLog(
            category='Location Management',
            action='Delete Location',
            severity='WARNING',
            user_id=current_user.id,
            resource_type='Location',
            resource_id=str(location_id),
            details=f"Location '{location_name}' deleted"
        )
        db.session.add(log_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Location "{location_name}" deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting location: {str(e)}")
        return jsonify({'success': False, 'message': f'Error deleting location: {str(e)}'}), 500

@api.route('/pickup-points', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def get_all_pickup_points():
    """Get all pickup points with optional filtering."""
    try:
        # Check if we should filter active only
        active_only = request.args.get('active', 'true').lower() == 'true'
        query = PickupPoint.query
        
        if active_only:
            query = query.filter_by(active=True)
            
        # Filter by name search term if provided
        search_term = request.args.get('search', '')
        if search_term:
            query = query.filter(PickupPoint.name.ilike(f'%{search_term}%'))
            
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)  # Limit max per_page
        
        # Execute paginated query
        pagination = query.order_by(PickupPoint.name).paginate(page=page, per_page=per_page)
        points = pagination.items
        
        # Convert to dictionary
        points_dict = [point.to_dict() for point in points]
        
        return jsonify({
            'success': True,
            'count': len(points_dict),
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
            'pickup_points': points_dict
        })
    except Exception as e:
        current_app.logger.error(f"Error getting pickup points: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting pickup points: {str(e)}'}), 500

@api.route('/pickup-points/<int:point_id>', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def get_pickup_point(point_id):
    """Get a specific pickup point by ID."""
    try:
        point = PickupPoint.query.get(point_id)
        
        if not point:
            return jsonify({'success': False, 'message': 'Pickup point not found'}), 404
            
        return jsonify({
            'success': True,
            'pickup_point': point.to_dict()
        })
    except Exception as e:
        current_app.logger.error(f"Error getting pickup point: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting pickup point: {str(e)}'}), 500

@api.route('/pickup-points/search', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def search_pickup_points():
    """Search for pickup points by name or proximity."""
    try:
        # Get search parameters
        search_term = request.args.get('q', '')
        latitude = request.args.get('lat', type=float)
        longitude = request.args.get('lng', type=float)
        max_distance = request.args.get('distance', 10, type=float)  # default 10km radius
        
        # If coordinates are provided, search by proximity
        if latitude is not None and longitude is not None:
            points = PickupPoint.query.filter_by(active=True).all()
            
            # Filter and sort by distance
            filtered_points = []
            for point in points:
                distance = GeospatialService.calculate_distance(
                    latitude, longitude, point.latitude, point.longitude
                )
                if distance <= max_distance:
                    point_dict = point.to_dict()
                    point_dict['distance'] = round(distance, 2)
                    filtered_points.append(point_dict)
                    
            # Sort by distance
            filtered_points.sort(key=lambda x: x['distance'])
            
            return jsonify({
                'success': True,
                'count': len(filtered_points),
                'pickup_points': filtered_points
            })
        
        # Otherwise, search by name
        elif search_term:
            points = PickupPoint.query.filter(
                PickupPoint.name.ilike(f'%{search_term}%'),
                PickupPoint.active == True
            ).all()
            
            points_dict = [point.to_dict() for point in points]
            
            return jsonify({
                'success': True,
                'count': len(points_dict),
                'pickup_points': points_dict
            })
        else:
            return jsonify({
                'success': False, 
                'message': 'Please provide either search term or coordinates'
            }), 400
            
    except Exception as e:
        current_app.logger.error(f"Error searching pickup points: {str(e)}")
        return jsonify({'success': False, 'message': f'Error searching pickup points: {str(e)}'}), 500

@api.route('/pickup-points', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_GEOSPATIAL)
@secure_endpoint(limit="60/minute")
def create_pickup_point():
    """Create a new pickup point."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'location', 'latitude', 'longitude']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
                
        # Check if pickup point with same name already exists
        existing = PickupPoint.query.filter_by(name=data['name']).first()
        if existing:
            return jsonify({
                'success': False, 
                'message': f'Pickup point with name "{data["name"]}" already exists'
            }), 409
            
        # Create new pickup point
        point = PickupPoint(
            name=data['name'],
            location=data['location'],
            latitude=data['latitude'],
            longitude=data['longitude'],
            description=data.get('description', ''),
            active=data.get('active', True)
        )
        
        # Save to database
        db.session.add(point)
        db.session.commit()
        
        # Add log entry
        log_entry = AuditLog(
            category='Location Management',
            action='Create Pickup Point',
            severity='INFO',
            user_id=current_user.id,
            resource_type='PickupPoint',
            resource_id=str(point.id),
            details=f"Pickup point '{point.name}' created"
        )
        db.session.add(log_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Pickup point created successfully',
            'pickup_point': point.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating pickup point: {str(e)}")
        return jsonify({'success': False, 'message': f'Error creating pickup point: {str(e)}'}), 500

@api.route('/pickup-points/<int:point_id>', methods=['PUT'])
@login_required
@permission_required(Permission.MANAGE_GEOSPATIAL)
@secure_endpoint(limit="60/minute")
def update_pickup_point(point_id):
    """Update an existing pickup point."""
    try:
        point = PickupPoint.query.get(point_id)
        
        if not point:
            return jsonify({'success': False, 'message': 'Pickup point not found'}), 404
            
        data = request.get_json()
        
        # Check name uniqueness if name is being changed
        if 'name' in data and data['name'] != point.name:
            existing = PickupPoint.query.filter_by(name=data['name']).first()
            if existing:
                return jsonify({
                    'success': False, 
                    'message': f'Pickup point with name "{data["name"]}" already exists'
                }), 409
        
        # Update fields
        if 'name' in data:
            point.name = data['name']
            
        if 'location' in data:
            point.location = data['location']
            
        if 'latitude' in data:
            point.latitude = data['latitude']
            
        if 'longitude' in data:
            point.longitude = data['longitude']
            
        if 'description' in data:
            point.description = data['description']
            
        if 'active' in data:
            point.active = data['active']
            
        point.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Add log entry
        log_entry = AuditLog(
            category='Location Management',
            action='Update Pickup Point',
            severity='INFO',
            user_id=current_user.id,
            resource_type='PickupPoint',
            resource_id=str(point.id),
            details=f"Pickup point '{point.name}' updated"
        )
        db.session.add(log_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Pickup point updated successfully',
            'pickup_point': point.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating pickup point: {str(e)}")
        return jsonify({'success': False, 'message': f'Error updating pickup point: {str(e)}'}), 500

@api.route('/pickup-points/<int:point_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.ADMIN)  # Only admins can delete pickup points
@secure_endpoint(limit="30/minute")
def delete_pickup_point(point_id):
    """Delete a pickup point."""
    try:
        point = PickupPoint.query.get(point_id)
        
        if not point:
            return jsonify({'success': False, 'message': 'Pickup point not found'}), 404
            
        # Store name for logging
        point_name = point.name
        
        # Delete the pickup point
        db.session.delete(point)
        db.session.commit()
        
        # Add log entry
        log_entry = AuditLog(
            category='Location Management',
            action='Delete Pickup Point',
            severity='WARNING',
            user_id=current_user.id,
            resource_type='PickupPoint',
            resource_id=str(point_id),
            details=f"Pickup point '{point_name}' deleted"
        )
        db.session.add(log_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Pickup point "{point_name}" deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting pickup point: {str(e)}")
        return jsonify({'success': False, 'message': f'Error deleting pickup point: {str(e)}'}), 500

@api.route('/geocode', methods=['GET'])
@login_required
@read_endpoint(limit="120/minute")
def geocode_address():
    """
    Convert an address to coordinates (mock implementation).
    In a production system, this would call an external geocoding API.
    """
    try:
        address = request.args.get('address', '')
        if not address:
            return jsonify({'success': False, 'message': 'Address is required'}), 400
            
        # Mock implementation using the geospatial service
        # In a real implementation, this would call an external API
        result = GeospatialService.mock_geocode(address)
        
        if result:
            return jsonify({
                'success': True,
                'result': result
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Could not geocode the provided address'
            }), 404
            
    except Exception as e:
        current_app.logger.error(f"Error geocoding address: {str(e)}")
        return jsonify({'success': False, 'message': f'Error geocoding address: {str(e)}'}), 500

@api.route('/reverse-geocode', methods=['GET'])
@login_required
@read_endpoint(limit="120/minute")
def reverse_geocode():
    """
    Convert coordinates to an address (mock implementation).
    In a production system, this would call an external geocoding API.
    """
    try:
        latitude = request.args.get('lat', type=float)
        longitude = request.args.get('lng', type=float)
        
        if latitude is None or longitude is None:
            return jsonify({'success': False, 'message': 'Latitude and longitude are required'}), 400
            
        # Mock implementation using the geospatial service
        # In a real implementation, this would call an external API
        result = GeospatialService.mock_reverse_geocode(latitude, longitude)
        
        if result:
            return jsonify({
                'success': True,
                'result': result
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Could not reverse geocode the provided coordinates'
            }), 404
            
    except Exception as e:
        current_app.logger.error(f"Error reverse geocoding: {str(e)}")
        return jsonify({'success': False, 'message': f'Error reverse geocoding: {str(e)}'}), 500

# API Key Management Endpoints

@api.route('/apikeys', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@read_endpoint(limit="120/minute")
def get_all_api_keys():
    """Get all API keys for the current user or all keys if admin."""
    try:
        # Determine if user can see all keys or just their own
        if current_user.can(Permission.ADMIN):
            query = APIKey.query
        else:
            query = APIKey.query.filter_by(user_id=current_user.id)
        
        # Order by created date (newest first)
        query = query.order_by(APIKey.created_at.desc())
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)  # Limit max per_page
        
        # Execute paginated query
        pagination = query.paginate(page=page, per_page=per_page)
        keys = pagination.items
        
        # Convert to dictionary
        keys_dict = [key.to_dict(hide_key=True) for key in keys]
        
        return jsonify({
            'success': True,
            'count': len(keys_dict),
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
            'api_keys': keys_dict
        })
    except Exception as e:
        current_app.logger.error(f"Error getting API keys: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting API keys: {str(e)}'}), 500

@api.route('/apikeys/<int:key_id>', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@read_endpoint(limit="120/minute")
def get_api_key(key_id):
    """Get a specific API key by ID."""
    try:
        api_key = APIKey.query.get(key_id)
        
        if not api_key:
            return jsonify({'success': False, 'message': 'API key not found'}), 404
            
        # Check if user has permission to view this key
        if not current_user.can(Permission.ADMIN) and api_key.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
            
        return jsonify({
            'success': True,
            'api_key': api_key.to_dict(hide_key=True)
        })
    except Exception as e:
        current_app.logger.error(f"Error getting API key: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting API key: {str(e)}'}), 500

@api.route('/apikeys', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@secure_endpoint(limit="10/minute")
def create_api_key():
    """Create a new API key."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
        
        # Generate a secure API key
        key_value = uuid.uuid4().hex + uuid.uuid4().hex  # 64 character key
        
        # Set expiration if provided
        expires_at = None
        if 'expires_days' in data and data['expires_days']:
            expires_days = int(data['expires_days'])
            if expires_days > 0:
                expires_at = datetime.utcnow() + timedelta(days=expires_days)
        
        # Create new API key
        api_key = APIKey(
            name=data['name'],
            description=data.get('description', ''),
            key_hash=key_value,  # This will be hashed in the model's __init__ method
            user_id=current_user.id,
            expires_at=expires_at,
            permissions=data.get('permissions', 0)
        )
        
        # Save to database
        db.session.add(api_key)
        db.session.commit()
        
        # Add log entry
        log_entry = AuditLog(
            category='API Key Management',
            action='Create API Key',
            severity='INFO',
            user_id=current_user.id,
            resource_type='APIKey',
            resource_id=str(api_key.id),
            details=f"API Key '{api_key.name}' created"
        )
        db.session.add(log_entry)
        db.session.commit()
        
        # Return with the unhashed key (only time it's shown)
        api_key_dict = api_key.to_dict()
        api_key_dict['key'] = key_value  # Include the actual API key only when first created
        
        return jsonify({
            'success': True,
            'message': 'API key created successfully. Please save the key value - it will not be shown again.',
            'api_key': api_key_dict
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating API key: {str(e)}")
        return jsonify({'success': False, 'message': f'Error creating API key: {str(e)}'}), 500

@api.route('/apikeys/<int:key_id>', methods=['PUT'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@secure_endpoint(limit="30/minute")
def update_api_key(key_id):
    """Update an existing API key (except the key value itself)."""
    try:
        api_key = APIKey.query.get(key_id)
        
        if not api_key:
            return jsonify({'success': False, 'message': 'API key not found'}), 404
            
        # Check if user has permission to update this key
        if not current_user.can(Permission.ADMIN) and api_key.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
            
        data = request.get_json()
        
        # Update fields
        if 'name' in data:
            api_key.name = data['name']
            
        if 'description' in data:
            api_key.description = data['description']
            
        if 'active' in data:
            api_key.active = data['active']
            
        if 'permissions' in data:
            api_key.permissions = data['permissions']
            
        # Update expiration if provided
        if 'expires_days' in data:
            if data['expires_days'] is None:
                api_key.expires_at = None
            else:
                expires_days = int(data['expires_days'])
                if expires_days > 0:
                    api_key.expires_at = datetime.utcnow() + timedelta(days=expires_days)
                else:
                    api_key.expires_at = None
                    
        api_key.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Add log entry
        log_entry = AuditLog(
            category='API Key Management',
            action='Update API Key',
            severity='INFO',
            user_id=current_user.id,
            resource_type='APIKey',
            resource_id=str(api_key.id),
            details=f"API Key '{api_key.name}' updated"
        )
        db.session.add(log_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'API key updated successfully',
            'api_key': api_key.to_dict(hide_key=True)
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating API key: {str(e)}")
        return jsonify({'success': False, 'message': f'Error updating API key: {str(e)}'}), 500

@api.route('/apikeys/<int:key_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@secure_endpoint(limit="15/minute")
def delete_api_key(key_id):
    """Delete an API key."""
    try:
        api_key = APIKey.query.get(key_id)
        
        if not api_key:
            return jsonify({'success': False, 'message': 'API key not found'}), 404
            
        # Check if user has permission to delete this key
        if not current_user.can(Permission.ADMIN) and api_key.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
            
        # Store info for logging
        key_name = api_key.name
        
        # Delete the API key
        db.session.delete(api_key)
        db.session.commit()
        
        # Add log entry
        log_entry = AuditLog(
            category='API Key Management',
            action='Delete API Key',
            severity='WARNING',
            user_id=current_user.id,
            resource_type='APIKey',
            resource_id=str(key_id),
            details=f"API Key '{key_name}' deleted"
        )
        db.session.add(log_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'API key "{key_name}" deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting API key: {str(e)}")
        return jsonify({'success': False, 'message': f'Error deleting API key: {str(e)}'}), 500

@api.route('/apikeys/<int:key_id>/regenerate', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@secure_endpoint(limit="5/minute")
def regenerate_api_key(key_id):
    """Regenerate an API key value."""
    try:
        api_key = APIKey.query.get(key_id)
        
        if not api_key:
            return jsonify({'success': False, 'message': 'API key not found'}), 404
            
        # Check if user has permission to regenerate this key
        if not current_user.can(Permission.ADMIN) and api_key.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
            
        # Generate a new secure API key
        new_key_value = uuid.uuid4().hex + uuid.uuid4().hex  # 64 character key
        
        # Update the key hash
        api_key.key_hash = new_key_value  # Will be hashed automatically
        api_key.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Add log entry
        log_entry = AuditLog(
            category='API Key Management',
            action='Regenerate API Key',
            severity='WARNING',
            user_id=current_user.id,
            resource_type='APIKey',
            resource_id=str(api_key.id),
            details=f"API Key '{api_key.name}' regenerated"
        )
        db.session.add(log_entry)
        db.session.commit()
        
        # Return with the unhashed key (only time it's shown)
        api_key_dict = api_key.to_dict()
        api_key_dict['key'] = new_key_value  # Include the actual API key
        
        return jsonify({
            'success': True,
            'message': 'API key regenerated successfully. Please save the new key value - it will not be shown again.',
            'api_key': api_key_dict
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error regenerating API key: {str(e)}")
        return jsonify({'success': False, 'message': f'Error regenerating API key: {str(e)}'}), 500

# ===== AMPDS Protocol API Endpoints =====

@api.route('/ampds/categories', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_AMPDS)
def get_ampds_categories():
    """Get unique AMPDS categories for filtering and selection in incident creation."""
    try:
        # Query for unique categories
        categories = db.session.query(AMPDSProtocol.category).distinct().order_by(AMPDSProtocol.category).all()
        
        # Format response
        result = {
            'status': 'success',
            'categories': [category[0] for category in categories]
        }
        
        # Log activity
        log_activity('API_ACCESS', f'Retrieved AMPDS categories', 'INFO')
        
        return jsonify(result), 200
    except Exception as e:
        log_activity('API_ERROR', f'Error retrieving AMPDS categories: {str(e)}', 'ERROR')
        return jsonify({
            'status': 'error',
            'message': 'Error retrieving AMPDS categories',
            'details': str(e)
        }), 500

# ===== Incident Management API Endpoints =====

@api.route('/api/incidents', methods=['GET'])
@login_required
@read_endpoint(limit="120/minute")
def get_all_incidents():
    """Get all incidents with optional filtering."""
    try:
        # Parse query parameters
        status = request.args.get('status')
        incident_type_id = request.args.get('type_id', type=int)
        priority = request.args.get('priority')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search_term = request.args.get('search', '')
        
        # Build query
        query = Incident.query
        
        # Apply filters
        if status:
            query = query.filter(Incident.status == status)
            
        if incident_type_id:
            query = query.filter(Incident.incident_type_id == incident_type_id)
            
        if priority:
            if priority.isdigit():
                query = query.filter(Incident.priority == int(priority))
            else:
                priority_value = Incident.PRIORITY_MAP.get(priority.upper())
                if priority_value:
                    query = query.filter(Incident.priority == priority_value)
        
        # Date filtering
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Incident.created_at >= start_date_obj)
            except ValueError:
                # Invalid date format, ignore this filter
                pass
                
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                # Add one day to include the entire end date
                end_date_obj = end_date_obj + timedelta(days=1)
                query = query.filter(Incident.created_at < end_date_obj)
            except ValueError:
                # Invalid date format, ignore this filter
                pass
        
        # Search by incident number, location, or description
        if search_term:
            query = query.filter(or_(
                Incident.incident_number.ilike(f'%{search_term}%'),
                Incident.location.ilike(f'%{search_term}%'),
                Incident.description.ilike(f'%{search_term}%'),
                Incident.caller.ilike(f'%{search_term}%')
            ))
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)  # Limit max per_page
        
        # Execute paginated query, ordering by newest first
        pagination = query.order_by(Incident.created_at.desc()).paginate(page=page, per_page=per_page)
        incidents = pagination.items
        
        # Convert to dictionary
        incidents_dict = [incident.to_dict() for incident in incidents]
        
        return jsonify({
            'success': True,
            'count': len(incidents_dict),
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
            'incidents': incidents_dict
        })
    except Exception as e:
        current_app.logger.error(f"Error getting incidents: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting incidents: {str(e)}'}), 500

@api.route('/api/incidents/<int:incident_id>', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def get_incident(incident_id):
    """Get a specific incident by ID."""
    try:
        incident = Incident.query.get(incident_id)
        
        if not incident:
            return jsonify({'success': False, 'message': 'Incident not found'}), 404
            
        return jsonify({
            'success': True,
            'incident': incident.to_dict()
        })
    except Exception as e:
        current_app.logger.error(f"Error getting incident: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting incident: {str(e)}'}), 500

@api.route('/api/incidents', methods=['POST'])
@login_required
@permission_required(Permission.CREATE_INCIDENT)
@secure_endpoint(limit="30/minute")
def create_incident():
    """Create a new incident."""
    try:
        # Log the API request
        current_app.logger.info(f"DB_OPERATION: Creating new incident | User: {current_user.username} ({current_user.id}) | IP: {request.remote_addr}")
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['incident_type_id', 'description']
        for field in required_fields:
            if field not in data:
                current_app.logger.warning(f"DB_OPERATION: Failed to create incident - missing field: {field} | User: {current_user.username} ({current_user.id})")
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
        
        # Create new incident
        incident = Incident(
            incident_type_id=data['incident_type_id'],
            description=data['description'],
            priority=data.get('priority', 2),
            status='PENDING',
            location=data.get('location', ''),
            location_id=data.get('location_id'),
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            caller=data.get('caller', ''),
            callback_number=data.get('callback_number', ''),
            created_by=current_user.id
        )
        
        # Set incident number
        incident.set_incident_number()
        
        # Save to database
        db.session.add(incident)
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Incident created successfully | ID: {incident.id} | Number: {incident.incident_number} | Type: {incident.incident_type_id} | User: {current_user.username} ({current_user.id})")
        
        # Create initial log entry
        log_entry = IncidentLog(
            incident_id=incident.id,
            message=f"Incident created by {current_user.username}",
            log_type='SYSTEM',
            created_by=current_user.id
        )
        db.session.add(log_entry)
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Initial log entry created for incident | Incident ID: {incident.id} | User: {current_user.username} ({current_user.id})")
        
        # Emit WebSocket event
        socketio.emit('incident_created', {
            'incident': incident.to_dict(),
            'user': current_user.to_dict()
        })
        
        return jsonify({
            'success': True,
            'message': 'Incident created successfully',
            'incident': incident.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB_OPERATION: Error creating incident: {str(e)} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error creating incident: {str(e)}'}), 500

@api.route('/api/incidents/<int:incident_id>', methods=['PUT'])
@login_required
@permission_required(Permission.UPDATE_INCIDENTS)
@secure_endpoint(limit="30/minute")
def update_incident(incident_id):
    """Update an existing incident."""
    try:
        incident = Incident.query.get(incident_id)
        
        if not incident:
            current_app.logger.warning(f"DB_OPERATION: Failed to update incident - not found | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Incident not found'}), 404
            
        # Log the API request
        current_app.logger.info(f"DB_OPERATION: Updating incident | ID: {incident_id} | Number: {incident.incident_number} | User: {current_user.username} ({current_user.id})")
        
        data = request.get_json()
        changes = []
        
        # Update fields if provided
        if 'incident_type_id' in data and data['incident_type_id'] != incident.incident_type_id:
            changes.append(f"Type: {incident.incident_type_id} -> {data['incident_type_id']}")
            incident.incident_type_id = data['incident_type_id']
            
        if 'priority' in data and data['priority'] != incident.priority:
            changes.append(f"Priority: {incident.priority} -> {data['priority']}")
            incident.priority = data['priority']
            
        if 'description' in data and data['description'] != incident.description:
            changes.append("Description updated")
            incident.description = data['description']
            
        if 'location' in data and data['location'] != incident.location:
            changes.append(f"Location: {incident.location} -> {data['location']}")
            incident.location = data['location']
            
        if 'latitude' in data and data['latitude'] != incident.latitude:
            changes.append(f"Coordinates updated")
            incident.latitude = data['latitude']
            
        if 'longitude' in data and data['longitude'] != incident.longitude:
            incident.longitude = data['longitude']
            
        if 'caller' in data and data['caller'] != incident.caller:
            changes.append(f"Caller: {incident.caller} -> {data['caller']}")
            incident.caller = data['caller']
            
        if 'callback_number' in data and data['callback_number'] != incident.callback_number:
            changes.append(f"Callback number updated")
            incident.callback_number = data['callback_number']
            
        incident.updated_at = datetime.utcnow()
        incident.updated_by = current_user.id
        
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Incident updated successfully | ID: {incident_id} | Changes: {', '.join(changes)} | User: {current_user.username} ({current_user.id})")
        
        # Add log entry for the update
        if changes:
            log_message = f"Incident updated by {current_user.username}. Changes: {', '.join(changes)}"
            log_entry = IncidentLog(
                incident_id=incident.id,
                message=log_message,
                log_type='SYSTEM',
                created_by=current_user.id
            )
            db.session.add(log_entry)
            db.session.commit()
            current_app.logger.info(f"DB_OPERATION: Update log entry created for incident | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        
        # Emit WebSocket event
        socketio.emit('incident_updated', {
            'incident': incident.to_dict(),
            'user': current_user.to_dict(),
            'changes': changes
        })
        
        return jsonify({
            'success': True,
            'message': 'Incident updated successfully',
            'incident': incident.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB_OPERATION: Error updating incident: {str(e)} | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error updating incident: {str(e)}'}), 500

@api.route('/api/incidents/<int:incident_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.DELETE_INCIDENTS)
@secure_endpoint(limit="10/minute")
def delete_incident(incident_id):
    """Delete an incident."""
    try:
        incident = Incident.query.get(incident_id)
        
        if not incident:
            current_app.logger.warning(f"DB_OPERATION: Failed to delete incident - not found | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Incident not found'}), 404
            
        # Store incident details for logging
        incident_num = incident.incident_number
        
        # Add to audit log before deletion
        audit_log = AuditLog(
            category='Incident Management',
            action='Delete Incident',
            severity='WARNING',
            user_id=current_user.id,
            resource_type='Incident',
            resource_id=str(incident.id),
            details=f"Incident {incident_num} deleted"
        )
        db.session.add(audit_log)
        
        # Delete the incident (will cascade delete logs and assignments due to relationship settings)
        db.session.delete(incident)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Incident {incident_num} deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB_OPERATION: Error deleting incident: {str(e)} | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error deleting incident: {str(e)}'}), 500

@api.route('/api/incidents/<int:incident_id>/status', methods=['PUT'])
@login_required
@permission_required(Permission.UPDATE_INCIDENTS)
@secure_endpoint(limit="30/minute")
def update_incident_status(incident_id):
    """Update incident status."""
    try:
        incident = Incident.query.get(incident_id)
        
        if not incident:
            current_app.logger.warning(f"DB_OPERATION: Failed to update incident status - incident not found | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Incident not found'}), 404
            
        data = request.get_json()
        
        if 'status' not in data:
            current_app.logger.warning(f"DB_OPERATION: Failed to update incident status - missing status field | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Missing required field: status'}), 400
            
        old_status = incident.status
        new_status = data['status']
        
        # Log the status change attempt
        current_app.logger.info(f"DB_OPERATION: Updating incident status | ID: {incident_id} | Old status: {old_status} | New status: {new_status} | User: {current_user.username} ({current_user.id})")
        
        # Validate status transition
        valid_transitions = {
            'PENDING': ['ACTIVE', 'CANCELLED'],
            'ACTIVE': ['PENDING', 'EN_ROUTE', 'ON_SCENE', 'CLOSED'],
            'EN_ROUTE': ['ACTIVE', 'ON_SCENE', 'CLOSED'],
            'ON_SCENE': ['ACTIVE', 'CLOSED'],
            'CLOSED': [],  # Closed incidents cannot transition to other statuses
            'CANCELLED': ['PENDING']  # Cancelled incidents can only be reopened as pending
        }
        
        if new_status not in valid_transitions.get(old_status, []):
            current_app.logger.warning(f"DB_OPERATION: Invalid status transition | ID: {incident_id} | From {old_status} to {new_status} | User: {current_user.username} ({current_user.id})")
            return jsonify({
                'success': False, 
                'message': f'Invalid status transition from {old_status} to {new_status}'
            }), 400
            
        # Update status
        incident.status = new_status
        incident.updated_at = datetime.utcnow()
        incident.updated_by = current_user.id
        
        # Add closure information if closing the incident
        if new_status == 'CLOSED':
            incident.closed_at = datetime.utcnow()
            incident.closed_by = current_user.id
            incident.resolution = data.get('resolution', '')
            current_app.logger.info(f"DB_OPERATION: Incident closed | ID: {incident_id} | Resolution: {incident.resolution} | User: {current_user.username} ({current_user.id})")
        
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Incident status updated successfully | ID: {incident_id} | From {old_status} to {new_status} | User: {current_user.username} ({current_user.id})")
        
        # Add log entry for the status change
        log_entry = IncidentLog(
            incident_id=incident.id,
            message=f"Status changed from {old_status} to {new_status} by {current_user.username}",
            log_type='STATUS',
            created_by=current_user.id
        )
        db.session.add(log_entry)
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Status change log entry created for incident | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        
        # Emit WebSocket event
        event_type = 'incident_closed' if new_status == 'CLOSED' else 'incident_status_changed'
        socketio.emit(event_type, {
            'incident': incident.to_dict(),
            'user': current_user.to_dict(),
            'old_status': old_status,
            'new_status': new_status
        })
        
        return jsonify({
            'success': True,
            'message': f'Incident status updated to {new_status}',
            'incident': incident.to_dict()
        })
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB_OPERATION: Error updating incident status: {str(e)} | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error updating incident status: {str(e)}'}), 500

@api.route('/api/incidents/<int:incident_id>/logs', methods=['GET'])
@login_required
@read_endpoint(limit="120/minute")
def get_incident_logs(incident_id):
    """Get logs for a specific incident."""
    try:
        incident = Incident.query.get(incident_id)
        
        if not incident:
            current_app.logger.warning(f"DB_OPERATION: Failed to get incident logs - incident not found | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Incident not found'}), 404
            
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)  # Limit max per_page
        
        # Get log type filter if provided
        log_type = request.args.get('type')
        
        # Build query
        query = IncidentLog.query.filter_by(incident_id=incident_id)
        
        if log_type:
            query = query.filter_by(type=log_type)
            
        # Execute paginated query, ordering by newest first
        pagination = query.order_by(IncidentLog.timestamp.desc()).paginate(page=page, per_page=per_page)
        logs = pagination.items
        
        # Convert to dictionary
        logs_dict = [log.to_dict() for log in logs]
        
        return jsonify({
            'success': True,
            'count': len(logs_dict),
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
            'logs': logs_dict
        })
    except Exception as e:
        current_app.logger.error(f"DB_OPERATION: Error getting incident logs: {str(e)} | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error getting incident logs: {str(e)}'}), 500

@api.route('/api/incidents/<int:incident_id>/logs', methods=['POST'])
@login_required
@permission_required(Permission.UPDATE_INCIDENTS)
@secure_endpoint(limit="60/minute")
def add_incident_log(incident_id):
    """Add a log entry to an incident."""
    try:
        incident = Incident.query.get(incident_id)
        
        if not incident:
            current_app.logger.warning(f"DB_OPERATION: Failed to add log entry - incident not found | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Incident not found'}), 404
            
        data = request.get_json()
        
        # Validate required fields
        if 'message' not in data:
            current_app.logger.warning(f"DB_OPERATION: Failed to add log entry - missing message | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Missing required field: message'}), 400
            
        # Log the operation
        current_app.logger.info(f"DB_OPERATION: Adding log entry to incident | ID: {incident_id} | Type: {data.get('type', 'INFO')} | User: {current_user.username} ({current_user.id})")
        
        # Create log entry
        log_entry = IncidentLog(
            incident_id=incident_id,
            message=data['message'],
            type=data.get('type', 'INFO'),
            created_by=current_user.id
        )
        
        db.session.add(log_entry)
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Log entry added successfully | ID: {log_entry.id} | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        
        return jsonify({
            'success': True,
            'message': 'Log entry added successfully',
            'log': log_entry.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB_OPERATION: Error adding log entry: {str(e)} | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error adding log entry: {str(e)}'}), 500

# ===== Incident Type Management API Endpoints =====

@api.route('/incident-types', methods=['GET'])
@login_required
@read_endpoint(limit="120/minute")
def get_all_incident_types():
    """Get all incident types with optional filtering."""
    try:
        # Check if we should filter active only
        active_only = request.args.get('active', 'true').lower() == 'true'
        query = IncidentType.query
        
        if active_only:
            query = query.filter_by(active=True)
            
        # Filter by name search term if provided
        search_term = request.args.get('search', '')
        if search_term:
            query = query.filter(IncidentType.name.ilike(f'%{search_term}%'))
            
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)  # Limit max per_page
        
        # Execute paginated query
        pagination = query.order_by(IncidentType.name).paginate(page=page, per_page=per_page)
        incident_types = pagination.items
        
        # Convert to dictionary
        types_dict = [incident_type.to_dict() for incident_type in incident_types]
        
        return jsonify({
            'success': True,
            'count': len(types_dict),
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
            'incident_types': types_dict
        })
    except Exception as e:
        current_app.logger.error(f"Error getting incident types: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting incident types: {str(e)}'}), 500

@api.route('/incident-types/<int:type_id>', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def get_incident_type(type_id):
    """Get a specific incident type by ID."""
    try:
        incident_type = IncidentType.query.get(type_id)
        
        if not incident_type:
            current_app.logger.warning(f"DB_OPERATION: Failed to get incident type - not found | ID: {type_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Incident type not found'}), 404
            
        return jsonify({
            'success': True,
            'incident_type': incident_type.to_dict()
        })
    except Exception as e:
        current_app.logger.error(f"DB_OPERATION: Error getting incident type: {str(e)} | ID: {type_id} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error getting incident type: {str(e)}'}), 500

@api.route('/incident-types', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_INCIDENTS)
@secure_endpoint(limit="30/minute")
def create_incident_type():
    """Create a new incident type."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name']
        for field in required_fields:
            if field not in data:
                current_app.logger.warning(f"DB_OPERATION: Failed to create incident type - missing field: {field} | User: {current_user.username} ({current_user.id})")
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
        
        # Check if name already exists
        existing = IncidentType.query.filter_by(name=data['name']).first()
        if existing:
            current_app.logger.warning(f"DB_OPERATION: Failed to create incident type - name already exists | Name: {data['name']} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': f'Incident type with name "{data["name"]}" already exists'}), 400
        
        # Create new incident type
        incident_type = IncidentType(
            name=data['name'],
            description=data.get('description', ''),
            default_priority=data.get('default_priority', 2),
            color=data.get('color', '#007bff'),
            requires_location=data.get('requires_location', True),
            requires_caller=data.get('requires_caller', True),
            active=data.get('active', True)
        )
        
        # Save to database
        db.session.add(incident_type)
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Incident type created successfully | ID: {incident_type.id} | Name: {incident_type.name} | User: {current_user.username} ({current_user.id})")
        
        # Add to audit log
        audit_log = AuditLog(
            category='Incident Management',
            action='Create Incident Type',
            severity='INFO',
            user_id=current_user.id,
            resource_type='IncidentType',
            resource_id=str(incident_type.id),
            details=f"Incident type '{incident_type.name}' created"
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Incident type created successfully',
            'incident_type': incident_type.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB_OPERATION: Error creating incident type: {str(e)} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error creating incident type: {str(e)}'}), 500

@api.route('/incident-types/<int:type_id>', methods=['PUT'])
@login_required
@permission_required(Permission.MANAGE_INCIDENTS)
@secure_endpoint(limit="30/minute")
def update_incident_type(type_id):
    """Update an existing incident type."""
    try:
        incident_type = IncidentType.query.get(type_id)
        
        if not incident_type:
            current_app.logger.warning(f"DB_OPERATION: Failed to update incident type - not found | ID: {type_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Incident type not found'}), 404
            
        data = request.get_json()
        
        # Check if name is being changed and already exists
        if 'name' in data and data['name'] != incident_type.name:
            existing = IncidentType.query.filter_by(name=data['name']).first()
            if existing:
                current_app.logger.warning(f"DB_OPERATION: Failed to update incident type - name already exists | Name: {data['name']} | User: {current_user.username} ({current_user.id})")
                return jsonify({'success': False, 'message': f'Incident type with name "{data["name"]}" already exists'}), 400
            incident_type.name = data['name']
            
        # Update other fields if provided
        if 'description' in data:
            incident_type.description = data['description']
            
        if 'default_priority' in data:
            incident_type.default_priority = data['default_priority']
            
        if 'color' in data:
            incident_type.color = data['color']
            
        if 'requires_location' in data:
            incident_type.requires_location = data['requires_location']
            
        if 'requires_caller' in data:
            incident_type.requires_caller = data['requires_caller']
            
        if 'active' in data:
            incident_type.active = data['active']
            
        incident_type.updated_at = datetime.utcnow()
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Incident type updated successfully | ID: {type_id} | Name: {incident_type.name} | User: {current_user.username} ({current_user.id})")
        
        # Add to audit log
        audit_log = AuditLog(
            category='Incident Management',
            action='Update Incident Type',
            severity='INFO',
            user_id=current_user.id,
            resource_type='IncidentType',
            resource_id=str(incident_type.id),
            details=f"Incident type '{incident_type.name}' updated"
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Incident type updated successfully',
            'incident_type': incident_type.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB_OPERATION: Error updating incident type: {str(e)} | ID: {type_id} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error updating incident type: {str(e)}'}), 500

@api.route('/incident-types/<int:type_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.MANAGE_INCIDENTS)
@secure_endpoint(limit="10/minute")
def delete_incident_type(type_id):
    """Delete an incident type."""
    try:
        incident_type = IncidentType.query.get(type_id)
        
        if not incident_type:
            current_app.logger.warning(f"DB_OPERATION: Failed to delete incident type - not found | ID: {type_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Incident type not found'}), 404
            
        # Check if there are any incidents using this type
        incident_count = Incident.query.filter_by(incident_type_id=type_id).count()
        if incident_count > 0:
            current_app.logger.warning(f"DB_OPERATION: Failed to delete incident type - type is used by incidents | ID: {type_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({
                'success': False, 
                'message': f'Cannot delete incident type that is used by {incident_count} incidents'
            }), 400
            
        # Store incident type name for logging
        type_name = incident_type.name
        
        # Add to audit log before deletion
        audit_log = AuditLog(
            category='Incident Management',
            action='Delete Incident Type',
            severity='WARNING',
            user_id=current_user.id,
            resource_type='IncidentType',
            resource_id=str(incident_type.id),
            details=f"Incident type '{type_name}' deleted"
        )
        db.session.add(audit_log)
        
        # Delete the incident type
        db.session.delete(incident_type)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Incident type "{type_name}" deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB_OPERATION: Error deleting incident type: {str(e)} | ID: {type_id} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error deleting incident type: {str(e)}'}), 500

# ===========================
# Notification System API
# ===========================

@api.route('/notifications', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def get_notifications():
    """
    Get all notifications for the current user with filtering options.
    
    Query Parameters:
    - unread_only (bool): Filter to unread notifications only
    - type (str): Filter by notification type (system, incident, unit, user, alert)
    - start_date (str): Filter by date range start (ISO 8601 format)
    - end_date (str): Filter by date range end (ISO 8601 format)
    - page (int): Page number for pagination
    - per_page (int): Results per page
    
    Returns:
        JSON response with notifications
    """
    # Get query parameters
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    notification_type = request.args.get('type')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    
    # Parse dates if provided
    start_date = None
    end_date = None
    
    if start_date_str:
        try:
            start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Invalid start_date format. Use ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ).'
            }), 400
            
    if end_date_str:
        try:
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Invalid end_date format. Use ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ).'
            }), 400
    
    # Build the query
    query = Notification.query.filter_by(user_id=current_user.id)
    
    if unread_only:
        query = query.filter_by(read=False)
        
    if notification_type:
        valid_types = [Notification.TYPE_SYSTEM, Notification.TYPE_INCIDENT, 
                      Notification.TYPE_UNIT, Notification.TYPE_USER, Notification.TYPE_ALERT]
        if notification_type not in valid_types:
            return jsonify({
                'success': False,
                'message': f'Invalid notification type. Must be one of: {", ".join(valid_types)}'
            }), 400
        query = query.filter_by(notification_type=notification_type)
        
    if start_date:
        query = query.filter(Notification.created_at >= start_date)
        
    if end_date:
        query = query.filter(Notification.created_at <= end_date)
    
    # Order by most recent first
    query = query.order_by(Notification.created_at.desc())
    
    # Paginate results
    paginated = query.paginate(page=page, per_page=per_page)
    
    # Prepare response
    notifications = [n.to_dict() for n in paginated.items]
    
    return jsonify({
        'success': True,
        'notifications': notifications,
        'pagination': {
            'total': paginated.total,
            'pages': paginated.pages,
            'page': page,
            'per_page': per_page,
            'has_next': paginated.has_next,
            'has_prev': paginated.has_prev
        }
    })

@api.route('/notifications/unread-count', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def get_unread_notifications_count():
    """
    Get the count of unread notifications for the current user.
    
    Returns:
        JSON response with unread notification count
    """
    count = Notification.query.filter_by(user_id=current_user.id, read=False).count()
    
    return jsonify({
        'success': True,
        'unread_count': count
    })

@api.route('/notifications/<int:notification_id>/read', methods=['PUT'])
@login_required
@secure_endpoint(limit="60/minute")
def mark_notification_read(notification_id):
    """
    Mark a notification as read.
    
    Parameters:
        notification_id (int): ID of the notification to mark as read
    
    Returns:
        JSON response with success status
    """
    notification = Notification.query.get_or_404(notification_id)
    
    # Check ownership
    if notification.user_id != current_user.id:
        return jsonify({
            'success': False,
            'message': 'Notification not found or access denied'
        }), 404
    
    # Mark as read
    notification.read = True
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Notification marked as read'
    })

@api.route('/notifications/read-all', methods=['PUT'])
@login_required
@secure_endpoint(limit="30/minute")
def mark_all_notifications_read():
    """
    Mark all notifications as read for the current user.
    
    Returns:
        JSON response with success status
    """
    # Update all unread notifications for current user
    Notification.query.filter_by(user_id=current_user.id, read=False).update({'read': True})
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'All notifications marked as read'
    })

@api.route('/notifications/<int:notification_id>', methods=['DELETE'])
@login_required
@secure_endpoint(limit="30/minute")
def delete_notification(notification_id):
    """
    Delete a notification.
    
    Parameters:
        notification_id (int): ID of the notification to delete
    
    Returns:
        JSON response with success status
    """
    notification = Notification.query.get_or_404(notification_id)
    
    # Check ownership
    if notification.user_id != current_user.id:
        return jsonify({
            'success': False,
            'message': 'Notification not found or access denied'
        }), 404
    
    # Delete notification
    db.session.delete(notification)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Notification deleted'
    })

@api.route('/notifications/preferences', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def get_notification_preferences():
    """
    Get notification preferences for the current user.
    
    Returns:
        JSON response with preferences
    """
    # Get or create preferences
    prefs = NotificationPreference.get_or_create(current_user.id)
    
    return jsonify({
        'success': True,
        'preferences': prefs.to_dict()
    })

@api.route('/notifications/preferences', methods=['PUT'])
@login_required
@secure_endpoint(limit="30/minute")
def update_notification_preferences():
    """
    Update notification preferences for the current user.
    
    Request Body:
    - app_enabled (bool): Enable app notifications
    - email_enabled (bool): Enable email notifications
    - app_notify_incident_created (bool): Notify when incidents are created
    - app_notify_incident_updated (bool): Notify when incidents are updated
    - app_notify_incident_closed (bool): Notify when incidents are closed
    - app_notify_unit_assigned (bool): Notify when units are assigned
    - app_notify_unit_cleared (bool): Notify when units are cleared
    - app_notify_system_events (bool): Notify for system events
    - email_notify_incident_created (bool): Email for incident creation
    - email_notify_incident_updated (bool): Email for incident updates
    - email_notify_incident_closed (bool): Email for incident closure
    - email_notify_unit_assigned (bool): Email for unit assignments
    - email_notify_unit_cleared (bool): Email for unit clearance
    - email_notify_system_events (bool): Email for system events
    
    Returns:
        JSON response with updated preferences
    """
    # Get or create preferences
    prefs = NotificationPreference.get_or_create(current_user.id)
    
    # Parse JSON request
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'message': 'No data provided'
        }), 400
    
    # Update app notification settings
    if 'app_enabled' in data:
        prefs.app_enabled = bool(data['app_enabled'])
    if 'app_notify_incident_created' in data:
        prefs.app_notify_incident_created = bool(data['app_notify_incident_created'])
    if 'app_notify_incident_updated' in data:
        prefs.app_notify_incident_updated = bool(data['app_notify_incident_updated'])
    if 'app_notify_incident_closed' in data:
        prefs.app_notify_incident_closed = bool(data['app_notify_incident_closed'])
    if 'app_notify_unit_assigned' in data:
        prefs.app_notify_unit_assigned = bool(data['app_notify_unit_assigned'])
    if 'app_notify_unit_cleared' in data:
        prefs.app_notify_unit_cleared = bool(data['app_notify_unit_cleared'])
    if 'app_notify_system_events' in data:
        prefs.app_notify_system_events = bool(data['app_notify_system_events'])
    
    # Update email notification settings
    if 'email_enabled' in data:
        prefs.email_enabled = bool(data['email_enabled'])
    if 'email_notify_incident_created' in data:
        prefs.email_notify_incident_created = bool(data['email_notify_incident_created'])
    if 'email_notify_incident_updated' in data:
        prefs.email_notify_incident_updated = bool(data['email_notify_incident_updated'])
    if 'email_notify_incident_closed' in data:
        prefs.email_notify_incident_closed = bool(data['email_notify_incident_closed'])
    if 'email_notify_unit_assigned' in data:
        prefs.email_notify_unit_assigned = bool(data['email_notify_unit_assigned'])
    if 'email_notify_unit_cleared' in data:
        prefs.email_notify_unit_cleared = bool(data['email_notify_unit_cleared'])
    if 'email_notify_system_events' in data:
        prefs.email_notify_system_events = bool(data['email_notify_system_events'])
    
    # Save changes
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Notification preferences updated',
        'preferences': prefs.to_dict()
    })

@api.route('/notifications/audio-preferences', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def get_audio_preferences():
    """
    Get audio notification preferences for the current user.
    
    Returns:
        JSON response with audio preferences
    """
    # Get or create preferences
    prefs = NotificationPreference.get_or_create(current_user.id)
    
    # Extract only audio-related preferences
    audio_prefs = {
        'audio_enabled': prefs.sound_notifications_enabled,
        'audio_incident_created': prefs.sound_incident_created,
        'audio_incident_updated': prefs.sound_incident_updated,
        'audio_incident_closed': prefs.sound_incident_closed,
        'audio_unit_assigned': prefs.sound_unit_assigned,
        'audio_unit_status_changed': prefs.sound_unit_status_changed
    }
    
    return jsonify({
        'success': True,
        'audio_preferences': audio_prefs
    })

@api.route('/notifications/audio-preferences', methods=['PUT'])
@login_required
@secure_endpoint(limit="30/minute")
def update_audio_preferences():
    """
    Update audio notification preferences for the current user.
    
    Request Body:
    - audio_enabled (bool): Enable audio notifications
    - audio_incident_created (bool): Audio alert for incident creation
    - audio_incident_updated (bool): Audio alert for incident updates
    - audio_incident_closed (bool): Audio alert for incident closure
    - audio_unit_assigned (bool): Audio alert for unit assignments
    - audio_unit_status_changed (bool): Audio alert for unit status changes
    
    Returns:
        JSON response with updated audio preferences
    """
    # Get or create preferences
    prefs = NotificationPreference.get_or_create(current_user.id)
    
    # Parse JSON request
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'message': 'No data provided'
        }), 400
    
    # Update audio notification settings
    if 'audio_enabled' in data:
        prefs.sound_notifications_enabled = bool(data['audio_enabled'])
    if 'audio_incident_created' in data:
        prefs.sound_incident_created = bool(data['audio_incident_created'])
    if 'audio_incident_updated' in data:
        prefs.sound_incident_updated = bool(data['audio_incident_updated'])
    if 'audio_incident_closed' in data:
        prefs.sound_incident_closed = bool(data['audio_incident_closed'])
    if 'audio_unit_assigned' in data:
        prefs.sound_unit_assigned = bool(data['audio_unit_assigned'])
    if 'audio_unit_status_changed' in data:
        prefs.sound_unit_status_changed = bool(data['audio_unit_status_changed'])
    
    # Save changes
    db.session.commit()
    
    # Extract only audio-related preferences for response
    audio_prefs = {
        'audio_enabled': prefs.sound_notifications_enabled,
        'audio_incident_created': prefs.sound_incident_created,
        'audio_incident_updated': prefs.sound_incident_updated,
        'audio_incident_closed': prefs.sound_incident_closed,
        'audio_unit_assigned': prefs.sound_unit_assigned,
        'audio_unit_status_changed': prefs.sound_unit_status_changed
    }
    
    return jsonify({
        'success': True,
        'message': 'Audio preferences updated',
        'audio_preferences': audio_prefs
    })

# Admin-only notification endpoints
@api.route('/admin/notifications', methods=['POST'])
@login_required
@admin_required
@secure_endpoint(limit="30/minute")
def create_notification():
    """
    Create a new notification (admin only).
    
    Request Body:
    - user_id (int): ID of the user to notify (required)
    - title (str): Notification title (required)
    - message (str): Notification message (required)
    - notification_type (str): Type of notification (system, incident, unit, user, alert)
    - reference_id (int): Optional ID reference to related entity
    - reference_type (str): Type of reference (incident, unit, etc.)
    - broadcast (bool): Whether to broadcast via WebSocket
    - send_email (bool): Whether to send email notification
    
    Returns:
        JSON response with created notification
    """
    # Parse JSON request
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'message': 'No data provided'
        }), 400
    
    # Validate required fields
    required_fields = ['user_id', 'title', 'message']
    for field in required_fields:
        if field not in data:
            return jsonify({
                'success': False,
                'message': f'Missing required field: {field}'
            }), 400
    
    # Validate user exists
    user = User.query.get(data['user_id'])
    if not user:
        return jsonify({
            'success': False,
            'message': f'User with ID {data["user_id"]} not found'
        }), 404
    
    # Set defaults
    notification_type = data.get('notification_type', Notification.TYPE_SYSTEM)
    reference_id = data.get('reference_id')
    reference_type = data.get('reference_type')
    broadcast = data.get('broadcast', True)
    send_email = data.get('send_email', True)
    
    # Create notification
    notification = NotificationService.create_notification(
        user_id=data['user_id'],
        title=data['title'],
        message=data['message'],
        notification_type=notification_type,
        reference_id=reference_id,
        reference_type=reference_type,
        broadcast=broadcast,
        send_email=send_email
    )
    
    if not notification:
        return jsonify({
            'success': False,
            'message': 'Failed to create notification. User may have disabled this notification type.'
        }), 400
    
    return jsonify({
        'success': True,
        'message': 'Notification created',
        'notification': notification.to_dict()
    }), 201

@api.route('/admin/notifications/bulk', methods=['POST'])
@login_required
@admin_required
@secure_endpoint(limit="30/minute")
def create_bulk_notifications():
    """
    Create notifications for multiple users (admin only).
    
    Request Body:
    - user_ids (list): List of user IDs to notify (required)
    - title (str): Notification title (required)
    - message (str): Notification message (required)
    - notification_type (str): Type of notification (system, incident, unit, user, alert)
    - reference_id (int): Optional ID reference to related entity
    - reference_type (str): Type of reference (incident, unit, etc.)
    - broadcast (bool): Whether to broadcast via WebSocket
    - send_email (bool): Whether to send email notification
    
    Returns:
        JSON response with created notifications
    """
    # Parse JSON request
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'message': 'No data provided'
        }), 400
    
    # Validate required fields
    required_fields = ['user_ids', 'title', 'message']
    for field in required_fields:
        if field not in data:
            return jsonify({
                'success': False,
                'message': f'Missing required field: {field}'
            }), 400
    
    # Validate user_ids is a list
    if not isinstance(data['user_ids'], list) or not data['user_ids']:
        return jsonify({
            'success': False,
            'message': 'user_ids must be a non-empty list'
        }), 400
    
    # Set defaults
    notification_type = data.get('notification_type', Notification.TYPE_SYSTEM)
    reference_id = data.get('reference_id')
    reference_type = data.get('reference_type')
    broadcast = data.get('broadcast', True)
    send_email = data.get('send_email', True)
    
    # Create notifications
    notifications = NotificationService.create_bulk_notifications(
        user_ids=data['user_ids'],
        title=data['title'],
        message=data['message'],
        notification_type=notification_type,
        reference_id=reference_id,
        reference_type=reference_type,
        broadcast=broadcast,
        send_email=send_email
    )
    
    return jsonify({
        'success': True,
        'message': f'Created {len(notifications)} notifications',
        'notification_count': len(notifications)
    }), 201

@api.route('/admin/notifications/audio-alert', methods=['POST'])
@login_required
@admin_required
@secure_endpoint(limit="30/minute")
def trigger_audio_alert():
    """
    Trigger an audio alert for users (admin only).
    
    Request Body:
    - user_ids (list): List of user IDs to alert (required)
    - alert_type (str): Type of alert (emergency, incident, unit, system)
    - message (str): Optional message to display with alert
    - sound (str): Optional sound file to play
    - priority (int): Alert priority (1-5, 5 being highest)
    
    Returns:
        JSON response with success status
    """
    # Parse JSON request
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'message': 'No data provided'
        }), 400
    
    # Validate required fields
    if 'user_ids' not in data:
        return jsonify({
            'success': False,
            'message': 'Missing required field: user_ids'
        }), 400
    
    # Validate user_ids is a list
    if not isinstance(data['user_ids'], list) or not data['user_ids']:
        return jsonify({
            'success': False,
            'message': 'user_ids must be a non-empty list'
        }), 400
    
    # Set defaults
    alert_type = data.get('alert_type', 'system')
    message = data.get('message', '')
    sound = data.get('sound', 'default_alert.mp3')
    priority = min(max(data.get('priority', 3), 1), 5)  # Ensure priority is between 1-5
    
    # Trigger audio alert via WebSocket
    if socketio:
        for user_id in data['user_ids']:
            # Create alert payload
            alert_data = {
                'alert_type': alert_type,
                'message': message,
                'sound': sound,
                'priority': priority,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Emit to user's room
            socketio.emit('audio_alert', alert_data, room=f"user_{user_id}")
    
    return jsonify({
        'success': True,
        'message': f'Audio alert sent to {len(data["user_ids"])} users'
    })

# WebSocket connection status endpoints
@api.route('/websocket/connections', methods=['GET'])
@login_required
@admin_required
@read_endpoint(limit="180/minute")
def get_websocket_connections():
    """
    Get all active WebSocket connections (admin only).
    
    Returns:
        JSON response with active connections
    """
    # Get all active connections
    connections = ConnectionManager.get_all_connections()
    
    # Format connection data
    connection_data = []
    for conn_id, conn in connections.items():
        user = User.query.get(conn['user_id']) if 'user_id' in conn else None
        connection_data.append({
            'client_id': conn_id,
            'user_id': conn.get('user_id'),
            'username': user.username if user else None,
            'connected_at': conn.get('connected_at'),
            'last_seen': conn.get('last_seen'),
            'state': conn.get('state'),
            'rooms': conn.get('rooms', [])
        })
    
    return jsonify({
        'success': True,
        'active_connections': connection_data,
        'total_connections': len(connection_data)
    })

@api.route('/websocket/connections/<client_id>', methods=['DELETE'])
@login_required
@admin_required
@secure_endpoint(limit="30/minute")
def disconnect_websocket_client(client_id):
    """
    Forcibly disconnect a WebSocket client (admin only).
    
    Parameters:
        client_id (str): Client ID to disconnect
    
    Returns:
        JSON response with success status
    """
    # Check if connection exists
    if not ConnectionManager.connection_exists(client_id):
        return jsonify({
            'success': False,
            'message': f'Connection with ID {client_id} not found'
        }), 404
    
    # Disconnect client
    if socketio:
        socketio.disconnect(client_id)
    
    # Remove from connection manager
    ConnectionManager.remove_connection(client_id)
    
    return jsonify({
        'success': True,
        'message': f'Connection {client_id} disconnected'
    })

@api.route('/websocket/connections/user/<int:user_id>', methods=['GET'])
@login_required
@admin_required
@read_endpoint(limit="180/minute")
def get_user_connections(user_id):
    """
    Get all active WebSocket connections for a specific user (admin only).
    
    Parameters:
        user_id (int): User ID to get connections for
    
    Returns:
        JSON response with user's connections
    """
    # Check if user exists
    user = User.query.get_or_404(user_id)
    
    # Get user's connections
    connections = ConnectionManager.get_user_connections(user_id)
    
    # Format connection data
    connection_data = []
    for conn_id, conn in connections.items():
        connection_data.append({
            'client_id': conn_id,
            'connected_at': conn.get('connected_at'),
            'last_seen': conn.get('last_seen'),
            'state': conn.get('state'),
            'rooms': conn.get('rooms', [])
        })
    
    return jsonify({
        'success': True,
        'user_id': user_id,
        'username': user.username,
        'connections': connection_data,
        'total_connections': len(connection_data)
    })

@api.route('/websocket/health', methods=['GET'])
@login_required
@read_endpoint(limit="180/minute")
def websocket_health():
    """
    Check WebSocket server health status.
    
    Returns:
        JSON response with WebSocket server status
    """
    is_available = socketio is not None
    
    return jsonify({
        'success': True,
        'websocket_available': is_available,
        'status': 'online' if is_available else 'offline'
    })

# ===== Map API Endpoints =====

@api.route('/map/config', methods=['GET'])
@login_required
def get_map_config():
    """Get map configuration for the frontend."""
    try:
        from services.geospatial_service import GeospatialService
        config = GeospatialService.get_map_config()
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        current_app.logger.error(f"Error getting map config: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@api.route('/map/data', methods=['GET'])
@login_required
def get_map_data():
    """Get all map data (units, incidents) for the frontend."""
    try:
        from services.geospatial_service import GeospatialService
        units = GeospatialService.get_all_units_locations()
        incidents = GeospatialService.get_all_active_incidents_locations()
        return jsonify({
            'success': True,
            'data': {
                'units': units,
                'incidents': incidents
            }
        })
    except Exception as e:
        current_app.logger.error(f"Error getting map data: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@api.route('/map/nearest-units/<int:incident_id>', methods=['GET'])
@login_required
def get_nearest_units(incident_id):
    """Find nearest available units to an incident."""
    try:
        from services.geospatial_service import GeospatialService
        limit = request.args.get('limit', 5, type=int)
        max_distance = request.args.get('maxDistance', 50, type=float)
        units = GeospatialService.find_nearest_units(incident_id, limit=limit, max_distance=max_distance)
        return jsonify({'success': True, 'units': units})
    except Exception as e:
        current_app.logger.error(f"Error finding nearest units: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@api.route('/map/route', methods=['GET'])
@login_required
def get_map_route():
    """Calculate route between two points."""
    try:
        from services.geospatial_service import GeospatialService
        start_lat = request.args.get('startLat', type=float)
        start_lng = request.args.get('startLng', type=float)
        end_lat = request.args.get('endLat', type=float)
        end_lng = request.args.get('endLng', type=float)
        if None in (start_lat, start_lng, end_lat, end_lng):
            return jsonify({'success': False, 'message': 'Missing coordinates'}), 400
        route = GeospatialService.mock_get_route(start_lat, start_lng, end_lat, end_lng)
        return jsonify({'success': True, 'route': route})
    except Exception as e:
        current_app.logger.error(f"Error calculating route: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Unit Assignment API Endpoints
@api.route('/incidents/<int:incident_id>/assign-unit', methods=['POST'])
@login_required
@permission_required(Permission.ASSIGN_UNITS)
@secure_endpoint(limit="30/minute")
def assign_unit_to_incident(incident_id):
    """Assign a unit to an incident."""
    try:
        incident = Incident.query.get(incident_id)
        
        if not incident:
            current_app.logger.warning(f"DB_OPERATION: Failed to assign unit - incident not found | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Incident not found'}), 404
            
        data = request.get_json()
        
        if 'unit_id' not in data:
            current_app.logger.warning(f"DB_OPERATION: Failed to assign unit - missing unit_id | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Missing required field: unit_id'}), 400
            
        unit_id = data['unit_id']
        
        # Check if unit exists
        unit = Unit.query.get(unit_id)
        if not unit:
            current_app.logger.warning(f"DB_OPERATION: Failed to assign unit - unit not found | Unit ID: {unit_id} | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Unit not found'}), 404
            
        # Check if unit is already assigned to this incident
        existing_assignment = UnitAssignment.query.filter_by(
            incident_id=incident_id,
            unit_id=unit_id,
            active=True
        ).first()
        
        if existing_assignment:
            current_app.logger.warning(f"DB_OPERATION: Unit already assigned | Unit ID: {unit_id} | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Unit is already assigned to this incident'}), 400
            
        # Log the assignment attempt
        current_app.logger.info(f"DB_OPERATION: Assigning unit to incident | Unit ID: {unit_id} | Unit Name: {unit.name} | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        
        # Create assignment
        assignment = UnitAssignment(
            incident_id=incident_id,
            unit_id=unit_id,
            assigned_by=current_user.id,
            assignment_time=datetime.utcnow(),
            active=True
        )
        db.session.add(assignment)
        
        # Update unit status if it's available
        if unit.status == 'AVAILABLE':
            unit.status = 'ASSIGNED'
            unit.last_status_change = datetime.utcnow()
            unit.current_incident_id = incident_id
            current_app.logger.info(f"DB_OPERATION: Unit status updated from AVAILABLE to ASSIGNED | Unit ID: {unit_id} | Incident ID: {incident_id}")
        
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Unit assigned successfully | Unit ID: {unit_id} | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        
        # Add log entry
        log_entry = IncidentLog(
            incident_id=incident.id,
            message=f"Unit {unit.name} assigned by {current_user.username}",
            log_type='UNIT',
            created_by=current_user.id
        )
        db.session.add(log_entry)
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Unit assignment log entry created | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        
        # Emit WebSocket events
        socketio.emit('incident_unit_assigned', {
            'incident': incident.to_dict(),
            'unit': unit.to_dict(),
            'user': current_user.to_dict(),
            'assignment': assignment.to_dict()
        })
        
        socketio.emit('unit_status_changed', {
            'unit': unit.to_dict(),
            'user': current_user.to_dict(),
            'old_status': 'AVAILABLE',
            'new_status': 'ASSIGNED'
        })
        
        return jsonify({
            'success': True,
            'message': f'Unit {unit.name} assigned to incident',
            'assignment': assignment.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB_OPERATION: Error assigning unit: {str(e)} | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error assigning unit: {str(e)}'}), 500

@api.route('/incidents/<int:incident_id>/clear-unit', methods=['POST'])
@login_required
@permission_required(Permission.ASSIGN_UNITS)
@secure_endpoint(limit="30/minute")
def clear_unit_from_incident(incident_id):
    """Clear a unit from an incident."""
    try:
        incident = Incident.query.get(incident_id)
        
        if not incident:
            current_app.logger.warning(f"DB_OPERATION: Failed to clear unit - incident not found | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Incident not found'}), 404
            
        data = request.get_json()
        
        if 'unit_id' not in data:
            current_app.logger.warning(f"DB_OPERATION: Failed to clear unit - missing unit_id | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Missing required field: unit_id'}), 400
            
        unit_id = data['unit_id']
        
        # Check if unit exists
        unit = Unit.query.get(unit_id)
        if not unit:
            current_app.logger.warning(f"DB_OPERATION: Failed to clear unit - unit not found | Unit ID: {unit_id} | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Unit not found'}), 404
            
        # Check if unit is assigned to this incident
        assignment = UnitAssignment.query.filter_by(
            incident_id=incident_id,
            unit_id=unit_id,
            active=True
        ).first()
        
        if not assignment:
            current_app.logger.warning(f"DB_OPERATION: Unit not assigned to incident | Unit ID: {unit_id} | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
            return jsonify({'success': False, 'message': 'Unit is not assigned to this incident'}), 400
            
        # Log the clear operation
        current_app.logger.info(f"DB_OPERATION: Clearing unit from incident | Unit ID: {unit_id} | Unit Name: {unit.name} | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        
        # Clear assignment
        assignment.active = False
        assignment.cleared_by = current_user.id
        assignment.clearance_time = datetime.utcnow()
        
        # Update unit status
        old_status = unit.status
        unit.status = 'AVAILABLE'
        unit.last_status_change = datetime.utcnow()
        unit.current_incident_id = None
        
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Unit cleared successfully | Unit ID: {unit_id} | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        current_app.logger.info(f"DB_OPERATION: Unit status updated from {old_status} to AVAILABLE | Unit ID: {unit_id}")
        
        # Add log entry
        log_entry = IncidentLog(
            incident_id=incident.id,
            message=f"Unit {unit.name} cleared by {current_user.username}",
            log_type='UNIT',
            created_by=current_user.id
        )
        db.session.add(log_entry)
        db.session.commit()
        current_app.logger.info(f"DB_OPERATION: Unit clearance log entry created | Incident ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        
        # Emit WebSocket events
        socketio.emit('incident_unit_cleared', {
            'incident': incident.to_dict(),
            'unit': unit.to_dict(),
            'user': current_user.to_dict(),
            'assignment': assignment.to_dict()
        })
        
        socketio.emit('unit_status_changed', {
            'unit': unit.to_dict(),
            'user': current_user.to_dict(),
            'old_status': old_status,
            'new_status': 'AVAILABLE'
        })
        
        return jsonify({
            'success': True,
            'message': f'Unit {unit.name} cleared from incident',
            'assignment': assignment.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"DB_OPERATION: Error clearing unit: {str(e)} | ID: {incident_id} | User: {current_user.username} ({current_user.id})")
        return jsonify({'success': False, 'message': f'Error clearing unit: {str(e)}'}), 500

@api.route('/api/incidents/next-case-number', methods=['GET'])
@login_required
@read_endpoint(limit="30/minute")
def get_next_case_number():
    """Get the next available case number for a new incident."""
    try:
        # Generate next case number based on current date and sequential counter
        current_date = datetime.now()
        date_prefix = current_date.strftime('%Y%m%d')
        
        # Find the highest case number with today's prefix
        latest_incident = Incident.query.filter(
            Incident.incident_number.like(f'{date_prefix}%')
        ).order_by(Incident.incident_number.desc()).first()
        
        if latest_incident and latest_incident.incident_number:
            # Extract the sequence number and increment
            try:
                sequence = int(latest_incident.incident_number[-4:]) + 1
            except ValueError:
                # If for some reason we can't parse the sequence, start at 1
                sequence = 1
        else:
            # No incidents today yet, start at 1
            sequence = 1
            
        # Format as YYYYMMDD-XXXX
        case_number = f"{date_prefix}-{sequence:04d}"
        
        current_app.logger.info(f"Generated next case number: {case_number} | User: {current_user.username} ({current_user.id})")
        
        return jsonify({
            'success': True,
            'caseNumber': case_number
        })
        
    except Exception as e:
        current_app.logger.error(f"Error generating case number: {str(e)} | User: {current_user.username} ({current_user.id})")
        return jsonify({
            'success': False,
            'message': f'Error generating case number: {str(e)}'
        }), 500
