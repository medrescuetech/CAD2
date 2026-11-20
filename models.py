from extensions import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from enum import Enum
import json
import hashlib
import secrets
import csv
import uuid
from sqlalchemy import func

class Permission:
    """User permission flags."""
    # General permissions
    VIEW_DASHBOARD = 0x0001
    ACCESS_API = 0x0002
    
    # Incident permissions
    CREATE_INCIDENT = 0x0004
    CREATE_INCIDENTS = 0x0004  # Alias for backward compatibility
    EDIT_INCIDENT = 0x0008
    UPDATE_INCIDENTS = 0x0008  # Alias for backward compatibility
    VIEW_INCIDENTS = 0x0010
    CLOSE_INCIDENT = 0x0020
    CLOSE_INCIDENTS = 0x0020  # Alias for backward compatibility
    DELETE_INCIDENT = 0x0040
    DELETE_INCIDENTS = 0x0040  # Alias for backward compatibility
    EDIT_INCIDENTS = 0x0008     # Alias for EDIT_INCIDENT
    MANAGE_INCIDENTS = 0x0004   # Alias used in templates (same as CREATE_INCIDENT)
    EXPORT_INCIDENTS = 0x0080
    IMPORT_INCIDENTS = 0x0100
    ADD_INCIDENT_LOGS = 0x0200000  # For adding logs to incidents
    
    # Unit permissions
    MANAGE_UNITS = 0x0200
    CREATE_UNITS = 0x0200      # Included in MANAGE_UNITS
    UPDATE_UNITS = 0x0200      # Included in MANAGE_UNITS
    DELETE_UNITS = 0x0200      # Included in MANAGE_UNITS
    EDIT_UNITS = 0x0200        # Included in MANAGE_UNITS
    ASSIGN_UNITS = 0x0400
    VIEW_UNITS = 0x0800
    TRACK_UNITS = 0x1000
    VIEW_UNIT_LOCATIONS = 0x2000
    
    # User & role permissions
    MANAGE_USERS = 0x4000
    VIEW_USERS = 0x4000        # Included in MANAGE_USERS
    MANAGE_ROLES = 0x8000
    VIEW_ROLES = 0x8000        # Included in MANAGE_ROLES
    
    # System permissions
    ADMIN = 0x10000
    ADMINISTRATOR = 0x10000    # Alias for backward compatibility
    MANAGE_SETTINGS = 0x10000  # Included in ADMIN
    VIEW_SETTINGS = 0x10000    # Included in ADMIN
    MANAGE_LOGS = 0x10000      # Included in ADMIN
    VIEW_LOGS = 0x10000        # Included in ADMIN
    VIEW_LOG = 0x10000         # Included in ADMIN
    VIEW_SYSTEM_LOGS = 0x10000 # Included in ADMIN
    AUDIT_SYSTEM = 0x10000     # Included in ADMIN
    BACKUP_DATA = 0x10000      # Included in ADMIN
    READ_ONLY = 0x40000        # Read-only access to the system
    VIEW_DAILY_LOG = 0x10000   # Alias - included in ADMIN
    EDIT_LOG = 0x10000         # Alias - included in ADMIN
    DELETE_LOG = 0x10000       # Alias - included in ADMIN
    
    # Geospatial permissions
    MANAGE_GEOSPATIAL = 0x20000
    VIEW_LOCATIONS = 0x20000   # Included in MANAGE_GEOSPATIAL
    VIEW_MAP = 0x20000         # Included in MANAGE_GEOSPATIAL
    ACCESS_ROUTING = 0x20000   # Included in MANAGE_GEOSPATIAL
    VIEW_PICKUP_POINTS = 0x20000  # Included in MANAGE_GEOSPATIAL
    MANAGE_PICKUP_POINTS = 0x20000  # Included in MANAGE_GEOSPATIAL

    # Data import/export permissions
    EXPORT_DATA = 0x400000     # General export permission
    IMPORT_DATA = 0x800000     # General import permission
    
    # Notification permissions
    MANAGE_NOTIFICATIONS = 0x40000
    VIEW_EMAIL_LOGS = 0x40000  # Included in MANAGE_NOTIFICATIONS
    TEST_EMAIL_SERVICE = 0x80000
    SEND_EMAILS = 0x100000
    
    # AMPDS (Advanced Medical Priority Dispatch System) permissions
    MANAGE_AMPDS = 0x1000000   # AMPDS management
    VIEW_AMPDS = 0x2000000     # AMPDS viewing
    
    # Report permissions
    VIEW_REPORTS = 0x4000000   # Report viewing
    MANAGE_REPORTS = 0x8000000 # Report management
    
    # API access permissions
    MANAGE_API_KEYS = 0x10000000  # API key management
    API_ACCESS = 0x20000000      # General API access
    
    # For backward compatibility - defining common permission sets
    MANAGE_INCIDENTS = CREATE_INCIDENT | EDIT_INCIDENT | DELETE_INCIDENT | VIEW_INCIDENTS

class Role(db.Model):
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    permissions = db.Column(db.Integer)
    
    # Relationships
    users = db.relationship('User', back_populates='role')
    
    def __init__(self, name, permissions=0):
        self.name = name
        self.permissions = permissions
    
    def has_permission(self, permission):
        """Check if role has the given permission."""
        # Administrators have all permissions
        if self.permissions & Permission.ADMIN == Permission.ADMIN:
            return True
        return self.permissions & permission == permission
    
    def add_permission(self, permission):
        """Add a permission to the role."""
        if not self.has_permission(permission):
            self.permissions += permission
    
    def remove_permission(self, permission):
        """Remove a permission from the role."""
        if self.has_permission(permission):
            self.permissions -= permission
    
    def reset_permissions(self):
        """Reset all permissions."""
        self.permissions = 0
    
    def get_permissions(self):
        """Get a list of permission names that this role has."""
        permissions = []
        for attr_name in dir(Permission):
            if attr_name.isupper():  # Only consider uppercase attribute names (constants)
                attr_value = getattr(Permission, attr_name)
                if isinstance(attr_value, int) and self.has_permission(attr_value):
                    permissions.append(attr_name)
        return permissions
    
    @staticmethod
    def insert_roles():
        """Insert or update roles from templates."""
        # Import role templates here to avoid circular imports
        from utils.role_templates import RoleTemplate
        
        # Get all role templates
        template_dict = RoleTemplate.get_template_dict()
        
        # Ensure each role is in the database
        for template_key, template_info in template_dict.items():
            role = Role.query.filter_by(name=template_info['name']).first()
            if not role:
                role = Role(name=template_info['name'])
            
            role.permissions = template_info['permissions']
            
            db.session.add(role)
        
        # Commit the session to save all changes
        db.session.commit()

