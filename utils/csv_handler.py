import csv
import io
import re
from datetime import datetime
from models import User, Unit, Location, AMPDSProtocol, Role, UnitType
from extensions import db

class CSVHandler:
    @staticmethod
    def validate_coordinates(lat, lon):
        try:
            lat = float(lat)
            lon = float(lon)
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                return False
            # Ensure no more than 10 decimal places
            lat_str = f"{lat:.10f}"
            lon_str = f"{lon:.10f}"
            return True
        except ValueError:
            return False

    @staticmethod
    def import_locations(file_stream):
        try:
            # Skip header row
            next(file_stream)
            
            csv_reader = csv.reader(file_stream)
            locations_added = 0
            locations_updated = 0
            errors = []

            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    if len(row) != 3:
                        errors.append(f"Row {row_num}: Invalid number of columns")
                        continue

                    lat, lon, name = row
                    
                    if not CSVHandler.validate_coordinates(lat, lon):
                        errors.append(f"Row {row_num}: Invalid coordinates")
                        continue

                    # Check if location exists
                    location = Location.query.filter_by(name=name).first()
                    
                    if location:
                        location.latitude = float(lat)
                        location.longitude = float(lon)
                        locations_updated += 1
                    else:
                        location = Location(
                            name=name,
                            latitude=float(lat),
                            longitude=float(lon)
                        )
                        db.session.add(location)
                        locations_added += 1

                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")

            db.session.commit()
            return {
                'added': locations_added,
                'updated': locations_updated,
                'errors': errors
            }

        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def import_users(file):
        """Import users from CSV file."""
        try:
            reader = csv.DictReader(file)
            required_fields = ['username', 'email', 'first_name', 'last_name', 'role', 'active']
            
            if not all(field in reader.fieldnames for field in required_fields):
                return {'error': f'Missing required fields. Required: {", ".join(required_fields)}'}
                
            added = 0
            updated = 0
            errors = []
            
            for row in reader:
                try:
                    # Validate required fields
                    if not all(row.get(field) for field in required_fields):
                        errors.append(f'Row {reader.line_num}: Missing required field values')
                        continue
                        
                    # Validate email format
                    if not re.match(r"[^@]+@[^@]+\.[^@]+", row['email']):
                        errors.append(f'Row {reader.line_num}: Invalid email format')
                        continue
                        
                    # Validate role
                    role = Role.query.filter_by(name=row['role'].lower()).first()
                    if not role:
                        errors.append(f'Row {reader.line_num}: Invalid role "{row["role"]}"')
                        continue
                        
                    # Convert active to boolean
                    active = str(row['active']).lower() in ('true', '1', 'yes', 'y')
                    
                    # Find or create user
                    user = User.query.filter_by(username=row['username']).first()
                    
                    if user:
                        # Update existing user
                        user.email = row['email']
                        user.first_name = row['first_name']
                        user.last_name = row['last_name']
                        user.role = role
                        user.active = active
                        updated += 1
                    else:
                        # Create new user
                        user = User(
                            username=row['username'],
                            email=row['email'],
                            first_name=row['first_name'],
                            last_name=row['last_name'],
                            role=role,
                            active=active
                        )
                        # Set default password
                        user.password = 'cadsystem'
                        db.session.add(user)
                        added += 1
                        
                except Exception as e:
                    errors.append(f'Row {reader.line_num}: {str(e)}')
                    continue
                    
            db.session.commit()
            return {
                'added': added,
                'updated': updated,
                'errors': errors
            }
            
        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def import_units(file):
        """Import units from CSV file."""
        try:
            reader = csv.DictReader(file)
            required_fields = ['unit_number', 'unit_type', 'station', 'status', 'active']
            
            if not all(field in reader.fieldnames for field in required_fields):
                return {'error': f'Missing required fields. Required: {", ".join(required_fields)}'}
                
            added = 0
            updated = 0
            errors = []
            
            for row in reader:
                try:
                    # Validate required fields
                    if not all(row.get(field) for field in required_fields):
                        errors.append(f'Row {reader.line_num}: Missing required field values')
                        continue
                        
                    # Validate unit type
                    if row['unit_type'].lower() not in UnitType.values():
                        errors.append(f'Row {reader.line_num}: Invalid unit type "{row["unit_type"]}". Must be one of: {", ".join(UnitType.values())}')
                        continue
                        
                    # Convert active to boolean
                    active = str(row['active']).lower() in ('true', '1', 'yes', 'y')
                    
                    # Find or create unit
                    unit = Unit.query.filter_by(unit_number=row['unit_number']).first()
                    
                    if unit:
                        # Update existing unit
                        unit.unit_type = row['unit_type'].lower()
                        unit.station = row['station']
                        unit.status = row['status']
                        unit.active = active
                        updated += 1
                    else:
                        # Create new unit
                        unit = Unit(
                            unit_number=row['unit_number'],
                            unit_type=row['unit_type'].lower(),
                            station=row['station'],
                            status=row['status'],
                            active=active
                        )
                        db.session.add(unit)
                        added += 1
                        
                except Exception as e:
                    errors.append(f'Row {reader.line_num}: {str(e)}')
                    continue
                    
            db.session.commit()
            return {
                'added': added,
                'updated': updated,
                'errors': errors
            }
            
        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def import_ampds(file_stream):
        try:
            # Skip header row
            next(file_stream)
            
            csv_reader = csv.reader(file_stream)
            protocols_added = 0
            protocols_updated = 0
            errors = []

            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    if len(row) != 7:
                        errors.append(f"Row {row_num}: Invalid number of columns")
                        continue

                    unique_id, category, card_number, priority, subcategory, dispatch_advice, prearrival_pdf = row
                    
                    # Check if protocol exists
                    protocol = AMPDSProtocol.query.filter_by(unique_id=unique_id).first()
                    
                    if protocol:
                        protocol.category = category
                        protocol.card_number = card_number
                        protocol.priority = priority
                        protocol.subcategory = subcategory
                        protocol.dispatch_advice = dispatch_advice
                        protocol.prearrival_pdf = prearrival_pdf
                        protocols_updated += 1
                    else:
                        protocol = AMPDSProtocol(
                            unique_id=unique_id,
                            category=category,
                            card_number=card_number,
                            priority=priority,
                            subcategory=subcategory,
                            dispatch_advice=dispatch_advice,
                            prearrival_pdf=prearrival_pdf
                        )
                        db.session.add(protocol)
                        protocols_added += 1

                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")

            db.session.commit()
            return {
                'added': protocols_added,
                'updated': protocols_updated,
                'errors': errors
            }

        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def export_locations():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['latitude', 'longitude', 'name'])
        
        # Write data
        locations = Location.query.order_by(Location.name).all()
        for location in locations:
            writer.writerow([
                f"{location.latitude:.10f}",
                f"{location.longitude:.10f}",
                location.name
            ])
            
        return output.getvalue()
    
    @staticmethod
    def export_users():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['username', 'email', 'first_name', 'last_name', 'role', 'active'])
        
        # Write data
        users = User.query.order_by(User.username).all()
        for user in users:
            writer.writerow([
                user.username,
                user.email,
                user.first_name,
                user.last_name,
                user.role.name,
                str(user.active).lower()
            ])
            
        return output.getvalue()
    
    @staticmethod
    def export_units():
        """Export units to CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['unit_number', 'unit_type', 'station', 'status', 'active'])
        
        # Write data
        units = Unit.query.order_by(Unit.unit_number).all()
        for unit in units:
            writer.writerow([
                unit.unit_number,
                unit.unit_type,
                unit.station,
                unit.status,
                str(unit.active).lower()
            ])
            
        return output.getvalue()
    
    @staticmethod
    def export_ampds():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['unique_id', 'category', 'card_number', 'priority', 'subcategory', 'dispatch_advice', 'prearrival_pdf'])
        
        # Write data
        protocols = AMPDSProtocol.query.order_by(AMPDSProtocol.card_number).all()
        for protocol in protocols:
            writer.writerow([
                protocol.unique_id,
                protocol.category,
                protocol.card_number,
                protocol.priority,
                protocol.subcategory,
                protocol.dispatch_advice,
                protocol.prearrival_pdf
            ])
            
        return output.getvalue()
