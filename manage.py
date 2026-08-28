#!/usr/bin/env python
"""
Flask application CLI management script.
This script allows for database migrations, shell access, and other management tasks.
"""

import os
import click
from flask_migrate import Migrate
from app import create_app, db
from models import User, Role, Permission

app = create_app(os.getenv('FLASK_CONFIG') or 'default')
migrate = Migrate(app, db)

# Import models for migrations to detect
from models import (
    User, Role, Permission, UserAssociation, PasswordHistory, 
    IPRestriction, IPAllowList, Unit, UnitType, UnitAssignment,
    Incident, IncidentLog, PickupPoint, APIKey, NotificationPreference
)

@app.shell_context_processor
def make_shell_context():
    """Make Flask shell context."""
    return dict(
        app=app, 
        db=db, 
        User=User, 
        Role=Role, 
        Permission=Permission
    )

@app.cli.command('init-db')
def init_db():
    """Initialize the database."""
    click.echo('Initializing the database...')
    db.create_all()
    click.echo('Database initialized!')

@app.cli.command('init-roles')
def init_roles():
    """Initialize role templates."""
    click.echo('Initializing roles from templates...')
    Role.insert_roles()
    click.echo('Roles initialized!')

@app.cli.command('create-admin')
@click.option('--username', default='admin', help='Admin username')
@click.option('--email', default='admin@example.com', help='Admin email')
@click.option('--password', help='Admin password')
def create_admin(username, email, password):
    """Create an administrator user."""
    if not password:
        password = click.prompt('Enter admin password', hide_input=True, confirmation_prompt=True)
    
    # Get admin role
    admin_role = Role.query.filter_by(name='Administrator').first()
    if not admin_role:
        click.echo('Administrator role not found. Initializing roles...')
        Role.insert_roles()
        admin_role = Role.query.filter_by(name='Administrator').first()
    
    # Check if admin user already exists
    admin_user = User.query.filter_by(username=username).first()
    if admin_user:
        click.echo(f'Admin user {username} already exists.')
        if click.confirm('Do you want to reset the password?'):
            admin_user.set_password(password)
            db.session.commit()
            click.echo(f'Password for {username} has been updated.')
        return
    
    # Create admin user
    admin_user = User(
        username=username,
        email=email,
        role=admin_role,
        first_name='System',
        last_name='Administrator'
    )
    admin_user.set_password(password)
    
    db.session.add(admin_user)
    db.session.commit()
    click.echo(f'Admin user {username} created successfully!')

@app.cli.command('reset-db')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
def reset_db(confirm):
    """Reset the database (CAUTION: Deletes all data)."""
    if not confirm and not click.confirm('This will delete all data. Are you sure?'):
        click.echo('Operation cancelled.')
        return
    
    click.echo('Dropping all tables...')
    db.drop_all()
    click.echo('Creating all tables...')
    db.create_all()
    click.echo('Initializing roles...')
    Role.insert_roles()
    click.echo('Database has been reset!')

@app.cli.command('init-ip-access')
def init_ip_access():
    """Initialize IP access control settings."""
    from utils.ip_access_control import initialize_ip_access_settings
    click.echo('Initializing IP access control settings...')
    initialize_ip_access_settings()
    click.echo('IP access control settings initialized!')

@app.cli.command('create-demo-data')
def create_demo_data():
    """Create demo data for testing."""
    click.echo('Creating demo data...')
    
    # Make sure roles exist
    Role.insert_roles()
    
    # Create users for each role
    roles = Role.query.all()
    for role in roles:
        username = role.name.lower().replace(' ', '_')
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(
                username=username,
                email=f'{username}@example.com',
                role=role,
                first_name=role.name,
                last_name='User'
            )
            user.set_password('password')
            db.session.add(user)
    
    # Create demo unit types
    from models import UnitType
    UnitType.insert_defaults()
    
    db.session.commit()
    click.echo('Demo data created successfully!')

if __name__ == '__main__':
    # This allows us to run Flask CLI commands
    # e.g., python manage.py db init
    # e.g., python manage.py db migrate
    # e.g., python manage.py db upgrade
    
    # Import Flask CLI commands
    from flask.cli import FlaskGroup
    from flask_migrate.cli import db as db_cli
    
    cli = FlaskGroup(create_app=lambda: app)
    cli.add_command(db_cli)
    cli()
