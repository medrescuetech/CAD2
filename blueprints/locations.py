"""
Location Services Blueprint

This module provides endpoints for managing locations, pickup points,
geocoding services, and location search functionality.
"""

from flask import Blueprint, request, jsonify, render_template, current_app, send_file
from flask_login import login_required, current_user
from models import db, Location, PickupPoint, Unit, Permission
from utils.decorators import permission_required
from utils.security import secure_endpoint, validate_coordinates
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
from utils.validation import validate_coordinates
from sqlalchemy import or_

import os
import csv
import io
from datetime import datetime
import requests
import geopy.distance
from geopy.geocoders import Nominatim

bp = Blueprint('locations', __name__)

# Configure geocoding service
geolocator = Nominatim(user_agent="cad_system_geocoder")

# Standard Locations Endpoints
@bp.route('/locations', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def get_locations():
    """Get locations with optional filtering."""
    # Get query parameters
    query = request.args.get('q', '')
    active_param = request.args.get('active', 'true')
    
    # Parse active parameter
    if active_param.lower() == 'true':
        active_filter = True
    elif active_param.lower() == 'false':
        active_filter = False
    else:
        active_filter = None  # All locations, regardless of active status
    
    # Build query
    locations_query = Location.query
    
    # Apply active filter if specified
    if active_filter is not None:
        locations_query = locations_query.filter(Location.active == active_filter)
    
    # Apply search filter if provided
    if query:
        locations_query = locations_query.filter(Location.name.ilike(f'%{query}%'))
    
    # Execute query and get results
    locations = locations_query.all()
    
    # Format results
    results = [location.to_dict() for location in locations]
    
    return jsonify({
        'success': True,
        'locations': results
    })

@bp.route('/locations/<int:location_id>', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def get_location(location_id):
    """Get a specific location by ID."""
    location = Location.query.get_or_404(location_id)
    
    return jsonify({
        'success': True,
        'location': location.to_dict()
    })

@bp.route('/locations', methods=['POST'])
@login_required
@permission_required(Permission.EDIT_INCIDENT)
@secure_endpoint(limit="10/minute")
def create_location():
    """Create a new location."""
    data = request.get_json()
    
    # Validate required fields
    if not data or not data.get('name'):
        return jsonify({
            'success': False,
            'message': 'Location name is required'
        }), 400
    
    # Validate coordinates if provided
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    
    if latitude is not None and longitude is not None:
        if not validate_coordinates(latitude, longitude):
            return jsonify({
                'success': False,
                'message': 'Invalid coordinates'
            }), 400
    else:
        return jsonify({
            'success': False,
            'message': 'Latitude and longitude are required'
        }), 400
    
    # Create new location
    new_location = Location(
        name=data['name'],
        latitude=latitude,
        longitude=longitude,
        active=data.get('active', True)
    )
    
    db.session.add(new_location)
    db.session.commit()
    
    # Log audit event
    log_audit_event(
        category=getattr(AuditCategory, 'LOCATION', AuditCategory.SECURITY),
        severity=AuditSeverity.INFO,
        message=f"Created new location: {new_location.name}",
        user_id=current_user.id
    )
    
    return jsonify({
        'success': True,
        'message': 'Location created successfully',
        'location': new_location.to_dict()
    })

@bp.route('/locations/<int:location_id>', methods=['PUT'])
@login_required
@permission_required(Permission.EDIT_INCIDENT)
@secure_endpoint(limit="10/minute")
def update_location(location_id):
    """Update an existing location."""
    location = Location.query.get_or_404(location_id)
    data = request.get_json()
    
    # Validate required fields
    if not data:
        return jsonify({
            'success': False,
            'message': 'No data provided'
        }), 400
    
    # Update fields
    if 'name' in data:
        location.name = data['name']
    
    # Validate coordinates if provided
    if 'latitude' in data and 'longitude' in data:
        latitude = data['latitude']
        longitude = data['longitude']
        
        if not validate_coordinates(latitude, longitude):
            return jsonify({
                'success': False,
                'message': 'Invalid coordinates'
            }), 400
        
        location.latitude = latitude
        location.longitude = longitude
    
    # Update active status if provided
    if 'active' in data:
        location.active = bool(data['active'])
    
    location.updated_at = datetime.utcnow()
    db.session.commit()
    
    # Log audit event
    log_audit_event(
        category=getattr(AuditCategory, 'LOCATION', AuditCategory.SECURITY),
        severity=AuditSeverity.INFO,
        message=f"Updated location: {location.name}",
        user_id=current_user.id
    )
    
    return jsonify({
        'success': True,
        'message': 'Location updated successfully',
        'location': location.to_dict()
    })

@bp.route('/locations/<int:location_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="5/minute")
def delete_location(location_id):
    """Delete a location."""
    location = Location.query.get_or_404(location_id)
    
    location_name = location.name
    db.session.delete(location)
    db.session.commit()
    
    # Log audit event
    log_audit_event(
        category=getattr(AuditCategory, 'LOCATION', AuditCategory.SECURITY),
        severity=AuditSeverity.WARNING,
        message=f"Deleted location: {location_name}",
        user_id=current_user.id
    )
    
    return jsonify({
        'success': True,
        'message': 'Location deleted successfully'
    })

@bp.route('/locations/import', methods=['POST'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="2/minute")
def import_locations():
    """Import locations from a CSV file."""
    if 'file' not in request.files:
        return jsonify({
            'success': False,
            'message': 'No file part in the request'
        }), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({
            'success': False,
            'message': 'No file selected'
        }), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({
            'success': False,
            'message': 'File must be a CSV'
        }), 400
    
    # Process CSV file
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)
        
        imported_count = 0
        error_count = 0
        errors = []
        
        for row in csv_reader:
            try:
                # Validate row data
                if not row.get('name'):
                    errors.append(f"Row {csv_reader.line_num}: Missing name")
                    error_count += 1
                    continue
                
                # Validate coordinates
                try:
                    latitude = float(row.get('latitude', ''))
                    longitude = float(row.get('longitude', ''))
                    
                    if not validate_coordinates(latitude, longitude):
                        errors.append(f"Row {csv_reader.line_num}: Invalid coordinates")
                        error_count += 1
                        continue
                except ValueError:
                    errors.append(f"Row {csv_reader.line_num}: Invalid coordinates format")
                    error_count += 1
                    continue
                
                # Parse active status
                active = row.get('active', 'true').lower() == 'true'
                
                # Check if location with the same name already exists
                existing_location = Location.query.filter_by(name=row['name']).first()
                
                if existing_location:
                    # Update existing location
                    existing_location.latitude = latitude
                    existing_location.longitude = longitude
                    existing_location.active = active
                    existing_location.updated_at = datetime.utcnow()
                else:
                    # Create new location
                    new_location = Location(
                        name=row['name'],
                        latitude=latitude,
                        longitude=longitude,
                        active=active
                    )
                    db.session.add(new_location)
                
                imported_count += 1
            
            except Exception as e:
                errors.append(f"Row {csv_reader.line_num}: {str(e)}")
                error_count += 1
        
        db.session.commit()
        
        # Log audit event
        log_audit_event(
            category=getattr(AuditCategory, 'LOCATION', AuditCategory.SECURITY),
            severity=AuditSeverity.INFO,
            message=f"Imported {imported_count} locations from CSV",
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True,
            'message': f"Successfully imported {imported_count} locations with {error_count} errors",
            'imported_count': imported_count,
            'error_count': error_count,
            'errors': errors
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error processing CSV file: {str(e)}"
        }), 500

@bp.route('/locations/export', methods=['GET'])
@login_required
@permission_required(Permission.EDIT_INCIDENT)
@secure_endpoint(limit="2/minute")
def export_locations():
    """Export locations to a CSV file."""
    # Get query parameters for filtering
    active_param = request.args.get('active', None)
    
    # Build query
    locations_query = Location.query
    
    # Apply active filter if specified
    if active_param is not None:
        active_filter = active_param.lower() == 'true'
        locations_query = locations_query.filter(Location.active == active_filter)
    
    # Get all locations
    locations = locations_query.all()
    
    # Create CSV in memory
    output = io.StringIO()
    csv_writer = csv.writer(output)
    
    # Write header
    csv_writer.writerow(['id', 'name', 'latitude', 'longitude', 'active', 'created_at', 'updated_at'])
    
    # Write data
    for location in locations:
        csv_writer.writerow([
            location.id,
            location.name,
            location.latitude,
            location.longitude,
            str(location.active).lower(),
            location.created_at.isoformat() if location.created_at else '',
            location.updated_at.isoformat() if location.updated_at else ''
        ])
    
    # Prepare response
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Log audit event
    log_audit_event(
        category=getattr(AuditCategory, 'LOCATION', AuditCategory.SECURITY),
        severity=AuditSeverity.INFO,
        message=f"Exported {len(locations)} locations to CSV",
        user_id=current_user.id
    )
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'locations_export_{timestamp}.csv'
    )

@bp.route('/locations/geocode', methods=['GET'])
@login_required
@secure_endpoint(limit="10/minute")
def geocode():
    """Geocode an address to get coordinates."""
    address = request.args.get('address', '')
    
    if not address:
        return jsonify({
            'success': False,
            'message': 'Address is required'
        }), 400
    
    try:
        location = geolocator.geocode(address)
        
        if not location:
            return jsonify({
                'success': False,
                'message': 'Could not geocode address'
            }), 404
        
        result = {
            'latitude': location.latitude,
            'longitude': location.longitude,
            'address': location.address
        }
        
        return jsonify({
            'success': True,
            'result': result
        })
    
    except Exception as e:
        current_app.logger.error(f"Geocoding error: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Geocoding error: {str(e)}"
        }), 500