class User(UserMixin, db.Model):
    """User model."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    active = db.Column(db.Boolean, default=True, index=True)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    session_id = db.Column(db.String(100), unique=True)  # For WebSocket session tracking
    
    # Relationships
    role = db.relationship('Role', back_populates='users')
    incidents_created = db.relationship('Incident', 
                                      foreign_keys='Incident.created_by_id',
                                      back_populates='created_by',
                                      lazy='dynamic')
    incidents_updated = db.relationship('Incident', 
                                      foreign_keys='Incident.updated_by_id',
                                      back_populates='updated_by',
                                      lazy='dynamic')
    dispatched_assignments = db.relationship('UnitAssignment',
                                           foreign_keys='UnitAssignment.dispatched_by_id',
                                           back_populates='dispatcher')
    api_keys = db.relationship('APIKey', back_populates='user')
    notification_preferences = db.relationship('NotificationPreference', 
                                                backref='user',
                                                uselist=False,
                                                cascade='all, delete-orphan')
    daily_logs = db.relationship('DailyLog', backref=db.backref('user_ref', uselist=False), lazy='dynamic')
    
    def __init__(self, username, email, role=None, active=True,
                 first_name=None, last_name=None, password=None):
        self.username = username
        self.email = email
        self.role = role
        self.active = active
        self.first_name = first_name or username
        self.last_name = last_name or ''
        if password:
            self.set_password(password)
    
    def set_password(self, password):
        """Set password hash for user."""
        self.password_hash = generate_password_hash(password)
    
    def verify_password(self, password):
        """Check if password matches hash."""
        return check_password_hash(self.password_hash, password)
        
    def check_password(self, password):
        """Alias for verify_password for compatibility."""
        return self.verify_password(password)
        
    @property
    def is_active(self):
        """Return if user is active."""
        return self.active
    
    @property
    def is_authenticated(self):
        """Return True as all User instances should be authenticated."""
        return True
    
    @property
    def is_anonymous(self):
        """Return False as anonymous users aren't supported."""
        return False
    
    def get_id(self):
        """Return the user ID as a unicode string."""
        return str(self.id)
    
    def can(self, permission):
        """Check if user has the given permission."""
        return self.role is not None and self.role.has_permission(permission)
    
    def has_permission(self, permission):
        """Alias for can() method - used in templates."""
        return self.can(permission)
    
    def is_administrator(self):
        """Check if user is an administrator."""
        return self.can(Permission.ADMIN)
    
    @property
    def full_name(self):
        """Get user's full name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
    
    def to_dict(self):
        """Convert user to dictionary for JSON responses."""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'full_name': self.full_name,
            'role_name': self.role.name if self.role else None,
            'active': self.active,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None
        }
        
    def change_role(self, new_role_name):
        """Change the user's role.
        Args:
            new_role_name: The name of the new role ('administrator', 'dispatcher', 'readonly', or 'supervisor')
        Returns:
            (bool, str): (Success status, Message)
        """
        if new_role_name not in ['administrator', 'dispatcher', 'readonly', 'supervisor']:
            return False, f"Invalid role name: {new_role_name}. Must be 'administrator', 'dispatcher', 'readonly', or 'supervisor'."
            
        role = Role.query.filter_by(name=new_role_name).first()
        if not role:
            return False, f"Role {new_role_name} not found."
            
        self.role = role
        try:
            db.session.commit()
            return True, f"Role changed to {new_role_name}"
        except Exception as e:
            db.session.rollback()
            return False, f"Error changing role: {str(e)}"

class PasswordHistory(db.Model):
    """Password history for users to prevent password reuse."""
    __tablename__ = 'password_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('password_history', lazy='dynamic'))
    
    def __init__(self, user_id, password):
        """Initialize with user_id and plain password."""
        self.user_id = user_id
        self.set_password(password)
    
    def __repr__(self):
        return f'<PasswordHistory {self.user_id} ({self.created_at})>'
    
    def set_password(self, password):
        """Set password hash from plain password."""
        self.password_hash = generate_password_hash(password)
    
    def verify_password(self, password):
        """Verify a password against this history entry."""
        return check_password_hash(self.password_hash, password)

class UserAssociation(db.Model):
    """Association between users, such as supervisor, partner, substitute, etc."""
    __tablename__ = 'user_associations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    target_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    association_type = db.Column(db.String(32), nullable=False)
    notes = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('outgoing_associations', lazy='dynamic'))
    target_user = db.relationship('User', foreign_keys=[target_user_id], backref=db.backref('incoming_associations', lazy='dynamic'))
    
    def __repr__(self):
        return f'<UserAssociation {self.user_id} -> {self.target_user_id} ({self.association_type})>'
    
    def to_dict(self):
        """Convert association to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'target_user_id': self.target_user_id,
            'source_username': self.user.username if self.user else None,
            'target_username': self.target_user.username if self.target_user else None,
            'association_type': self.association_type,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class IPRestriction(db.Model):
    """IP address restriction for system access."""
    __tablename__ = 'ip_restrictions'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50), nullable=False, index=True)
    reason = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    added_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    removed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    removed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    added_by = db.relationship('User', foreign_keys=[added_by_user_id])
    removed_by = db.relationship('User', foreign_keys=[removed_by_user_id])
    
    def __repr__(self):
        return f'<IPRestriction {self.ip_address}>'
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'ip_address': self.ip_address,
            'reason': self.reason,
            'is_active': self.is_active,
            'added_by_user_id': self.added_by_user_id,
            'removed_by_user_id': self.removed_by_user_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'removed_at': self.removed_at.isoformat() if self.removed_at else None
        }

class IPAllowList(db.Model):
    """IP address allowlist for system access."""
    __tablename__ = 'ip_allowlist'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    added_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    removed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    removed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    added_by = db.relationship('User', foreign_keys=[added_by_user_id])
    removed_by = db.relationship('User', foreign_keys=[removed_by_user_id])
    
    def __repr__(self):
        return f'<IPAllowList {self.ip_address}>'
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'ip_address': self.ip_address,
            'description': self.description,
            'is_active': self.is_active,
            'added_by_user_id': self.added_by_user_id,
            'removed_by_user_id': self.removed_by_user_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'removed_at': self.removed_at.isoformat() if self.removed_at else None
        }

