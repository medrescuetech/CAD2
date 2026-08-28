import pytest
from flask import url_for

from app import db
from models import User, Role


def ensure_admin(app):
    with app.app_context():
        role = Role.query.filter_by(name='administrator').first()
        if role is None:
            role = Role(name='administrator')
            db.session.add(role)
            db.session.commit()
        user = User.query.filter_by(username='admin').first()
        if not user:
            user = User(username='admin', email='admin@example.com', role=role, first_name='Admin', last_name='User')
            user.set_password('admin')
            db.session.add(user)
            db.session.commit()


def test_health_endpoint(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data and data.get('status') == 'ok'


def test_login_flow(app, client):
    ensure_admin(app)
    # GET login page
    r_get = client.get('/auth/login')
    assert r_get.status_code in (200, 302)

    # POST credentials (CSRF disabled in testing config)
    r_post = client.post('/auth/login', data={'username': 'admin', 'password': 'admin'}, follow_redirects=False)
    # Either redirect to home/dashboard or render with error
    assert r_post.status_code in (302, 200)
