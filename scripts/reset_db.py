from app import create_app, db
from models import Role, Permission, User

def reset_database():
    """Reset the database and create initial data."""
    app = create_app()
    with app.app_context():
        # Drop and recreate all tables
        db.drop_all()
        db.create_all()
        
        # Create default roles
        admin_role = Role(name='Administrator')
        admin_role.permissions = Permission.ADMINISTRATOR
        
        dispatcher_role = Role(name='Dispatcher')
        dispatcher_role.permissions = (
            Permission.VIEW_INCIDENTS |
            Permission.CREATE_INCIDENTS |
            Permission.EDIT_INCIDENTS |
            Permission.VIEW_UNITS |
            Permission.EDIT_UNITS |
            Permission.VIEW_REPORTS |
            Permission.GENERATE_REPORTS
        )
        
        user_role = Role(name='User')
        user_role.permissions = (
            Permission.VIEW_INCIDENTS |
            Permission.VIEW_UNITS
        )
        
        db.session.add_all([admin_role, dispatcher_role, user_role])
        
        # Create admin user
        admin = User(
            username='admin',
            email='admin@example.com',
            first_name='Admin',
            last_name='User',
            role=admin_role
        )
        admin.set_password('admin')
        db.session.add(admin)
        
        # Commit changes
        db.session.commit()
        
        print("Database reset complete. Default admin credentials:")
        print("Username: admin")
        print("Password: admin")

if __name__ == '__main__':
    reset_database()
