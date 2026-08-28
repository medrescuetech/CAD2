import os, sys, io
sys.path.insert(0, r"c:\Users\agill\CascadeProjects\cad system 2")
from app import create_app, db
from models import Role, User, Permission

def ensure_admin(app):
    with app.app_context():
        db.create_all()
        role = Role.query.filter_by(name='administrator').first()
        if not role:
            role = Role(name='administrator', permissions=0)
            db.session.add(role)
            db.session.commit()
        full = 0
        for attr in dir(Permission):
            if attr.isupper():
                val = getattr(Permission, attr)
                if isinstance(val, int):
                    full |= val
        role.permissions = full
        db.session.commit()
        user = User.query.filter_by(username='admin').first()
        if not user:
            user = User(username='admin', email='admin@example.com', role=role, first_name='Admin', last_name='User')
            user.set_password('admin')
            db.session.add(user)
            db.session.commit()


def main():
    app = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False, 'DISABLE_BACKGROUND_TASKS': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    ensure_admin(app)
    with app.app_context():
        client = app.test_client()
        r = client.post('/auth/login', data={'username':'admin','password':'admin'})
        print('login status', r.status_code)
        with client.session_transaction() as sess:
            sess['csrf_token'] = 'tok'
        data = {'file': (io.BytesIO(b'unique_id,category,card_number,priority,subcategory\nA01,Medical,1,LOW,Abdominal Pain\n'), 'ampds_small.csv')}
        resp = client.post('/api/ampds/import', data=data, headers={'X-CSRF-Token': 'tok'}, content_type='multipart/form-data')
        print('import status', resp.status_code)
        print('import body', resp.data.decode('utf-8', errors='replace'))

if __name__ == '__main__':
    main()
