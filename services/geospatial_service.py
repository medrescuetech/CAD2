"""
Geospatial Service Module

This module provides map and location-based services including:
- Map API integration
- Unit tracking on map
- Incident location display
- Location utilities

The module includes mock implementations for certain features that would typically
rely on external mapping/routing APIs in a production environment.
"""

from models import Unit, Incident, Location, PickupPoint
from extensions import db
from flask import current_app
import math
import json
from datetime import datetime, timedelta

class GeospatialService:
    """Service class for handling all map and location operations."""
    
    # Constants for the mock implementation
    EARTH_RADIUS_KM = 6371  # Earth radius in kilometers
    
    @staticmethod
    def get_unit_location(unit_id):
        """
        Get the current location of a unit. Since units don't have GPS onboard,
        this will use either the incident location the unit is assigned to, or
        the unit's default/home location.
        
        Args:
            unit_id: ID of the unit
            
        Returns:
            Dictionary containing latitude, longitude, and address information
        """
        unit = Unit.query.get(unit_id)
        if not unit:
            return None
            
        # Check if unit has an active assignment to an incident
        from models import UnitAssignment
        active_assignment = UnitAssignment.query.filter_by(
            unit_id=unit.id, active=True
        ).first()
        if active_assignment:
            incident = Incident.query.get(active_assignment.incident_id)
            if incident and incident.latitude and incident.longitude:
                return {
                    'unit_id': unit.id,
                    'unit_name': unit.name,
                    'latitude': incident.latitude,
                    'longitude': incident.longitude,
                    'address': incident.location,
                    'timestamp': datetime.utcnow().isoformat(),
                    'source': 'incident_assignment'
                }
        
        # Use the unit's location_id (FK to Location table)
        if unit.location_id:
            location = Location.query.get(unit.location_id)
            if location and location.latitude and location.longitude:
                return {
                    'unit_id': unit.id,
                    'unit_name': unit.name,
                    'latitude': location.latitude,
                    'longitude': location.longitude,
                    'address': location.address,
                    'timestamp': datetime.utcnow().isoformat(),
                    'source': 'home_location'
                }
                
        # If no home location, return the default location from config (e.g., department HQ)
        default_lat = current_app.config.get('DEFAULT_LATITUDE')
        default_lng = current_app.config.get('DEFAULT_LONGITUDE')
        default_address = current_app.config.get('DEFAULT_ADDRESS', 'Department Headquarters')
        
        if default_lat and default_lng:
            return {
                'unit_id': unit.id,
                'unit_name': unit.name,
                'latitude': default_lat,
                'longitude': default_lng,
                'address': default_address,
                'timestamp': datetime.utcnow().isoformat(),
                'source': 'default_location'
            }
            
        return None
    
    @staticmethod
    def get_all_units_locations():
        """
        Get locations for all active units.
        
        Returns:
            List of unit location dictionaries
        """
        units = Unit.query.filter_by(active=True).all()
        locations = []
        
        for unit in units:
            location = GeospatialService.get_unit_location(unit.id)
            if location:
                # Add unit status information
                location['status'] = unit.status
                location['status_timestamp'] = unit.updated_at.isoformat() if unit.updated_at else None
                # Add unit type for proper map icon selection
                if unit.type:
                    location['unit_type'] = unit.type.name
                    location['unit_icon'] = unit.type.icon if hasattr(unit.type, 'icon') else None
                locations.append(location)
                
        return locations
    
    @staticmethod
    def get_incident_location(incident_id):
        """
        Get the location of an incident.
        
        Args:
            incident_id: ID of the incident
            
        Returns:
            Dictionary containing latitude, longitude, and address information
        """
        incident = Incident.query.get(incident_id)
        if not incident or not incident.latitude or not incident.longitude:
            return None
            
        return {
            'incident_id': incident.id,
            'incident_number': incident.incident_number,
            'latitude': incident.latitude,
            'longitude': incident.longitude,
            'address': incident.location,
            'priority': incident.priority,
            'status': incident.status,
            'created_at': incident.created_at.isoformat(),
            'type': incident.incident_type
        }
    
    @staticmethod
    def get_all_active_incidents_locations():
        """
        Get locations for all active incidents.
        
        Returns:
            List of incident location dictionaries
        """
        # Get all incidents that are not closed
        incidents = Incident.query.filter(Incident.status != 'closed').all()
        locations = []
        
        for incident in incidents:
            location = GeospatialService.get_incident_location(incident.id)
            if location:
                locations.append(location)
                
        return locations
    
    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):
        """
        Calculate the distance between two points using the Haversine formula.
        
        Args:
            lat1: Latitude of point 1 (in degrees)
            lon1: Longitude of point 1 (in degrees)
            lat2: Latitude of point 2 (in degrees)
            lon2: Longitude of point 2 (in degrees)
            
        Returns:
            Distance in kilometers
        """
        # Convert coordinates from degrees to radians
        lat1_rad = math.radians(float(lat1))
        lon1_rad = math.radians(float(lon1))
        lat2_rad = math.radians(float(lat2))
        lon2_rad = math.radians(float(lon2))
        
        # Haversine formula
        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = GeospatialService.EARTH_RADIUS_KM * c
        
        return distance
    
    @staticmethod
    def find_nearest_units(incident_id, limit=5, max_distance=50):
        """
        Find the nearest units to an incident.
        
        Args:
            incident_id: ID of the incident
            limit: Maximum number of units to return
            max_distance: Maximum distance in kilometers
            
        Returns:
            List of unit dictionaries with distance information
        """
        incident_location = GeospatialService.get_incident_location(incident_id)
        if not incident_location:
            return []
            
        all_units = Unit.query.filter_by(active=True).all()
        units_with_distance = []
        
        from models import UnitAssignment
        for unit in all_units:
            # Skip units that are already assigned to this incident
            existing = UnitAssignment.query.filter_by(
                unit_id=unit.id, incident_id=incident_id, active=True
            ).first()
            if existing:
                continue
                
            unit_location = GeospatialService.get_unit_location(unit.id)
            if not unit_location:
                continue
                
            # Calculate distance
            distance = GeospatialService.calculate_distance(
                incident_location['latitude'], 
                incident_location['longitude'],
                unit_location['latitude'], 
                unit_location['longitude']
            )
            
            # Only include units within the max distance
            if distance <= max_distance:
                units_with_distance.append({
                    'unit_id': unit.id,
                    'unit_name': unit.name,
                    'unit_type': unit.type.name if unit.type else None,
                    'status': unit.status,
                    'distance_km': round(distance, 2),
                    'estimated_arrival_minutes': round(distance * 2), # Mock implementation: 2 min per km
                    'latitude': unit_location['latitude'],
                    'longitude': unit_location['longitude'],
                    'source': unit_location['source']
                })
                
        # Sort by distance and limit the results
        units_with_distance.sort(key=lambda x: x['distance_km'])
        return units_with_distance[:limit]
    
    @staticmethod
    def get_map_config():
        """
        Get map configuration settings for the frontend.
        
        Returns:
            Dictionary containing map settings
        """
        return {
            'default_center': {
                'lat': current_app.config.get('DEFAULT_LATITUDE', 40.7128),
                'lng': current_app.config.get('DEFAULT_LONGITUDE', -74.0060)
            },
            'default_zoom': current_app.config.get('DEFAULT_MAP_ZOOM', 12),
            'map_provider': current_app.config.get('MAP_PROVIDER', 'leaflet'),
            'api_key': current_app.config.get('MAP_API_KEY', ''),
            'geocoding_enabled': current_app.config.get('GEOCODING_ENABLED', True),
            'routing_enabled': current_app.config.get('ROUTING_ENABLED', True),
            'max_bounds': current_app.config.get('MAP_MAX_BOUNDS', None)
        }
    
    @staticmethod
    def mock_geocode_address(address):
        """
        Mock implementation of geocoding service.
        In a production environment, this would call an external geocoding API.
        
        Args:
            address: Address string to geocode
            
        Returns:
            Dictionary containing geocoded coordinates
        """
        # For testing, return mock coordinates based on address hash
        # In production, this would call a geocoding API
        address_hash = sum(ord(c) for c in address)
        
        # Generate deterministic but seemingly random coordinates
        # This is just for demonstration - real implementation would use a geocoding service
        base_lat = current_app.config.get('DEFAULT_LATITUDE', 40.7128)
        base_lng = current_app.config.get('DEFAULT_LONGITUDE', -74.0060)
        
        lat_offset = (address_hash % 100) / 500  # Small offset within ~0.2 degrees
        lng_offset = (address_hash % 100) / 500
        
        # Alternate positive and negative offsets based on hash
        if address_hash % 2 == 0:
            lat_offset = -lat_offset
        if address_hash % 3 == 0:
            lng_offset = -lng_offset
            
        return {
            'latitude': base_lat + lat_offset,
            'longitude': base_lng + lng_offset,
            'address': address,
            'accuracy': 'approximate',
            'source': 'mock_geocoder'
        }
    
    @staticmethod
    def mock_get_route(start_lat, start_lng, end_lat, end_lng):
        """
        Mock implementation of routing service.
        In a production environment, this would call an external routing API.
        
        Args:
            start_lat: Starting latitude
            start_lng: Starting longitude
            end_lat: Ending latitude
            end_lng: Ending longitude
            
        Returns:
            Dictionary containing route information
        """
        # Calculate direct distance
        distance = GeospatialService.calculate_distance(
            float(start_lat), float(start_lng),
            float(end_lat), float(end_lng)
        )
        
        # Mock travel time (2 minutes per km)
        travel_time_minutes = round(distance * 2)
        
        # Create a simple route - direct line with a few points in between
        route_points = []
        steps = 5
        
        for i in range(steps + 1):
            factor = i / steps
            lat = float(start_lat) + (float(end_lat) - float(start_lat)) * factor
            lng = float(start_lng) + (float(end_lng) - float(start_lng)) * factor
            
            # Add some random variation to make it look more like a real route
            # Skip first and last points to ensure the route starts and ends at the exact coordinates
            if 0 < i < steps:
                import random
                lat_variation = (random.random() - 0.5) * 0.01
                lng_variation = (random.random() - 0.5) * 0.01
                lat += lat_variation
                lng += lng_variation
                
            route_points.append([lat, lng])
            
        return {
            'distance_km': round(distance, 2),
            'duration_minutes': travel_time_minutes,
            'route_geometry': route_points,
            'start_address': f"{start_lat}, {start_lng}",
            'end_address': f"{end_lat}, {end_lng}",
            'source': 'mock_router'
        }
        
    @staticmethod
    def simulate_unit_movement(unit_id, target_lat, target_lng, speed_km_h=40):
        """
        Simulate unit movement towards a target location for visualization purposes.
        This is useful for demonstrations and testing the map tracking UI.
        
        Args:
            unit_id: ID of the unit to simulate
            target_lat: Target latitude
            target_lng: Target longitude
            speed_km_h: Speed in kilometers per hour
            
        Returns:
            Dictionary containing updated unit location and movement information
        """
        unit = Unit.query.get(unit_id)
        if not unit:
            return None
            
        # Get current unit location
        current_location = GeospatialService.get_unit_location(unit_id)
        if not current_location:
            return None
            
        current_lat = float(current_location['latitude'])
        current_lng = float(current_location['longitude'])
        
        # Calculate distance to target
        distance_km = GeospatialService.calculate_distance(
            current_lat, current_lng,
            float(target_lat), float(target_lng)
        )
        
        # Calculate time to arrival
        time_hours = distance_km / float(speed_km_h)
        arrival_minutes = int(time_hours * 60)
        
        # Calculate new position based on a small time step (simulate movement)
        # For demo purposes, move 1/10th of the way to the destination
        if distance_km > 0.1:  # Only move if not already very close
            move_factor = 0.1  # Move 10% of the remaining distance
            new_lat = current_lat + (float(target_lat) - current_lat) * move_factor
            new_lng = current_lng + (float(target_lng) - current_lng) * move_factor
            
            # Update the unit's location timestamp
            movement_timestamp = datetime.utcnow()
            
            return {
                'unit_id': unit_id,
                'unit_name': unit.name,
                'previous_latitude': current_lat,
                'previous_longitude': current_lng,
                'latitude': new_lat,
                'longitude': new_lng,
                'target_latitude': float(target_lat),
                'target_longitude': float(target_lng),
                'distance_remaining_km': round(distance_km * (1 - move_factor), 2),
                'estimated_arrival_minutes': arrival_minutes,
                'timestamp': movement_timestamp.isoformat(),
                'speed_km_h': speed_km_h,
                'status': unit.status,
                'is_moving': True
            }
        else:
            # Unit has effectively arrived at the destination
            return {
                'unit_id': unit_id,
                'unit_name': unit.name,
                'latitude': float(target_lat),
                'longitude': float(target_lng),
                'distance_remaining_km': 0,
                'estimated_arrival_minutes': 0,
                'timestamp': datetime.utcnow().isoformat(),
                'status': unit.status,
                'is_moving': False
            }
    
    @staticmethod
    def get_units_in_area(center_lat, center_lng, radius_km=10):
        """
        Find all units within a specific radius of a center point.
        
        Args:
            center_lat: Center point latitude
            center_lng: Center point longitude
            radius_km: Search radius in kilometers
            
        Returns:
            List of units within the specified radius
        """
        all_units = Unit.query.filter_by(active=True).all()
        units_in_area = []
        
        for unit in all_units:
            unit_location = GeospatialService.get_unit_location(unit.id)
            if not unit_location:
                continue
                
            # Calculate distance from center point
            distance = GeospatialService.calculate_distance(
                float(center_lat), float(center_lng),
                float(unit_location['latitude']), float(unit_location['longitude'])
            )
            
            if distance <= radius_km:
                unit_data = unit_location.copy()
                unit_data['distance_km'] = round(distance, 2)
                units_in_area.append(unit_data)
                
        # Sort by distance
        units_in_area.sort(key=lambda x: x['distance_km'])
        return units_in_area
        
    @staticmethod
    def get_incidents_in_area(center_lat, center_lng, radius_km=10, include_closed=False):
        """
        Find all incidents within a specific radius of a center point.
        
        Args:
            center_lat: Center point latitude
            center_lng: Center point longitude
            radius_km: Search radius in kilometers
            include_closed: Whether to include closed incidents
            
        Returns:
            List of incidents within the specified radius
        """
        query = Incident.query
        if not include_closed:
            query = query.filter(Incident.status != 'closed')
            
        all_incidents = query.all()
        incidents_in_area = []
        
        for incident in all_incidents:
            if not incident.latitude or not incident.longitude:
                continue
                
            # Calculate distance from center point
            distance = GeospatialService.calculate_distance(
                float(center_lat), float(center_lng),
                float(incident.latitude), float(incident.longitude)
            )
            
            if distance <= radius_km:
                incident_data = GeospatialService.get_incident_location(incident.id)
                if incident_data:
                    incident_data['distance_km'] = round(distance, 2)
                    incidents_in_area.append(incident_data)
                
        # Sort by distance
        incidents_in_area.sort(key=lambda x: x['distance_km'])
        return incidents_in_area
        
    @staticmethod
    def find_pickup_points_near_location(lat, lng, radius_km=2, limit=5):
        """
        Find pickup points near a location.
        
        Args:
            lat: Latitude
            lng: Longitude
            radius_km: Search radius in kilometers
            limit: Maximum number of results
            
        Returns:
            List of pickup points within the radius
        """
        pickup_points = PickupPoint.query.all()
        points_with_distance = []
        
        for point in pickup_points:
            if not point.latitude or not point.longitude:
                continue
                
            # Calculate distance
            distance = GeospatialService.calculate_distance(
                float(lat), float(lng),
                float(point.latitude), float(point.longitude)
            )
            
            if distance <= radius_km:
                points_with_distance.append({
                    'id': point.id,
                    'name': point.name,
                    'description': point.description,
                    'address': point.address,
                    'latitude': point.latitude,
                    'longitude': point.longitude,
                    'distance_km': round(distance, 2),
                    'access_info': point.access_info
                })
                
        # Sort by distance and limit results
        points_with_distance.sort(key=lambda x: x['distance_km'])
        return points_with_distance[:limit]
    
    @staticmethod
    def get_location_clusters(locations, cluster_radius_km=0.5):
        """
        Group locations into clusters based on proximity.
        Useful for map visualization to avoid overlapping markers.
        
        Args:
            locations: List of location dictionaries with lat/lng
            cluster_radius_km: Radius for clustering in kilometers
            
        Returns:
            List of cluster dictionaries
        """
        if not locations:
            return []
            
        clusters = []
        processed = set()
        
        for i, location in enumerate(locations):
            if i in processed:
                continue
                
            # Start a new cluster
            cluster = {
                'center': {
                    'latitude': float(location['latitude']),
                    'longitude': float(location['longitude'])
                },
                'count': 1,
                'items': [location]
            }
            processed.add(i)
            
            # Find all locations within cluster_radius_km
            for j, other_location in enumerate(locations):
                if j in processed or j == i:
                    continue
                    
                distance = GeospatialService.calculate_distance(
                    float(location['latitude']), float(location['longitude']),
                    float(other_location['latitude']), float(other_location['longitude'])
                )
                
                if distance <= cluster_radius_km:
                    cluster['items'].append(other_location)
                    cluster['count'] += 1
                    processed.add(j)
                    
            # Calculate cluster center (average of all points)
            if cluster['count'] > 1:
                avg_lat = sum(float(item['latitude']) for item in cluster['items']) / cluster['count']
                avg_lng = sum(float(item['longitude']) for item in cluster['items']) / cluster['count']
                cluster['center'] = {
                    'latitude': avg_lat,
                    'longitude': avg_lng
                }
                
            clusters.append(cluster)
            
        return clusters

# Additional helper function to be used in API endpoints
def get_map_data():
    """
    Get all map data for the frontend map display.
    
    Returns:
        Dictionary containing units and incidents for the map
    """
    units = GeospatialService.get_all_units_locations()
    incidents = GeospatialService.get_all_active_incidents_locations()
    config = GeospatialService.get_map_config()
    
    return {
        'units': units,
        'incidents': incidents,
        'config': config,
        'timestamp': datetime.utcnow().isoformat()
    }
