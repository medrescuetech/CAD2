from datetime import datetime, timedelta
import random
import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from models import User, Role, Unit, Incident, UnitAssignment, DailyLog, Location, IncidentLog, Permission

def generate_test_data():
    """Generate test data for the CAD system."""
    app = create_app()
    
    with app.app_context():
        # Create roles
        Role.insert_roles()
        db.session.commit()
        
        # Get roles
        admin_role = Role.query.filter_by(name='administrator').first()
        user_role = Role.query.filter_by(name='user').first()
        
        # Create users if they don't exist
        test_users = [
            {
                'username': 'admin',
                'email': 'admin@example.com',
                'password': 'admin123',
                'first_name': 'Admin',
                'last_name': 'User',
                'role': admin_role,
                'active': True
            },
            {
                'username': 'dispatcher1',
                'email': 'dispatcher1@example.com',
                'password': 'dispatch123',
                'first_name': 'John',
                'last_name': 'Smith',
                'role': user_role,
                'active': True
            },
            {
                'username': 'dispatcher2',
                'email': 'dispatcher2@example.com',
                'password': 'dispatch123',
                'first_name': 'Jane',
                'last_name': 'Doe',
                'role': user_role,
                'active': True
            }
        ]
        
        users = []
        for user_data in test_users:
            user = User.query.filter_by(username=user_data['username']).first()
            if not user:
                user = User(**user_data)
                db.session.add(user)
            users.append(user)
        db.session.commit()
        
        # Create units if they don't exist
        unit_types = ['paramedic', 'critical care', 'fast attack', 'tanker', 'pumper', 'buggy', 'bike']
        units = []
        for i in range(1, 11):
            unit_number = f'UNIT-{i:03d}'
            existing_unit = Unit.query.filter_by(unit_number=unit_number).first()
            if not existing_unit:
                unit = Unit(
                    unit_number=unit_number,
                    unit_type=random.choice(unit_types),
                    status='available',
                    station=f'Station {random.randint(1, 5)}',
                    location='Base',
                    latitude=-33.8688 + random.uniform(-0.1, 0.1),
                    longitude=151.2093 + random.uniform(-0.1, 0.1),
                    active=True
                )
                db.session.add(unit)
                units.append(unit)
            else:
                units.append(existing_unit)
        db.session.commit()
        
        # Create locations if they don't exist
        test_locations = [
            ('Sydney CBD', -33.8688, 151.2093),
            ('Bondi Beach', -33.8915, 151.2767),
            ('Parramatta', -33.8150, 151.0011),
            ('Chatswood', -33.7967, 151.1800),
            ('Manly', -33.7969, 151.2850)
        ]
        
        locations = []
        for name, lat, lon in test_locations:
            location = Location.query.filter_by(name=name).first()
            if not location:
                location = Location(
                    name=name,
                    latitude=lat,
                    longitude=lon
                )
                db.session.add(location)
            locations.append(location)
        db.session.commit()
        
        # Create incidents if they don't exist
        incident_types = ['Medical', 'Fire', 'Rescue', 'Hazmat', 'Traffic Accident']
        priorities = [1, 2, 3]
        statuses = ['pending', 'open', 'closed']
        
        for i in range(1, 21):
            incident_number = f'INC-{i:05d}'
            existing_incident = Incident.query.filter_by(incident_number=incident_number).first()
            if not existing_incident:
                incident_type = random.choice(incident_types)
                priority = random.choice(priorities)
                status = random.choice(statuses)
                location = random.choice(locations)
                created_by = random.choice(users)
                
                # Generate a random time in the last 7 days
                created_at = datetime.utcnow() - timedelta(
                    days=random.randint(0, 7),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )
                
                incident = Incident(
                    incident_number=incident_number,
                    incident_type=incident_type,
                    priority=priority,
                    status=status,
                    location=location.name,
                    location_id=location.id,
                    latitude=location.latitude + random.uniform(-0.01, 0.01),
                    longitude=location.longitude + random.uniform(-0.01, 0.01),
                    description=f'Test incident {i} - {incident_type}',
                    created_by=created_by,
                    created_at=created_at
                )
                
                if status == 'closed':
                    incident.closed_at = created_at + timedelta(hours=random.randint(1, 8))
                    incident.closed_by = random.choice(users)
                
                db.session.add(incident)
                db.session.commit()
                
                # Add incident logs
                log_actions = ['CREATED', 'STATUS_CHANGE', 'UNIT_ASSIGNED', 'UNIT_CLEARED', 'NOTE_ADDED']
                for _ in range(random.randint(2, 5)):
                    log = IncidentLog(
                        incident=incident,
                        user=random.choice(users),
                        action=random.choice(log_actions),
                        details=f'Test log entry for incident {incident.incident_number}',
                        timestamp=created_at + timedelta(minutes=random.randint(0, 480))
                    )
                    db.session.add(log)
                
                # Assign units
                if status != 'pending':
                    num_units = random.randint(1, 3)
                    assigned_units = random.sample(units, num_units)
                    for unit in assigned_units:
                        assignment = UnitAssignment(
                            incident=incident,
                            unit=unit,
                            status='assigned' if status == 'open' else 'cleared',
                            dispatched_by=random.choice(users),
                            assigned_at=created_at + timedelta(minutes=random.randint(5, 30)),
                            notes=f'Unit {unit.unit_number} assigned to incident {incident.incident_number}'
                        )
                        db.session.add(assignment)
                
                db.session.commit()
        
        # Create daily logs
        shifts = ['Day', 'Night']
        for user in users:
            for day in range(7):
                log_date = datetime.utcnow().date() - timedelta(days=day)
                shift = random.choice(shifts)
                
                log = DailyLog(
                    date=log_date,
                    shift=shift,
                    user=user,
                    notes=f'Daily log for {user.username} on {log_date} ({shift} shift)'
                )
                db.session.add(log)
        
        db.session.commit()
        print("Test data generated successfully!")

if __name__ == '__main__':
    generate_test_data()
