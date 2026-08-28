import os
import sys

# Add project root to PYTHONPATH so 'app' and 'models' can be imported when running from scripts/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app, db
from models import User, Role


def main():
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username='admin').first()
        if user:
            user.set_password('admin')
            db.session.commit()
            print('Updated password for existing admin user: admin')
            return
        role = Role.query.filter_by(name='Administrator').first()
        if not role:
            Role.insert_roles()
            role = Role.query.filter_by(name='Administrator').first()
        user = User(
            username='admin',
            email='admin@example.com',
            role=role,
            first_name='Admin',
            last_name='User'
        )
        user.set_password('admin')
        db.session.add(user)
        db.session.commit()
        print('Created new admin user with password: admin')


if __name__ == '__main__':
    main()