class UnitType(db.Model):
    """Unit type model."""
    __tablename__ = 'unit_type'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    units = db.relationship('Unit', back_populates='type')
    
    def __repr__(self):
        return f'<UnitType {self.name}>'
    
    def to_dict(self):
        """Convert unit type to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @staticmethod
    def insert_defaults():
        """Insert default unit types."""
        defaults = [
            ('Paramedic', 'Standard paramedic unit'),
            ('Critical Care', 'Advanced life support unit'),
            ('Basic Life Support', 'Basic life support unit'),
            ('Supervisor', 'Supervisor vehicle'),
            ('Special Operations', 'Special operations unit')
        ]
        
        for name, description in defaults:
            unit_type = UnitType.query.filter_by(name=name).first()
            if not unit_type:
                unit_type = UnitType(name=name, description=description)
                db.session.add(unit_type)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # current_app.logger.error(f"Error inserting default unit types: {str(e)}")

class Unit(db.Model):
    """Unit model."""
    __tablename__ = 'unit'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    type_id = db.Column(db.Integer, db.ForeignKey('unit_type.id'))
    active = db.Column(db.Boolean, default=True)
    # New simple string location used by tests
    location = db.Column(db.String(200))
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'))
    status = db.Column(db.String(20), default='available')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    type = db.relationship('UnitType', back_populates='units')
    # Keep relationship under a different attribute name to avoid conflicts with test expectations
    location_rel = db.relationship('Location', back_populates='units')
    assignments = db.relationship('UnitAssignment', back_populates='unit')

    def __repr__(self):
        return f'<Unit {self.name}>'

    def to_dict(self):
        """Convert unit to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type.name if self.type else None,
            'active': self.active,
            'location': self.location if self.location else (self.location_rel.name if self.location_rel else None),
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class IncidentQuery(db.Query):
    def __init__(self, *args, **kwargs):
        super(IncidentQuery, self).__init__(*args, **kwargs)
        
    def get(self, ident):
        # Custom implementation to avoid using incident_type_id
        if isinstance(ident, (int, float, str)):
            return self.filter(Incident.id == ident).first()
        return super(IncidentQuery, self).get(ident)
    
    def all(self):
        # Define the specific columns we want to select
        query = self.with_entities(
            Incident.id,
            Incident.incident_number,
            Incident.priority,
            Incident.status,
            Incident.location,
            Incident.location_id,
            Incident.latitude,
            Incident.longitude,
            Incident.caller,
            Incident.callback_number,
            Incident.description,
            Incident.ampds_code,
            Incident.ampds_data,
            Incident.resolution,
            Incident.created_at,
            Incident.updated_at,
            Incident.created_by_id,
            Incident.updated_by_id
        )
        # Call the base implementation of all() directly from SQLAlchemy's Query class
        return db.Query.all(query)
    
    def count(self):
        # Custom count to avoid using incident_type_id
        return db.session.query(func.count(Incident.id)).scalar()

