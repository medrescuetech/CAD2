import os
import sys
import pytest

# Ensure project root on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app, db
from models import Role, User, Permission


@pytest.fixture(scope="session")
def app():
    overrides = {
        'TESTING': True,
        'DEBUG': False,
        'WTF_CSRF_ENABLED': False,
        'DISABLE_BACKGROUND_TASKS': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'ENABLE_WEBSOCKET': False,
        'SERVER_NAME': 'localhost',
    }
    app = create_app(overrides)
    with app.app_context():
        db.create_all()
        # Ensure administrator role has full permissions
        admin_role = Role.query.filter_by(name='administrator').first()
        if not admin_role:
            admin_role = Role(name='administrator', permissions=0)
            db.session.add(admin_role)
            db.session.commit()
        # Aggregate all permission bits defined in Permission
        full_perms = 0
        for attr in dir(Permission):
            if attr.isupper():
                val = getattr(Permission, attr)
                if isinstance(val, int):
                    full_perms |= val
        admin_role.permissions = full_perms
        db.session.commit()
        # Ensure admin user exists and is assigned to administrator role
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                email='admin@example.com',
                role=admin_role,
                first_name='Admin',
                last_name='User'
            )
            admin_user.set_password('admin')
            db.session.add(admin_user)
            db.session.commit()
        else:
            admin_user.role = admin_role
            db.session.commit()
        yield app
        db.session.remove()


@pytest.fixture()
def client(app):
    return app.test_client()
