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
            required_fields = ['username', 'email']
            optional_fields = ['first_name', 'last_name', 'role', 'active', 'password']

            if not reader.fieldnames or not all(field in reader.fieldnames for field in required_fields):
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

                    # Resolve role (optional, case-insensitive); fall back to the first role
                    role = None
                    if row.get('role'):
                        role = Role.query.filter(
                            db.func.lower(Role.name) == row['role'].strip().lower()
                        ).first()
                        if not role:
                            errors.append(f'Row {reader.line_num}: Invalid role "{row["role"]}"')
                            continue
                    if not role:
                        role = Role.query.order_by(Role.id).first()
                        if not role:
                            errors.append(f'Row {reader.line_num}: No roles configured')
                            continue

                    # Convert active to boolean (default true)
                    active = str(row.get('active', 'true')).lower() in ('true', '1', 'yes', 'y')

                    # Find or create user
                    user = User.query.filter_by(username=row['username']).first()

                    if user:
                        # Update existing user
                        user.email = row['email']
                        user.first_name = row.get('first_name') or user.first_name
                        user.last_name = row.get('last_name') or user.last_name
                        user.role = role
                        user.active = active
                        if row.get('password'):
                            user.set_password(row['password'])
                        updated += 1
                    else:
                        email_owner = User.query.filter_by(email=row['email']).first()
                        if email_owner:
                            errors.append(f'Row {reader.line_num}: Email "{row["email"]}" already used by "{email_owner.username}"')
                            continue
                        user = User(
                            username=row['username'],
                            email=row['email'],
                            first_name=row.get('first_name', ''),
                            last_name=row.get('last_name', ''),
                            role=role,
                            active=active,
                            password=row.get('password') or 'cadsystem'
                        )
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
            required_fields = ['name']

            if not reader.fieldnames or not all(field in reader.fieldnames for field in required_fields):
                return {'error': f'Missing required fields. Required: {", ".join(required_fields)}. Optional: type, location, status, active'}

            added = 0
            updated = 0
            errors = []

            for row in reader:
                try:
                    if not row.get('name'):
                        errors.append(f'Row {reader.line_num}: Missing required field values')
                        continue

                    # Resolve unit type by name (optional); create it if unknown
                    unit_type = None
                    if row.get('type'):
                        type_name = row['type'].strip()
                        unit_type = UnitType.query.filter(
                            db.func.lower(UnitType.name) == type_name.lower()
                        ).first()
                        if not unit_type:
                            unit_type = UnitType(name=type_name)
                            db.session.add(unit_type)
                            db.session.flush()

                    # Convert active to boolean (default true)
                    active = str(row.get('active', 'true')).lower() in ('true', '1', 'yes', 'y')

                    # Find or create unit (upsert by name)
                    unit = Unit.query.filter_by(name=row['name']).first()

                    if unit:
                        unit.type = unit_type or unit.type
                        unit.location = row.get('location') or unit.location
                        unit.status = row.get('status') or unit.status
                        unit.active = active
                        updated += 1
                    else:
                        unit = Unit(
                            name=row['name'],
                            type=unit_type,
                            location=row.get('location', ''),
                            status=row.get('status') or 'available',
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
        writer.writerow(['name', 'type', 'location', 'status', 'active'])

        # Write data
        units = Unit.query.order_by(Unit.name).all()
        for unit in units:
            writer.writerow([
                unit.name,
                unit.type.name if unit.type else '',
                unit.location or '',
                unit.status or '',
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
