from app import app, db
from models import Role, User, Permission
import os

def recreate_database():
    with app.app_context():
        # Drop all tables
        print("Dropping all tables...")
        db.drop_all()
        
        # Create all tables
        print("Creating all tables...")
        db.create_all()
        
        # Insert roles
        print("Creating roles...")
        Role.insert_roles()
        
        # Create admin user
        admin_role = Role.query.filter_by(name='administrator').first()
        if admin_role is None:
            print("Error: Administrator role not found")
            return
            
        admin = User(
            username='admin',
            email='admin@example.com',
            password='admin',
            first_name='Admin',
            last_name='User',
            role=admin_role,
            active=True
        )
        
        db.session.add(admin)
        
        try:
            db.session.commit()
            print("Database recreated successfully!")
            print("Default admin credentials:")
            print("Username: admin")
            print("Password: admin")
            print("\nPlease change these credentials after first login!")
        except Exception as e:
            print(f"Error creating database: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    # Check if database file exists
    db_path = 'cad.db'
    if os.path.exists(db_path):
        # Skip confirmation in development
        if os.getenv('FLASK_ENV') == 'production':
            confirm = input(f"This will delete the existing database at {db_path}. Continue? (y/N): ")
            if confirm.lower() != 'y':
                print("Operation cancelled.")
                exit()
            
    recreate_database()
