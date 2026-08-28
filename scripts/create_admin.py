from werkzeug.security import generate_password_hash
import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import User, Role, Permission
from extensions import db

def create_admin_user():
    app = create_app()
    with app.app_context():
        # Create roles first
        Role.insert_roles()
        
        # Get admin role
        admin_role = Role.query.filter_by(name='Administrator').first()
        if not admin_role:
            print("Error: Administrator role not found")
            return
        
        # Delete existing admin user if it exists
        admin = User.query.filter_by(username='admin').first()
        if admin:
            print("Deleting existing admin user...")
            db.session.delete(admin)
            db.session.commit()
            
        # Create new admin user
        admin = User(
            username='admin',
            email='admin@example.com',
            first_name='System',
            last_name='Administrator',
            role_id=admin_role.id,
            active=True
        )
        admin.password = 'admin'  # This will use the password setter to hash
        
        db.session.add(admin)
        db.session.commit()
        print("Admin user created successfully")

if __name__ == '__main__':
    create_admin_user()