@bp.route('/locations/reverse_geocode', methods=['GET'])
@login_required
@secure_endpoint(limit="10/minute")
def reverse_geocode():
    """Reverse geocode coordinates to get an address."""
    try:
        lat = request.args.get('lat', type=float)
        lng = request.args.get('lng', type=float)
        
        if lat is None or lng is None:
            return jsonify({
                'success': False,
                'message': 'Latitude and longitude are required'
            }), 400
        
        if not validate_coordinates(lat, lng):
            return jsonify({
                'success': False,
                'message': 'Invalid coordinates'
            }), 400
        
        location = geolocator.reverse((lat, lng))
        
        if not location:
            return jsonify({
                'success': False,
                'message': 'Could not reverse geocode coordinates'
            }), 404
        
        result = {
            'address': location.address,
            'raw': location.raw
        }
        
        return jsonify({
            'success': True,
            'result': result
        })
    
    except Exception as e:
        current_app.logger.error(f"Reverse geocoding error: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Reverse geocoding error: {str(e)}"
        }), 500

@bp.route('/admin/locations', methods=['GET'])
@login_required
@permission_required(Permission.ADMIN)
def admin_locations():
    """Render the admin locations page."""
    # Get all locations
    locations = Location.query.all()
    
    # Get locations that need review (e.g., newly created)
    locations_for_review = Location.query.filter_by(needs_review=True).all()
    
    return render_template(
        'admin/locations.html',
        locations=locations,
        locations_for_review=locations_for_review
    )

