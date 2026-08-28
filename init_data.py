from app import create_app
from models import UnitType, Role
from extensions import db

def init_data():
    app = create_app()
    with app.app_context():
        # Create all database tables
        db.create_all()
        
        # Insert default unit types
        UnitType.insert_defaults()
        
        # Insert default roles
        Role.insert_roles()

if __name__ == '__main__':
    init_data()
