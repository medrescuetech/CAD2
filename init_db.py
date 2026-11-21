from app import create_app
from extensions import db
from datetime import datetime, timedelta
from models import User, Role, Permission, Incident, Unit, IncidentLog, UnitAssignment, PickupPoint, DailyLog, UnitType, Location, IncidentType
from core.reference_data import insert_defaults as insert_core_reference_data
from werkzeug.security import generate_password_hash
import logging

def init_db():
    app = create_app()
    with app.app_context():
        # Drop all existing tables
        db.drop_all()
        
        # Create all tables
        db.create_all()
        
        # Create roles (lowercase names to match app.py)
        admin_role = Role(
            name='administrator',
            permissions=Permission.ADMINISTRATOR
        )
        
        dispatcher_role = Role(
            name='dispatcher',
            permissions=Permission.VIEW_SYSTEM_LOGS | Permission.VIEW_INCIDENTS | Permission.CREATE_INCIDENT | Permission.EDIT_INCIDENT
        )
        
        # Add roles to session first
        db.session.add(admin_role)
        db.session.add(dispatcher_role)
        db.session.flush()  # This ensures we get the role IDs
        
        # Create admin user (pass plain password - set_password will hash it)
        admin = User(
            username='admin',
            email='admin@localhost',
            password='admin',
            role=admin_role,
            first_name='System',
            last_name='Administrator',
            active=True
        )
        
        # Create test dispatcher (pass plain password - set_password will hash it)
        dispatcher = User(
            username='dispatcher',
            email='dispatcher@localhost',
            password='dispatcher',
            role=dispatcher_role,
            first_name='Dispatch',
            last_name='Operator',
            active=True
        )
        
        # Create unit types
        ambulance_type = UnitType(name='Ambulance', description='Emergency medical services')
        fire_engine_type = UnitType(name='Fire Engine', description='Fire suppression and rescue')
        police_type = UnitType(name='Police', description='Law enforcement')
        
        # Create locations with coordinates for major US cities
        central_station = Location(
            name='Central Station', 
            address='123 Main St, Chicago, IL 60601',
            latitude=41.8781,
            longitude=-87.6298,
            city='Chicago',
            state='IL',
            postal_code='60601',
            active=True
        )
        
        north_station = Location(
            name='North Station', 
            address='456 North Ave, New York, NY 10013',
            latitude=40.7128,
            longitude=-74.0060,
            city='New York',
            state='NY',
            postal_code='10013',
            active=True
        )
        
        south_station = Location(
            name='South Station', 
            address='789 South St, Houston, TX 77002',
            latitude=29.7604,
            longitude=-95.3698,
            city='Houston',
            state='TX',
            postal_code='77002',
            active=True
        )
        
        # Add unit types, locations, and users to session
        db.session.add(ambulance_type)
        db.session.add(fire_engine_type)
        db.session.add(police_type)
        db.session.add(central_station)
        db.session.add(north_station)
        db.session.add(south_station)
        db.session.add(admin)
        db.session.add(dispatcher)
        db.session.flush()  # Ensure we have IDs for the next step
        
        # Create units with proper relationships
        # location is a string column, location_id is the FK
        units = [
            Unit(
                name='AMB-101',
                type=ambulance_type,
                location=central_station.address,
                location_id=central_station.id,
                status='available',
                active=True
            ),
            Unit(
                name='ENG-201',
                type=fire_engine_type,
                location=north_station.address,
                location_id=north_station.id,
                status='available',
                active=True
            ),
            Unit(
                name='POL-301',
                type=police_type,
                location=south_station.address,
                location_id=south_station.id,
                status='available',
                active=True
            )
        ]
        
        # Add sample pickup points
        pickup_points = [
            PickupPoint(
                name='Central Hospital',
                location='123 Main St',
                latitude=40.7128,
                longitude=-74.0060,
                description='Main entrance of Central Hospital'
            ),
            PickupPoint(
                name='City Mall',
                location='456 Market St',
                latitude=40.7589,
                longitude=-73.9851,
                description='North entrance of City Mall'
            )
        ]
        
        # Create default incident types
        incident_types = [
            IncidentType(
                name='Medical Emergency',
                description='General medical emergency response',
                default_priority=2,
                color='#ff4444',
                requires_location=True,
                requires_caller=True,
                active=True
            ),
            IncidentType(
                name='Traffic Accident',
                description='Motor vehicle collision',
                default_priority=2,
                color='#ffbb33',
                requires_location=True,
                requires_caller=True,
                active=True
            ),
            IncidentType(
                name='Fire',
                description='Structure or vegetation fire',
                default_priority=1,
                color='#ff0000',
                requires_location=True,
                requires_caller=True,
                active=True
            ),
            IncidentType(
                name='Public Disturbance',
                description='Disorderly conduct or disturbance',
                default_priority=3,
                color='#33b5e5',
                requires_location=True,
                requires_caller=False,
                active=True
            )
        ]
        
        # Create sample incidents
        now = datetime.utcnow()
        incidents = [
            Incident(
                incident_number='INC-1001',
                incident_type_id=1,  # Medical Emergency
                priority=2,
                status='open',
                location='123 Oak Street',
                latitude=41.9000,
                longitude=-87.6244,
                caller='John Doe',
                callback_number='555-0101',
                description='Elderly male experiencing chest pain',
                created_by_id=dispatcher.id,
                created_at=now - timedelta(minutes=30)
            ),
            Incident(
                incident_number='INC-1002',
                incident_type_id=2,  # Traffic Accident
                priority=2,
                status='pending',
                location='Main St & 1st Ave',
                latitude=41.9012,
                longitude=-87.6234,
                caller='Jane Smith',
                callback_number='555-0202',
                description='Two-vehicle collision, no injuries reported',
                created_by_id=dispatcher.id,
                created_at=now - timedelta(minutes=15)
            )
        ]
        
        try:
            # Add all sample data
            db.session.add(admin)
            db.session.add(dispatcher)
            
            # Add units, locations, and types
            for unit in units:
                db.session.add(unit)
                
            for point in pickup_points:
                db.session.add(point)
                
            # Add incident types
            for incident_type in incident_types:
                db.session.add(incident_type)
                
            # Add incidents
            for incident in incidents:
                db.session.add(incident)
            
            # Create unit assignments for the first incident
            # Assign units to incidents
            if incidents and units:
                assignment = UnitAssignment(
                    unit=units[0],
                    incident=incidents[0],
                    status='assigned',
                    dispatched_by_id=dispatcher.id,
                    dispatched_at=now - timedelta(minutes=25),
                    notes='Initial dispatch for medical emergency'
                )
                db.session.add(assignment)
                
                # Add log entry for the assignment
                log_entry = IncidentLog(
                    incident=incidents[0],
                    user=dispatcher,
                    message=f'Unit {units[0].name} dispatched to the scene',
                    type='dispatch'
                )
                db.session.add(log_entry)
            
            # Commit changes
            db.session.commit()

            # Seed controlled dictionaries for the CAD ecosystem core
            insert_core_reference_data()

            logging.info("Database initialized successfully with sample data")
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error initializing database: {str(e)}")
            raise

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    init_db()