@bp.route('/locations/nearby', methods=['GET'])
@login_required
@secure_endpoint(limit="10/minute")
def get_nearby_locations():
    """Get locations near a specific point within a given radius."""
    try:
        lat = request.args.get('lat', type=float)
        lng = request.args.get('lng', type=float)
        radius = request.args.get('radius', default=5, type=float)  # Default 5km radius
        
        if lat is None or lng is None:
            return jsonify({
                'success': False,
                'message': 'Latitude and longitude are required'
            }), 400
        
        if not validate_coordinates(lat, lng):
            return jsonify({
                'success': False,
                'message': 'Invalid coordinates'
            }), 400
        
        # Get all locations
        locations = Location.query.filter_by(active=True).all()
        
        # Filter locations by distance
        nearby_locations = []
        
        for location in locations:
            distance = geopy.distance.distance(
                (lat, lng),
                (location.latitude, location.longitude)
            ).kilometers
            
            if distance <= radius:
                location_dict = location.to_dict()
                location_dict['distance'] = round(distance, 2)
                nearby_locations.append(location_dict)
        
        # Sort by distance
        nearby_locations.sort(key=lambda x: x['distance'])
        
        return jsonify({
            'success': True,
            'locations': nearby_locations
        })
    
    except Exception as e:
        current_app.logger.error(f"Error finding nearby locations: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error finding nearby locations: {str(e)}"
        }), 500