class Incident(db.Model):
    """Incident model."""
    __tablename__ = 'incidents'
    query_class = IncidentQuery
    
    # Priority constants
    PRIORITY_LOW = 1
    PRIORITY_MEDIUM = 2
    PRIORITY_HIGH = 3
    PRIORITY_CRITICAL = 4
    
    PRIORITY_MAP = {
        'LOW': PRIORITY_LOW,
        'MEDIUM': PRIORITY_MEDIUM,
        'HIGH': PRIORITY_HIGH,
        'CRITICAL': PRIORITY_CRITICAL
    }
    
    PRIORITY_MAP_REVERSE = {
        PRIORITY_LOW: 'LOW',
        PRIORITY_MEDIUM: 'MEDIUM',
        PRIORITY_HIGH: 'HIGH',
        PRIORITY_CRITICAL: 'CRITICAL'
    }
    
    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_OPEN = 'open'
    STATUS_CLOSED = 'closed'
    
    id = db.Column(db.Integer, primary_key=True)
    incident_number = db.Column(db.String(20), unique=True, index=True)
    incident_type_id = db.Column(db.Integer, db.ForeignKey('incident_types.id'), nullable=True)
    priority = db.Column(db.Integer)
    status = db.Column(db.String(20), default=STATUS_PENDING)
    # Simple type string used by tests
    type_text = db.Column(db.String(50))
    location = db.Column(db.String(200))
    location_id = db.Column(db.String(50))  # For reference to external location systems
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    caller = db.Column(db.String(100))
    callback_number = db.Column(db.String(20))
    description = db.Column(db.Text)
    ampds_code = db.Column(db.String(20))  # AMPDS protocol code
    ampds_data = db.Column(db.Text)  # JSON storage of AMPDS data
    resolution = db.Column(db.Text)  # Resolution notes when incident is closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # --- CAD ecosystem shared-core fields ---
    incident_uuid = db.Column(db.String(36), unique=True, index=True)
    owning_application = db.Column(db.String(16), default='MAIN', index=True)
    event_workspace_id = db.Column(db.Integer, db.ForeignKey('event_workspace.id'))
    event_location_id = db.Column(db.Integer, db.ForeignKey('event_location.id'))
    lifecycle_status = db.Column(db.String(24), default='NEW', index=True)
    escalation_mode = db.Column(db.String(32))
    escalated_at = db.Column(db.DateTime)
    responsible_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    row_version = db.Column(db.Integer, default=1, nullable=False)
    closed_at = db.Column(db.DateTime)
    closed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    closure_outcome = db.Column(db.String(64))
    urgent_update = db.Column(db.Boolean, default=False)

    # Relationships
    event_workspace = db.relationship('EventWorkspace',
                                      backref=db.backref('incidents', lazy='dynamic'))
    event_location = db.relationship('EventLocation')
    responsible_user = db.relationship('User', foreign_keys=[responsible_user_id])
    closed_by = db.relationship('User', foreign_keys=[closed_by_id])
    created_by = db.relationship('User', 
                                foreign_keys=[created_by_id],
                                back_populates='incidents_created')
    updated_by = db.relationship('User', 
                                foreign_keys=[updated_by_id],
                                back_populates='incidents_updated')
    unit_assignments = db.relationship('UnitAssignment', 
                                      back_populates='incident',
                                      cascade='all, delete-orphan')
    logs = db.relationship('IncidentLog', backref='incident', lazy='dynamic',
                          cascade='all, delete-orphan')

    def __init__(self, incident_number=None, incident_type_id=None, priority=None, status=STATUS_PENDING,
                 location=None, description=None, created_by_id=None, created_at=None,
                 caller=None, callback_number=None, latitude=None, longitude=None, 
                 location_id=None):
        self.incident_type_id = incident_type_id
        self.set_priority(priority if priority else self.PRIORITY_MEDIUM)
        self.status = status
        self.location = location
        self.description = description
        self.caller = caller
        self.callback_number = callback_number
        self.latitude = latitude
        self.longitude = longitude
        self.location_id = location_id
        self.created_by_id = created_by_id
        if not self.incident_uuid:
            self.incident_uuid = str(uuid.uuid4())

        if incident_number:
            self.incident_number = incident_number
        else:
            self.incident_number = self.generate_incident_number()
            
        if created_at:
            self.created_at = created_at
        
    def set_priority(self, priority):
        """Set priority from either string or integer value."""
        if isinstance(priority, str):
            self.priority = self.PRIORITY_MAP.get(priority.upper(), self.PRIORITY_MEDIUM)
        else:
            self.priority = priority if priority in self.PRIORITY_MAP_REVERSE else self.PRIORITY_MEDIUM

    def get_priority_string(self):
        """Get priority as string value."""
        return self.PRIORITY_MAP_REVERSE.get(self.priority, 'MEDIUM')

    # Backward-compatible simple type property used in tests
    @property
    def type(self):
        return self.type_text

    @type.setter
    def type(self, value):
        self.type_text = value

    @staticmethod
    def generate_incident_number():
        """Generate a unique incident number."""
        year = datetime.utcnow().year
        # Get the highest number for this year
        try:
            last_incident = Incident.query.filter(
                Incident.incident_number.like(f'INC-{year}-%')
            ).order_by(Incident.incident_number.desc()).first()
            
            if last_incident and last_incident.incident_number:
                try:
                    last_num = int(last_incident.incident_number.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
                
            return f'INC-{year}-{new_num:05d}'
        except Exception as e:
            # Fallback to timestamp-based number if database query fails
            timestamp = int(datetime.utcnow().timestamp())
            return f'INC-{year}-{timestamp}'

    def update_status(self, new_status, user_id):
        """Update incident status and log the change."""
        valid_statuses = [self.STATUS_PENDING, self.STATUS_OPEN, self.STATUS_CLOSED]
        if new_status not in valid_statuses:
            raise ValueError(f'Invalid status: {new_status}. Must be one of {", ".join(valid_statuses)}')
            
        old_status = self.status
        if old_status == new_status:
            return False  # No change needed
            
        self.status = new_status
        self.updated_at = datetime.utcnow()
        self.updated_by_id = user_id
        
        # If input is added and status is pending, automatically change to open
        if new_status == self.STATUS_PENDING and self.has_required_data():
            self.status = self.STATUS_OPEN
            new_status = self.STATUS_OPEN
        
        # Create log entry for status change
        log = IncidentLog(
            incident_id=self.id,
            user_id=user_id,
            message=f"Status changed from {old_status} to {new_status}",
            type="status",
            timestamp=datetime.utcnow()
        )
        db.session.add(log)
        return True

    def has_required_data(self):
        """Check if incident has required data to be considered 'open'."""
        return bool(self.incident_type and self.location and self.description)

    def set_ampds_protocol(self, protocol, user_id):
        """Set AMPDS protocol data and log it."""
        if isinstance(protocol, AMPDSProtocol):
            self.ampds_code = protocol.unique_id
            self.ampds_data = json.dumps(protocol.to_dict())
            
            # Create log entry
            log = IncidentLog(
                incident_id=self.id,
                user_id=user_id,
                message=f"AMPDS Protocol {protocol.unique_id} assigned: {protocol.subcategory}",
                type="info",
                timestamp=datetime.utcnow()
            )
            db.session.add(log)
            return True
        return False

    def get_ampds_data(self):
        """Get parsed AMPDS data."""
        if self.ampds_data:
            try:
                return json.loads(self.ampds_data)
            except:
                return None
        return None

    def add_log_entry(self, message, user_id, type="info"):
        """Add a log entry to this incident."""
        log = IncidentLog(
            incident_id=self.id,
            user_id=user_id,
            message=message,
            type=type,
            timestamp=datetime.utcnow()
        )
        db.session.add(log)
        return log

    def to_dict(self):
        """Convert incident to dictionary for JSON responses."""
        assigned_units = []
        for assignment in self.unit_assignments:
            if not assignment.cleared:
                assigned_units.append({
                    'id': assignment.unit.id,
                    'name': assignment.unit.name,
                    'status': assignment.unit.status,
                    'assigned_at': assignment.dispatched_at.isoformat() if assignment.dispatched_at else None
                })
                
        logs = []
        for log in self.logs.order_by(IncidentLog.timestamp.desc()).limit(50):
            logs.append({
                'id': log.id,
                'incident_id': log.incident_id,
                'user_id': log.user_id,
                'username': log.user.username if log.user else None,
                'message': log.message,
                'type': log.type,
                'timestamp': log.timestamp.isoformat(),
                'user': log.user.username if log.user else None
            })
            
        ampds_data = None
        if self.ampds_data:
            try:
                ampds_data = json.loads(self.ampds_data)
            except:
                pass
                
        return {
            'id': self.id,
            'incident_number': self.incident_number,
            'incident_type_id': self.incident_type_id,
            'incident_type': self.incident_type.name if self.incident_type else None,
            'type': self.type_text,
            'priority': self.priority,
            'priority_text': self.get_priority_string(),
            'status': self.status,
            'location': self.location,
            'location_id': self.location_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'caller': self.caller,
            'event_location': self.event_location.to_dict() if self.event_location else None,
            'callback_number': self.callback_number,
            'description': self.description,
            'ampds_code': self.ampds_code,
            'ampds_data': ampds_data,
            'resolution': self.resolution,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'created_by_id': self.created_by_id,
            'updated_by_id': self.updated_by_id,
            'incident_uuid': self.incident_uuid,
            'owning_application': self.owning_application,
            'event_workspace_id': self.event_workspace_id,
            'event_location_id': self.event_location_id,
            'lifecycle_status': self.lifecycle_status,
            'escalation_mode': self.escalation_mode,
            'responsible_user_id': self.responsible_user_id,
            'row_version': self.row_version,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'closure_outcome': self.closure_outcome,
            'urgent_update': self.urgent_update,
            'assigned_units': assigned_units,
            'logs': logs
        }

# Simple enums for tests to import
class IncidentStatus:
    PENDING = Incident.STATUS_PENDING
    OPEN = Incident.STATUS_OPEN
    CLOSED = Incident.STATUS_CLOSED

class IncidentPriority:
    LOW = Incident.PRIORITY_LOW
    MEDIUM = Incident.PRIORITY_MEDIUM
    HIGH = Incident.PRIORITY_HIGH
    CRITICAL = Incident.PRIORITY_CRITICAL

class UnitAssignment(db.Model):
    """Unit assignment model."""
    __tablename__ = 'unit_assignment'
    
    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'), nullable=False)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='assigned')
    dispatched_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    dispatched_at = db.Column(db.DateTime, default=datetime.utcnow)
    arrived_at = db.Column(db.DateTime)
    cleared_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    unit = db.relationship('Unit', back_populates='assignments')
    incident = db.relationship('Incident', back_populates='unit_assignments')
    dispatcher = db.relationship('User', 
                               foreign_keys=[dispatched_by_id],
                               back_populates='dispatched_assignments')

class IncidentLog(db.Model):
    __tablename__ = 'incident_log'
    
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id', ondelete='CASCADE'), 
                           nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')  # info, status, note, warning, error
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationship
    user = db.relationship('User', backref='log_entries')
    
    def to_dict(self):
        """Convert log entry to dictionary for JSON responses."""
        return {
            'id': self.id,
            'incident_id': self.incident_id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'message': self.message,
            'type': self.type,
            'timestamp': self.timestamp.isoformat(),
            'user': self.user.username if self.user else None
        }

class PickupPoint(db.Model):
    __tablename__ = 'pickup_point'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    location = db.Column(db.String(200), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DailyLog(db.Model):
    """Daily log model."""
    __tablename__ = 'daily_log'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    shift = db.Column(db.String(20), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_archived = db.Column(db.Boolean, default=False, index=True)
    archived_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    entries = db.relationship('DailyLogEntry', backref='log', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<DailyLog {self.date} ({self.shift})>'
    
    def to_dict(self):
        """Convert daily log to dictionary for JSON responses."""
        return {
            'id': self.id,
            'date': self.date.strftime('%Y-%m-%d') if self.date else None,
            'shift': self.shift,
            'user_id': self.user_id,
            'user': self.user_ref.full_name() if self.user_ref else None,
            'notes': self.notes,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
            'log_number': f"{self.date.strftime('%Y%m%d')}-{self.shift.upper()}" if self.date else None,
            'entries': [entry.to_dict() for entry in self.entries],
            'is_archived': self.is_archived,
            'archived_at': self.archived_at.strftime('%Y-%m-%d %H:%M:%S') if self.archived_at else None
        }
    
    @staticmethod
    def get_logs_by_date_range(start_date, end_date, shift=None):
        """Get daily logs within a date range, optionally filtered by shift."""
        query = DailyLog.query.filter(DailyLog.date >= start_date, DailyLog.date <= end_date)
        
        if shift:
            query = query.filter(DailyLog.shift == shift)
            
        return query.order_by(DailyLog.date, DailyLog.shift).all()

class DailyLogEntry(db.Model):
    """Model for individual entries within a daily log."""
    __tablename__ = 'daily_log_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    type = db.Column(db.String(50), nullable=False, default='GENERAL')
    text = db.Column(db.Text, nullable=False)
    
    # Attachment fields
    has_attachment = db.Column(db.Boolean, default=False)
    attachment_filename = db.Column(db.String(255), nullable=True)
    attachment_path = db.Column(db.String(255), nullable=True)
    attachment_type = db.Column(db.String(50), nullable=True)  # file extension or mime type
    attachment_size = db.Column(db.Integer, nullable=True)  # size in bytes
    
    # Relationships
    user = db.relationship('User', backref=db.backref('daily_log_entries', lazy='dynamic'))
    
    def __repr__(self):
        return f'<LogEntry {self.timestamp} ({self.type})>'
    
    def to_dict(self):
        """Convert log entry to dictionary for JSON responses."""
        return {
            'id': self.id,
            'log_id': self.log_id,
            'user_id': self.user_id,
            'user_name': self.user.full_name() if self.user else None,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None,
            'type': self.type,
            'text': self.text,
            'has_attachment': self.has_attachment,
            'attachment': {
                'filename': self.attachment_filename,
                'type': self.attachment_type,
                'size': self.attachment_size
            } if self.has_attachment else None
        }

class IncidentType(db.Model):
    """Model for standardized incident types."""
    __tablename__ = 'incident_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    description = db.Column(db.Text)
    default_priority = db.Column(db.Integer, default=2)  # Default to medium priority
    color = db.Column(db.String(20), default="#007bff")  # Color for UI display
    requires_location = db.Column(db.Boolean, default=True)
    requires_caller = db.Column(db.Boolean, default=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to incidents - using lazy='dynamic' to avoid loading all incidents at once
    incidents = db.relationship('Incident', foreign_keys='Incident.incident_type_id', backref='incident_type', lazy='dynamic')
    
    def __repr__(self):
        return f"<IncidentType {self.name}>"
    
    def to_dict(self):
        """Convert to dictionary for JSON responses."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'default_priority': self.default_priority,
            'priority_string': Incident.PRIORITY_MAP_REVERSE.get(self.default_priority, 'MEDIUM'),
            'color': self.color,
            'requires_location': self.requires_location,
            'requires_caller': self.requires_caller,
            'active': self.active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    @staticmethod
    def insert_defaults():
        """Insert default incident types."""
        default_types = [
            {'name': 'Medical Emergency', 'description': 'Medical emergency requiring immediate attention', 
             'default_priority': Incident.PRIORITY_HIGH, 'color': '#dc3545'},
            {'name': 'Traffic Accident', 'description': 'Vehicle collision or traffic-related incident', 
             'default_priority': Incident.PRIORITY_MEDIUM, 'color': '#fd7e14'},
            {'name': 'Fire', 'description': 'Fire-related emergency', 
             'default_priority': Incident.PRIORITY_HIGH, 'color': '#dc3545'},
            {'name': 'Security', 'description': 'Security-related incident', 
             'default_priority': Incident.PRIORITY_MEDIUM, 'color': '#6c757d'},
            {'name': 'Public Assistance', 'description': 'Non-emergency assistance to the public', 
             'default_priority': Incident.PRIORITY_LOW, 'color': '#28a745'}
        ]
        
        for type_data in default_types:
            existing = IncidentType.query.filter_by(name=type_data['name']).first()
            if not existing:
                incident_type = IncidentType(
                    name=type_data['name'],
                    description=type_data['description'],
                    default_priority=type_data['default_priority'],
                    color=type_data['color']
                )
                db.session.add(incident_type)
        
        db.session.commit()

class Location(db.Model):
    __tablename__ = 'location'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    address = db.Column(db.Text)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active = db.Column(db.Boolean, default=True, index=True)
    needs_review = db.Column(db.Boolean, default=False)
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(50), default='USA')
    type = db.Column(db.String(50), default='standard') # e.g. standard, hospital, police, fire, etc.
    source = db.Column(db.String(50)) # how the location was added (manual, geocoded, imported)
    
    # Relationships
    units = db.relationship('Unit', back_populates='location_rel')
    
    def __repr__(self):
        return f'<Location: {self.name}, ({self.latitude}, {self.longitude})>'
        
    def to_dict(self):
        """Convert location to dictionary for JSON responses."""
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'city': self.city,
            'state': self.state,
            'postal_code': self.postal_code,
            'country': self.country,
            'type': self.type,
            'active': self.active,
            'needs_review': self.needs_review,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_formatted_address(self):
        """Return formatted address for display."""
        if self.address:
            return self.address
            
        # Build address from components if available
        address_parts = []
        if self.name:
            address_parts.append(self.name)
        if self.city:
            city_state = []
            if self.city:
                city_state.append(self.city)
            if self.state:
                city_state.append(self.state)
            if city_state:
                address_parts.append(', '.join(city_state))
        if self.postal_code:
            address_parts.append(self.postal_code)
        if self.country and self.country.upper() != 'USA':
            address_parts.append(self.country)
            
        return ', '.join(address_parts) if address_parts else f"({self.latitude}, {self.longitude})"
    
    @classmethod
    def search(cls, query, limit=20, active_only=True):
        """Search for locations by name, address or other fields."""
        search_query = f"%{query}%"
        filters = [
            cls.name.ilike(search_query),
            cls.address.ilike(search_query) if cls.address is not None else False,
            cls.city.ilike(search_query) if cls.city is not None else False,
            cls.postal_code.ilike(search_query) if cls.postal_code is not None else False
        ]
        
        # Build query
        db_query = cls.query.filter(or_(*filters))
        
        # Filter by active status if requested
        if active_only:
            db_query = db_query.filter(cls.active == True)
            
        return db_query.order_by(cls.name).limit(limit).all()
    
    @classmethod
    def find_or_create_from_geocoding(cls, address, lat, lng, name=None, source='geocoding'):
        """Find existing location or create a new one based on geocoding results."""
        # First check if location with these coordinates already exists 
        # (within a small margin of error)
        margin = 0.0001 # Approximately 10 meters
        existing = cls.query.filter(
            cls.latitude.between(lat - margin, lat + margin),
            cls.longitude.between(lng - margin, lng + margin)
        ).first()
        
        if existing:
            return existing, False
            
        # If not found by coordinates, check for matching address or name
        if name:
            existing = cls.query.filter(cls.name == name).first()
            if existing:
                return existing, False
                
        # Create new location
        location = cls(
            name=name or address,
            address=address,
            latitude=lat,
            longitude=lng,
            source=source
        )
        
        # Try to parse address components
        try:
            parts = address.split(',')
            if len(parts) >= 3:
                location.city = parts[-3].strip()
                location.state = parts[-2].strip()
                postal_country = parts[-1].strip().split()
                if len(postal_country) >= 1:
                    location.postal_code = postal_country[0]
                if len(postal_country) >= 2:
                    location.country = ' '.join(postal_country[1:])
        except:
            # If parsing fails, just continue with what we have
            pass
            
        db.session.add(location)
        db.session.commit()
        
        return location, True

class SystemSetting(db.Model):
    """System settings model for storing configuration."""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<SystemSetting {self.name}>'

class AMPDSProtocol(db.Model):
    """AMPDS Protocol model for medical dispatch protocols."""
    __tablename__ = 'ampds_protocols'
    
    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(20), unique=True, index=True, nullable=False)
    category = db.Column(db.String(50), nullable=False, index=True)
    card_number = db.Column(db.String(20), nullable=False, index=True)
    priority = db.Column(db.String(20), nullable=False)
    subcategory = db.Column(db.String(200), nullable=False)
    dispatch_advice = db.Column(db.Text)
    prearrival_pdf = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<AMPDSProtocol {self.unique_id}: {self.subcategory}>'
    
    def to_dict(self):
        """Convert protocol to dictionary for API responses."""
        return {
            'id': self.id,
            'unique_id': self.unique_id,
            'category': self.category,
            'card_number': self.card_number,
            'priority': self.priority,
            'subcategory': self.subcategory,
            'dispatch_advice': self.dispatch_advice,
            'prearrival_pdf': self.prearrival_pdf,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        
    @staticmethod
    def search(query, limit=20, category=None, card_number=None, priority=None):
        """
        Search for AMPDS protocols by various fields.
        
        Args:
            query: The search query string
            limit: Maximum number of results to return
            category: Optional category filter
            card_number: Optional card number filter
            priority: Optional priority filter
            
        Returns:
            List of matching AMPDSProtocol objects
        """
        # Start with a base query
        base_query = AMPDSProtocol.query
        
        # Apply optional filters
        if category:
            base_query = base_query.filter(AMPDSProtocol.category == category)
        
        if card_number:
            base_query = base_query.filter(AMPDSProtocol.card_number == card_number)
            
        if priority:
            base_query = base_query.filter(AMPDSProtocol.priority == priority)
        
        # Apply text search if query is provided
        if query and len(query.strip()) > 0:
            search_query = f"%{query.strip()}%"
            base_query = base_query.filter(
                db.or_(
                    AMPDSProtocol.unique_id.ilike(search_query),
                    AMPDSProtocol.category.ilike(search_query),
                    AMPDSProtocol.subcategory.ilike(search_query),
                    AMPDSProtocol.dispatch_advice.ilike(search_query),
                    AMPDSProtocol.card_number.ilike(search_query)
                )
            )
        
        # Order by card number and category for consistent results
        return base_query.order_by(
            AMPDSProtocol.card_number, 
            AMPDSProtocol.category
        ).limit(limit).all()
        
    @staticmethod
    def suggest_protocols_for_incident_type(incident_type_name, limit=5):
        """
        Suggest AMPDS protocols that might be relevant for a given incident type.
        
        Args:
            incident_type_name: The name of the incident type
            limit: Maximum number of suggestions to return
            
        Returns:
            List of suggested AMPDSProtocol objects
        """
        # Split the incident type name into keywords for better matching
        keywords = [k.strip() for k in incident_type_name.lower().split() if len(k.strip()) > 2]
        
        if not keywords:
            # If no useful keywords, return some common protocols
            return AMPDSProtocol.query.order_by(
                AMPDSProtocol.priority
            ).limit(limit).all()
        
        # Build a query that checks each keyword against the subcategory field
        conditions = []
        for keyword in keywords:
            conditions.append(AMPDSProtocol.subcategory.ilike(f"%{keyword}%"))
            
        # Return protocols that match any of the keywords, sorted by priority
        return AMPDSProtocol.query.filter(
            db.or_(*conditions)
        ).order_by(
            AMPDSProtocol.priority
        ).limit(limit).all()

    @staticmethod
    def import_from_csv(csv_file, commit=True):
        """
        Import AMPDS protocols from a CSV file.
        
        Args:
            csv_file: A file-like object containing CSV data
            commit: Whether to commit the changes to the database
            
        Returns:
            tuple: (success_count, error_count, errors)
            
        CSV format should have headers:
        unique_id,category,card_number,priority,subcategory,dispatch_advice,prearrival_pdf
        """
        # Normalize input to a text stream for csv module
        try:
            import io as _io
            text_stream = None
            # If it's a Werkzeug FileStorage, use .stream
            stream = getattr(csv_file, 'stream', csv_file)
            # If stream supports read(), get content
            if hasattr(stream, 'read'):
                data = stream.read()
                # If subsequent consumers expect to re-read, reset pointer safely
                try:
                    stream.seek(0)
                except Exception:
                    pass
                if isinstance(data, bytes):
                    data = data.decode('utf-8', errors='replace')
                elif not isinstance(data, str):
                    data = str(data)
                text_stream = _io.StringIO(data)
            else:
                # Assume iterable of text lines
                text_stream = stream
            reader = csv.DictReader(text_stream)
        except Exception as e:
            return 0, 1, [f"Failed to read CSV: {e}"]
        success_count = 0
        error_count = 0
        errors = []
        
        required_fields = ['unique_id', 'category', 'card_number', 'priority', 'subcategory']
        
        for i, row in enumerate(reader, start=1):
            # Validate required fields
            missing_fields = [field for field in required_fields if not row.get(field)]
            if missing_fields:
                error_count += 1
                errors.append(f"Row {i}: Missing required fields: {', '.join(missing_fields)}")
                continue
                
            try:
                # Check if protocol already exists
                existing = AMPDSProtocol.query.filter_by(unique_id=row['unique_id']).first()
                if existing:
                    # Update existing protocol
                    existing.category = row['category']
                    existing.card_number = row['card_number']
                    existing.priority = row['priority']
                    existing.subcategory = row['subcategory']
                    existing.dispatch_advice = row.get('dispatch_advice', '')
                    existing.prearrival_pdf = row.get('prearrival_pdf', '')
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new protocol
                    protocol = AMPDSProtocol(
                        unique_id=row['unique_id'],
                        category=row['category'],
                        card_number=row['card_number'],
                        priority=row['priority'],
                        subcategory=row['subcategory'],
                        dispatch_advice=row.get('dispatch_advice', ''),
                        prearrival_pdf=row.get('prearrival_pdf', '')
                    )
                    db.session.add(protocol)
                success_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f"Row {i}: Error processing row: {str(e)}")
        
        if commit and success_count > 0:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                errors.append(f"Database error: {str(e)}")
                return 0, error_count + success_count, errors
        
        return success_count, error_count, errors
    
    @staticmethod
    def search(query, limit=20):
        """
        Search for AMPDS protocols by unique_id, category, or subcategory.
        
        Args:
            query: The search query string
            limit: Maximum number of results to return
            
        Returns:
            List of matching AMPDSProtocol objects
        """
        search_query = f"%{query}%"
        return AMPDSProtocol.query.filter(
            db.or_(
                AMPDSProtocol.unique_id.ilike(search_query),
                AMPDSProtocol.category.ilike(search_query),
                AMPDSProtocol.subcategory.ilike(search_query)
            )
        ).limit(limit).all()

class APIKey(db.Model):
    """Model for API Keys used for external service integration."""
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    key_prefix = db.Column(db.String(16), nullable=False)  # Prefix for identifying the key (stored in plaintext)
    key_hash = db.Column(db.String(256), nullable=False)   # Hashed key for verification
    active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    permissions = db.Column(db.Integer, default=Permission.API_ACCESS)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    
    # Relationships
    created_by = db.relationship('User', foreign_keys=[created_by_id], overlaps="api_keys")
    user = db.relationship('User', back_populates='api_keys', overlaps="created_by")
    
    def __init__(self, **kwargs):
        super(APIKey, self).__init__(**kwargs)
        
    @staticmethod
    def generate_key(length=32):
        """Generate a secure API key."""
        import secrets
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def get_hash(key):
        """Get hash of key for secure storage."""
        import hashlib
        return hashlib.sha256(key.encode('utf-8')).hexdigest()
    
    def verify_key(self, key):
        """Verify if a provided key matches this API key."""
        if not self.active:
            return False
            
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
            
        # Check if the key hash matches
        return self.key_hash == self.get_hash(key)
    
    def update_last_used(self):
        """Update the last used timestamp."""
        self.last_used_at = datetime.utcnow()
        db.session.add(self)
        db.session.commit()
    
    @classmethod
    def create_key(cls, name, description=None, permissions=Permission.API_ACCESS, 
                   created_by=None, expires_at=None, key_length=32):
        """Create a new API key with secure generation and storage."""
        raw_key = cls.generate_key(key_length)
        key_prefix = raw_key[:8]  # First 8 characters as prefix
        key_hash = cls.get_hash(raw_key)
        
        api_key = cls(
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            active=True,
            description=description,
            permissions=permissions,
            created_by_id=created_by.id if created_by else None,
            expires_at=expires_at
        )
        
        db.session.add(api_key)
        db.session.commit()
        
        # Return the full key only once - it won't be accessible later
        return api_key, f"{key_prefix}.{raw_key[8:]}"
    
    def has_permission(self, permission):
        """Check if the API key has a specific permission."""
        return self.permissions & permission == permission
    
    def to_dict(self):
        """Convert the API key to a dictionary (excluding sensitive data)."""
        return {
            'id': self.id,
            'name': self.name,
            'key_prefix': self.key_prefix,
            'active': self.active,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'created_by': self.created_by.username if self.created_by else None
        }

class Notification(db.Model):
    """Model for storing user notifications."""
    __tablename__ = 'notifications'
    
    # Notification type constants
    TYPE_SYSTEM = 'system'      # System notifications
    TYPE_INCIDENT = 'incident'  # Incident related notifications
    TYPE_UNIT = 'unit'          # Unit related notifications
    TYPE_USER = 'user'          # User activity notifications
    TYPE_ALERT = 'alert'        # Critical alerts requiring immediate attention
    
    # Notification status constants
    STATUS_UNREAD = 'unread'
    STATUS_READ = 'read'
    STATUS_ARCHIVED = 'archived'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False, default=TYPE_SYSTEM, index=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_UNREAD, index=True)
    reference_id = db.Column(db.Integer)  # Optional ID reference to related entity (incident, unit, etc.)
    reference_type = db.Column(db.String(50))  # Type of reference (incident, unit, etc.)
    is_read = db.Column(db.Boolean, default=False)
    is_email_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic'))
    
    def __repr__(self):
        return f'<Notification {self.id}: {self.title[:20]}...>'
    
    def mark_as_read(self):
        """Mark notification as read."""
        self.is_read = True
        self.status = self.STATUS_READ
        self.updated_at = datetime.utcnow()
        return self
    
    def archive(self):
        """Archive notification."""
        self.status = self.STATUS_ARCHIVED
        self.updated_at = datetime.utcnow()
        return self
        
    def to_dict(self):
        """Convert notification to dictionary for API responses."""
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'notification_type': self.notification_type,
            'status': self.status,
            'is_read': self.is_read,
            'reference_id': self.reference_id,
            'reference_type': self.reference_type,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class AuditLog(db.Model):
    """Model for storing security audit logs."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(36), index=True)  # UUID for request tracking
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    category = db.Column(db.String(50), nullable=False, index=True)  # Authentication, Access Control, etc.
    action = db.Column(db.String(100), nullable=False)
    severity = db.Column(db.String(20), nullable=False, index=True)  # INFO, WARNING, ERROR, CRITICAL
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    endpoint = db.Column(db.String(100), nullable=True)
    resource_type = db.Column(db.String(50), nullable=True, index=True)
    resource_id = db.Column(db.String(50), nullable=True)
    details = db.Column(db.Text, nullable=True)  # JSON string of additional details

    # Relationships
    user = db.relationship('User', backref=db.backref('audit_logs', lazy='dynamic'))

    def __init__(self, **kwargs):
        super(AuditLog, self).__init__(**kwargs)

    @classmethod
    def get_logs_by_category(cls, category, limit=100):
        """Get audit logs by category."""
        return cls.query.filter_by(category=category).order_by(cls.timestamp.desc()).limit(limit).all()

    @classmethod
    def get_logs_by_user(cls, user_id, limit=100):
        """Get audit logs for a specific user."""
        return cls.query.filter_by(user_id=user_id).order_by(cls.timestamp.desc()).limit(limit).all()

    @classmethod
    def get_logs_by_severity(cls, severity, limit=100):
        """Get audit logs by severity level."""
        return cls.query.filter_by(severity=severity).order_by(cls.timestamp.desc()).limit(limit).all()

    @classmethod
    def get_recent_logs(cls, limit=100):
        """Get recent audit logs."""
        return cls.query.order_by(cls.timestamp.desc()).limit(limit).all()

    @classmethod
    def search_logs(cls, search_term, limit=100):
        """Search audit logs by term."""
        return cls.query.filter(
            db.or_(
                cls.action.ilike(f'%{search_term}%'),
                cls.details.ilike(f'%{search_term}%'),
                cls.endpoint.ilike(f'%{search_term}%')
            )
        ).order_by(cls.timestamp.desc()).limit(limit).all()

    def to_dict(self):
        """Convert audit log to dictionary."""
        return {
            'id': self.id,
            'request_id': self.request_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'category': self.category,
            'action': self.action,
            'severity': self.severity,
            'user_id': self.user_id,
            'user': self.user.username if self.user else None,
            'ip_address': self.ip_address,
            'endpoint': self.endpoint,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'details': json.loads(self.details) if self.details else {}
        }

class NotificationPreference(db.Model):
    """User notification preferences."""
    __tablename__ = 'notification_preferences'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # App notification preferences
    app_notifications_enabled = db.Column(db.Boolean, default=True)
    app_incident_created = db.Column(db.Boolean, default=True)
    app_incident_updated = db.Column(db.Boolean, default=True)
    app_incident_closed = db.Column(db.Boolean, default=True)
    app_unit_assigned = db.Column(db.Boolean, default=True)
    app_unit_status_changed = db.Column(db.Boolean, default=True)
    app_system_notifications = db.Column(db.Boolean, default=True)
    
    # Email notification preferences
    email_notifications_enabled = db.Column(db.Boolean, default=True)
    email_incident_created = db.Column(db.Boolean, default=True)
    email_incident_updated = db.Column(db.Boolean, default=True)
    email_incident_closed = db.Column(db.Boolean, default=True)
    email_unit_assigned = db.Column(db.Boolean, default=True)
    email_unit_status_changed = db.Column(db.Boolean, default=True)
    email_system_notifications = db.Column(db.Boolean, default=True)
    
    # Sound notification preferences
    sound_notifications_enabled = db.Column(db.Boolean, default=True)
    sound_incident_created = db.Column(db.Boolean, default=True)
    sound_incident_updated = db.Column(db.Boolean, default=False)
    sound_incident_closed = db.Column(db.Boolean, default=False)
    sound_unit_assigned = db.Column(db.Boolean, default=True)
    sound_unit_status_changed = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<NotificationPreference {self.id}>'
        
    @staticmethod
    def get_or_create(user_id):
        """Get user preferences or create default ones."""
        prefs = NotificationPreference.query.filter_by(user_id=user_id).first()
        
        if not prefs:
            prefs = NotificationPreference(user_id=user_id)
            db.session.add(prefs)
            db.session.commit()
            
        return prefs

class EmailLog(db.Model):
    """Email log entry."""
    __tablename__ = 'email_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    recipient = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    template_name = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False)  # sent, failed
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    notification_id = db.Column(db.Integer, db.ForeignKey('notifications.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    def __repr__(self):
        return f'<EmailLog {self.id} - {self.status}>'

class BlacklistedToken(db.Model):
    """Model to store blacklisted password reset tokens to prevent reuse."""
    __tablename__ = 'blacklisted_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(128), unique=True, nullable=False)
    blacklisted_on = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    @staticmethod
    def blacklist_token(token):
        """Blacklist a token by storing its hash."""
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        blacklisted_token = BlacklistedToken(token_hash=token_hash)
        db.session.add(blacklisted_token)
        db.session.commit()
        return True
    
    @staticmethod
    def check_blacklist(token):
        """Check if a token is blacklisted."""
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        return BlacklistedToken.query.filter_by(token_hash=token_hash).first() is not None
