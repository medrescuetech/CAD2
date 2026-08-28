import os
import sys

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app, db
from models import User, Role

def main():
    app = create_app()
    with app.app_context():
        # Check by username 'admin' (should be unique by DB constraint)
        admins_by_username = User.query.filter_by(username='admin').all()
        print(f"Users with username 'admin': {len(admins_by_username)}")
        for u in admins_by_username:
            print(f" - id={u.id}, email={u.email}, active={u.active}")

        # Check all users with Administrator role
        admin_role = Role.query.filter_by(name='Administrator').first()
        if admin_role:
            admin_role_users = User.query.filter_by(role=admin_role).all()
            print(f"Users with role 'Administrator': {len(admin_role_users)}")
            for u in admin_role_users:
                print(f" - id={u.id}, username={u.username}, email={u.email}, active={u.active}")
        else:
            print("Administrator role not found.")

        # If duplicates by username exist (shouldn't due to unique), keep lowest id active, deactivate others
        if len(admins_by_username) > 1:
            admins_by_username.sort(key=lambda u: u.id)
            keeper = admins_by_username[0]
            to_deactivate = admins_by_username[1:]
            for u in to_deactivate:
                u.active = False
            db.session.commit()
            print(f"Deactivated {len(to_deactivate)} duplicate 'admin' users, kept id={keeper.id}")
        else:
            print("No duplicate 'admin' usernames detected.")

if __name__ == '__main__':
    main()