# Pickup Points Endpoints
@bp.route('/pickup-points', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def get_pickup_points():
    """Get all pickup points or search for pickup points by name."""
    try:
        search_query = request.args.get('q', '')
        active_only = request.args.get('active', 'true').lower() == 'true'
        
        query = PickupPoint.query
        
        if search_query:
            query = query.filter(
                or_(
                    PickupPoint.name.ilike(f"%{search_query}%"),
                    PickupPoint.location.ilike(f"%{search_query}%"),
                    PickupPoint.description.ilike(f"%{search_query}%")
                )
            )
            
        if active_only:
            query = query.filter_by(active=True)
            
        pickup_points = query.order_by(PickupPoint.name).all()
        
        return jsonify({
            'success': True,
            'pickup_points': [pp.to_dict() for pp in pickup_points],
            'count': len(pickup_points)
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving pickup points: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving pickup points: {str(e)}"
        }), 500

@bp.route('/pickup-points/<int:pickup_point_id>', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def get_pickup_point(pickup_point_id):
    """Get a specific pickup point by ID."""
    try:
        pickup_point = PickupPoint.query.get_or_404(pickup_point_id)
        
        return jsonify({
            'success': True,
            'pickup_point': pickup_point.to_dict()
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving pickup point: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving pickup point: {str(e)}"
        }), 500

@bp.route('/pickup-points', methods=['POST'])
@login_required
@permission_required(Permission.EDIT_INCIDENT)
@secure_endpoint(limit="15/minute")
def create_pickup_point():
    """Create a new pickup point."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': "Missing JSON data"
            }), 400
        
        name = data.get('name')
        location = data.get('location')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if not name or not location or latitude is None or longitude is None:
            return jsonify({
                'success': False,
                'message': "Name, location, latitude, and longitude are required"
            }), 400
        
        # Validate coordinates
        if not validate_coordinates(latitude, longitude):
            return jsonify({
                'success': False,
                'message': "Invalid coordinates provided"
            }), 400
            
        # Check if pickup point already exists
        existing = PickupPoint.query.filter_by(name=name).first()
        if existing:
            return jsonify({
                'success': False,
                'message': f"Pickup point with name '{name}' already exists"
            }), 409
        
        # Create new pickup point
        pickup_point = PickupPoint(
            name=name,
            location=location,
            latitude=float(latitude),
            longitude=float(longitude),
            description=data.get('description', ''),
            active=data.get('active', True)
        )
        
        db.session.add(pickup_point)
        db.session.commit()
        
        # Log audit event
        log_audit_event(
            category=AuditCategory.LOCATION,
            severity=AuditSeverity.INFO,
            message=f"Created new pickup point: {name}",
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True,
            'message': f"Pickup point '{name}' created successfully",
            'pickup_point': pickup_point.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating pickup point: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error creating pickup point: {str(e)}"
        }), 500

@bp.route('/pickup-points/<int:pickup_point_id>', methods=['PUT'])
@login_required
@permission_required(Permission.EDIT_INCIDENT)
@secure_endpoint(limit="15/minute")
def update_pickup_point(pickup_point_id):
    """Update an existing pickup point."""
    try:
        pickup_point = PickupPoint.query.get_or_404(pickup_point_id)
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': "Missing JSON data"
            }), 400
        
        # Update fields if provided
        if 'name' in data:
            # Check if name already exists for another pickup point
            existing = PickupPoint.query.filter(
                PickupPoint.name == data['name'], 
                PickupPoint.id != pickup_point_id
            ).first()
            
            if existing:
                return jsonify({
                    'success': False,
                    'message': f"Pickup point with name '{data['name']}' already exists"
                }), 409
                
            pickup_point.name = data['name']
            
        if 'location' in data:
            pickup_point.location = data['location']
            
        if 'latitude' in data and 'longitude' in data:
            latitude = data['latitude']
            longitude = data['longitude']
            
            # Validate coordinates
            if not validate_coordinates(latitude, longitude):
                return jsonify({
                    'success': False,
                    'message': "Invalid coordinates provided"
                }), 400
                
            pickup_point.latitude = float(latitude)
            pickup_point.longitude = float(longitude)
        
        if 'description' in data:
            pickup_point.description = data['description']
            
        if 'active' in data:
            pickup_point.active = data['active']
        
        pickup_point.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Log audit event
        log_audit_event(
            category=AuditCategory.LOCATION,
            severity=AuditSeverity.INFO,
            message=f"Updated pickup point: {pickup_point.name}",
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True,
            'message': f"Pickup point '{pickup_point.name}' updated successfully",
            'pickup_point': pickup_point.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating pickup point: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error updating pickup point: {str(e)}"
        }), 500

@bp.route('/pickup-points/<int:pickup_point_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="10/minute")
def delete_pickup_point(pickup_point_id):
    """Delete a pickup point."""
    try:
        pickup_point = PickupPoint.query.get_or_404(pickup_point_id)
        
        # Instead of deleting, mark as inactive
        pickup_point.active = False
        pickup_point.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Log audit event
        log_audit_event(
            category=AuditCategory.LOCATION,
            severity=AuditSeverity.WARNING,
            message=f"Deactivated pickup point: {pickup_point.name}",
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True,
            'message': f"Pickup point '{pickup_point.name}' deactivated successfully"
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deactivating pickup point: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error deactivating pickup point: {str(e)}"
        }), 500

# Geocoding Services
@bp.route('/geocode-address', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def geocode_address():
    """Geocode an address to get coordinates."""
    try:
        address = request.args.get('address')
        
        if not address:
            return jsonify({
                'success': False,
                'message': "Address parameter is required"
            }), 400
        
        # Mock implementation for geocoding
        # In a real implementation, you would call an external geocoding service
        # such as Google Maps, Mapbox, or OpenStreetMap Nominatim
        
        # Simulate a geocoding response
        import random
        
        # Use fixed coordinates for testing
        mock_results = {
            "123 Main St": (34.0522, -118.2437),  # Los Angeles
            "456 Park Ave": (40.7128, -74.0060),  # New York
            "789 Market St": (37.7749, -122.4194)  # San Francisco
        }
        
        # If we have a fixed result, use it, otherwise generate random nearby coordinates
        if address in mock_results:
            lat, lng = mock_results[address]
        else:
            # Generate a "random" result that's consistent for the same address
            # This uses a simple hash of the address to seed the random generator
            seed = sum(ord(c) for c in address)
            random.seed(seed)
            lat = 35.0 + random.uniform(-10, 10)
            lng = -100.0 + random.uniform(-20, 20)
        
        result = {
            'latitude': round(lat, 6),
            'longitude': round(lng, 6),
            'address': address,
            'confidence': 0.9,  # Mock confidence score
            'is_mock': True
        }
        
        return jsonify({
            'success': True,
            'result': result
        })
    except Exception as e:
        current_app.logger.error(f"Error geocoding address: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error geocoding address: {str(e)}"
        }), 500

@bp.route('/reverse-geocode-coords', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def reverse_geocode_coords():
    """Reverse geocode coordinates to get an address."""
    try:
        latitude = request.args.get('latitude')
        longitude = request.args.get('longitude')
        
        if not latitude or not longitude:
            return jsonify({
                'success': False,
                'message': "Latitude and longitude parameters are required"
            }), 400
        
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            return jsonify({
                'success': False,
                'message': "Latitude and longitude must be valid numbers"
            }), 400
        
        # Validate coordinates
        if not validate_coordinates(latitude, longitude):
            return jsonify({
                'success': False,
                'message': "Invalid coordinates provided"
            }), 400
        
        # Mock implementation for reverse geocoding
        # In a real implementation, you would call an external geocoding service
        
        # Mock result based on coordinates
        lat_rounded = round(latitude, 2)
        lng_rounded = round(longitude, 2)
        
        # Generate a mock address based on the coordinates
        mock_address = f"{abs(int(lat_rounded * 100))} {['North', 'South'][latitude < 0]} {['East', 'West'][longitude < 0]} St"
        mock_city = "Mockville"
        mock_state = "MS"
        mock_zip = f"{abs(int(lat_rounded * 100 + lng_rounded * 100)) % 90000 + 10000}"
        
        result = {
            'address': mock_address,
            'city': mock_city,
            'state': mock_state,
            'zip': mock_zip,
            'formatted_address': f"{mock_address}, {mock_city}, {mock_state} {mock_zip}",
            'latitude': latitude,
            'longitude': longitude,
            'confidence': 0.8,  # Mock confidence score
            'is_mock': True
        }
        
        return jsonify({
            'success': True,
            'result': result
        })
    except Exception as e:
        current_app.logger.error(f"Error reverse geocoding coordinates: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error reverse geocoding coordinates: {str(e)}"
        }), 500

# Location Search
@bp.route('/search', methods=['GET'])
@login_required
@secure_endpoint(limit="30/minute")
def search_locations():
    """Search for locations, pickup points, and generate suggestions."""
    try:
        query = request.args.get('q', '')
        
        if not query or len(query) < 2:
            return jsonify({
                'success': False,
                'message': "Search query must be at least 2 characters"
            }), 400
            
        # Search locations
        locations = Location.query.filter(
            Location.name.ilike(f"%{query}%"),
            Location.active == True
        ).order_by(Location.name).limit(10).all()
        
        # Search pickup points
        pickup_points = PickupPoint.query.filter(
            or_(
                PickupPoint.name.ilike(f"%{query}%"),
                PickupPoint.location.ilike(f"%{query}%"),
                PickupPoint.description.ilike(f"%{query}%")
            ),
            PickupPoint.active == True
        ).order_by(PickupPoint.name).limit(10).all()
        
        # Format results
        results = {
            'locations': [location.to_dict() for location in locations],
            'pickup_points': [pp.to_dict() for pp in pickup_points],
            'suggestions': []  # This would normally come from an address autocomplete service
        }
        
        # Mock suggestions
        if len(query) >= 3:
            # Generate some mock address suggestions based on the query
            mock_suggestions = [
                f"{query} Street, Anytown",
                f"{query} Avenue, Cityville",
                f"{query.title()} Boulevard, Metropolis"
            ]
            results['suggestions'] = mock_suggestions[:3]
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(locations) + len(pickup_points) + len(results['suggestions'])
        })
    except Exception as e:
        current_app.logger.error(f"Error searching locations: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error searching locations: {str(e)}"
        }), 500

# Add to PickupPoint model to make it work properly with the blueprint
def add_to_dict_method():
    """Add to_dict method to PickupPoint model if it's missing."""
    if not hasattr(PickupPoint, 'to_dict') or not callable(getattr(PickupPoint, 'to_dict')):
        def to_dict(self):
            """Convert pickup point to dictionary."""
            return {
                'id': self.id,
                'name': self.name,
                'location': self.location,
                'latitude': self.latitude,
                'longitude': self.longitude,
                'description': self.description,
                'active': self.active,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None
            }
        setattr(PickupPoint, 'to_dict', to_dict)

# Call the function to ensure PickupPoint has to_dict method
add_to_dict_method()
