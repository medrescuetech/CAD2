"""
User Management API Blueprint

This module provides API endpoints for managing users, roles, and permissions.
"""

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from models import User, Role, Permission, db
from utils.decorators import permission_required, permissions_required, read_endpoint, write_endpoint, api_validation
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
from utils.validation import validate_json_schema, SCHEMAS
from sqlalchemy.exc import IntegrityError
import json
from datetime import datetime, timedelta

# Create blueprint
users_bp = Blueprint('users', __name__, url_prefix='/api/users')

# User Management API Routes
@users_bp.route('', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@read_endpoint(limit="60/minute")
def get_users():
    """Get all users with pagination."""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    
    query = User.query
    
    # Filter by role if specified
    role_id = request.args.get('role_id', None, type=int)
    if role_id:
        query = query.filter(User.roles.any(Role.id == role_id))
    
    # Search by name or username
    search = request.args.get('search', None, type=str)
    if search:
        search_term = f"%{search}%"
        query = query.filter((User.username.ilike(search_term)) | 
                            (User.first_name.ilike(search_term)) | 
                            (User.last_name.ilike(search_term)))
    
    # Execute paginated query
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items
    
    # Format response
    user_list = [{
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'active': user.active,
        'roles': [{'id': role.id, 'name': role.name} for role in user.roles],
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'last_login': user.last_login.isoformat() if user.last_login else None
    } for user in users]
    
    return jsonify({
        'success': True,
        'users': user_list,
        'pagination': {
            'total': pagination.total,
            'pages': pagination.pages,
            'page': page,
            'per_page': per_page,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    })

@users_bp.route('/<int:user_id>', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@read_endpoint(limit="60/minute")
def get_user(user_id):
    """Get a specific user by ID."""
    user = User.query.get_or_404(user_id)
    
    # Format response
    user_data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'active': user.active,
        'roles': [{'id': role.id, 'name': role.name} for role in user.roles],
        'permissions': user.get_permissions(),
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'last_login': user.last_login.isoformat() if user.last_login else None
    }
    
    return jsonify({
        'success': True,
        'user': user_data
    })

@users_bp.route('', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@write_endpoint(limit="30/minute")
@validate_json_schema(SCHEMAS['user'])
def create_user():
    """Create a new user."""
    data = request.get_json()
    
    # Check if username or email already exists
    if User.query.filter_by(username=data['username']).first():
        return jsonify({
            'success': False,
            'message': 'Username already exists'
        }), 409
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({
            'success': False,
            'message': 'Email already exists'
        }), 409
    
    # Create new user
    user = User(
        username=data['username'],
        email=data['email'],
        password=generate_password_hash(data['password']),
        first_name=data.get('first_name', ''),
        last_name=data.get('last_name', ''),
        active=True,
        created_at=datetime.utcnow()
    )
    
    # Add roles if specified
    if 'role_id' in data:
        role = Role.query.get(data['role_id'])
        if role:
            user.roles.append(role)
    
    # Save to database
    try:
        db.session.add(user)
        db.session.commit()
        
        # Log the event
        log_audit_event(
            category=AuditCategory.USER_MANAGEMENT,
            action="User created",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            details={
                'created_user_id': user.id,
                'created_username': user.username,
                'roles': [role.name for role in user.roles]
            }
        )
        
        # Format response
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'active': user.active,
            'roles': [{'id': role.id, 'name': role.name} for role in user.roles],
            'created_at': user.created_at.isoformat() if user.created_at else None
        }
        
        return jsonify({
            'success': True,
            'message': 'User created successfully',
            'user': user_data
        }), 201
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Database error occurred'
        }), 500

@users_bp.route('/<int:user_id>', methods=['PUT'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@write_endpoint(limit="30/minute")
def update_user(user_id):
    """Update an existing user."""
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    # Check if admin is trying to modify their own admin status
    if current_user.id == user_id and 'role_id' in data:
        new_role = Role.query.get(data['role_id'])
        if new_role and not new_role.has_permission(Permission.ADMIN) and user.has_permission(Permission.ADMIN):
            return jsonify({
                'success': False,
                'message': 'Cannot remove your own admin privileges'
            }), 403
    
    # Update user fields
    if 'username' in data and data['username'] != user.username:
        # Check if new username already exists
        if User.query.filter_by(username=data['username']).first():
            return jsonify({
                'success': False,
                'message': 'Username already exists'
            }), 409
        user.username = data['username']
    
    if 'email' in data and data['email'] != user.email:
        # Check if new email already exists
        if User.query.filter_by(email=data['email']).first():
            return jsonify({
                'success': False,
                'message': 'Email already exists'
            }), 409
        user.email = data['email']
    
    # Update other fields
    if 'first_name' in data:
        user.first_name = data['first_name']
    
    if 'last_name' in data:
        user.last_name = data['last_name']
    
    if 'active' in data:
        user.active = bool(data['active'])
    
    if 'password' in data:
        user.password = generate_password_hash(data['password'])
    
    # Update roles if specified
    if 'role_id' in data:
        role = Role.query.get(data['role_id'])
        if role:
            user.roles = [role]  # Replace existing roles
    
    # Save to database
    try:
        db.session.commit()
        
        # Log the event
        log_audit_event(
            category=AuditCategory.USER_MANAGEMENT,
            action="User updated",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            details={
                'updated_user_id': user.id,
                'updated_username': user.username,
                'updated_fields': list(data.keys())
            }
        )
        
        # Format response
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'active': user.active,
            'roles': [{'id': role.id, 'name': role.name} for role in user.roles],
            'updated_at': datetime.utcnow().isoformat()
        }
        
        return jsonify({
            'success': True,
            'message': 'User updated successfully',
            'user': user_data
        })
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Database error occurred'
        }), 500

@users_bp.route('/<int:user_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@write_endpoint(limit="10/minute")
def delete_user(user_id):
    """Delete a user."""
    # Prevent self-deletion
    if current_user.id == user_id:
        return jsonify({
            'success': False,
            'message': 'Cannot delete your own account'
        }), 403
    
    user = User.query.get_or_404(user_id)
    
    # Store user info for audit log
    user_info = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'roles': [role.name for role in user.roles]
    }
    
    # Delete the user
    try:
        db.session.delete(user)
        db.session.commit()
        
        # Log the event
        log_audit_event(
            category=AuditCategory.USER_MANAGEMENT,
            action="User deleted",
            severity=AuditSeverity.WARNING,
            user_id=current_user.id,
            details=user_info
        )
        
        return jsonify({
            'success': True,
            'message': 'User deleted successfully'
        })
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Cannot delete user with associated records'
        }), 409

# Role Management API Routes
@users_bp.route('/roles', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@read_endpoint(limit="60/minute")
def get_roles():
    """Get all roles."""
    roles = Role.query.all()
    
    # Format response
    role_list = [{
        'id': role.id,
        'name': role.name,
        'description': role.description,
        'permissions': role.permissions,
        'default': role.default,
        'users_count': len(role.users)
    } for role in roles]
    
    return jsonify({
        'success': True,
        'roles': role_list
    })

@users_bp.route('/roles/<int:role_id>', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@read_endpoint(limit="60/minute")
def get_role(role_id):
    """Get a specific role by ID."""
    role = Role.query.get_or_404(role_id)
    
    # Format response
    role_data = {
        'id': role.id,
        'name': role.name,
        'description': role.description,
        'permissions': role.permissions,
        'default': role.default,
        'users': [{
            'id': user.id,
            'username': user.username,
            'email': user.email
        } for user in role.users]
    }
    
    return jsonify({
        'success': True,
        'role': role_data
    })

@users_bp.route('/roles', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@write_endpoint(limit="10/minute")
def create_role():
    """Create a new role."""
    data = request.get_json()
    
    # Validate required fields
    if not data.get('name'):
        return jsonify({
            'success': False,
            'message': 'Role name is required'
        }), 400
    
    # Check if role name already exists
    if Role.query.filter_by(name=data['name']).first():
        return jsonify({
            'success': False,
            'message': 'Role name already exists'
        }), 409
    
    # Create new role
    role = Role(
        name=data['name'],
        description=data.get('description', ''),
        permissions=data.get('permissions', 0),
        default=data.get('default', False)
    )
    
    # Save to database
    try:
        db.session.add(role)
        db.session.commit()
        
        # Log the event
        log_audit_event(
            category=AuditCategory.USER_MANAGEMENT,
            action="Role created",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            details={
                'role_id': role.id,
                'role_name': role.name,
                'permissions': role.permissions
            }
        )
        
        # Format response
        role_data = {
            'id': role.id,
            'name': role.name,
            'description': role.description,
            'permissions': role.permissions,
            'default': role.default
        }
        
        return jsonify({
            'success': True,
            'message': 'Role created successfully',
            'role': role_data
        }), 201
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Database error occurred'
        }), 500

@users_bp.route('/roles/<int:role_id>', methods=['PUT'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@write_endpoint(limit="10/minute")
def update_role(role_id):
    """Update an existing role."""
    role = Role.query.get_or_404(role_id)
    data = request.get_json()
    
    # Update role fields
    if 'name' in data and data['name'] != role.name:
        # Check if new name already exists
        if Role.query.filter_by(name=data['name']).first():
            return jsonify({
                'success': False,
                'message': 'Role name already exists'
            }), 409
        role.name = data['name']
    
    if 'description' in data:
        role.description = data['description']
    
    if 'permissions' in data:
        role.permissions = data['permissions']
    
    if 'default' in data:
        role.default = bool(data['default'])
    
    # Save to database
    try:
        db.session.commit()
        
        # Log the event
        log_audit_event(
            category=AuditCategory.USER_MANAGEMENT,
            action="Role updated",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            details={
                'role_id': role.id,
                'role_name': role.name,
                'updated_fields': list(data.keys())
            }
        )
        
        # Format response
        role_data = {
            'id': role.id,
            'name': role.name,
            'description': role.description,
            'permissions': role.permissions,
            'default': role.default
        }
        
        return jsonify({
            'success': True,
            'message': 'Role updated successfully',
            'role': role_data
        })
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Database error occurred'
        }), 500

@users_bp.route('/roles/<int:role_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@write_endpoint(limit="5/minute")
def delete_role(role_id):
    """Delete a role."""
    role = Role.query.get_or_404(role_id)
    
    # Prevent deletion of admin role
    if role.has_permission(Permission.ADMIN):
        return jsonify({
            'success': False,
            'message': 'Cannot delete administrator role'
        }), 403
    
    # Check if role has users
    if role.users:
        return jsonify({
            'success': False,
            'message': 'Cannot delete role with assigned users'
        }), 409
    
    # Store role info for audit log
    role_info = {
        'id': role.id,
        'name': role.name,
        'permissions': role.permissions
    }
    
    # Delete the role
    try:
        db.session.delete(role)
        db.session.commit()
        
        # Log the event
        log_audit_event(
            category=AuditCategory.USER_MANAGEMENT,
            action="Role deleted",
            severity=AuditSeverity.WARNING,
            user_id=current_user.id,
            details=role_info
        )
        
        return jsonify({
            'success': True,
            'message': 'Role deleted successfully'
        })
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Cannot delete role with dependencies'
        }), 409

# User Authentication API Routes
@users_bp.route('/auth/login', methods=['POST'])
@write_endpoint(limit="10/minute")
def login():
    """User login endpoint."""
    data = request.get_json()
    
    # Validate required fields
    if not data.get('username') or not data.get('password'):
        return jsonify({
            'success': False,
            'message': 'Username and password are required'
        }), 400
    
    # Find user by username
    user = User.query.filter_by(username=data['username']).first()
    
    # Check if user exists and password is correct
    if user and check_password_hash(user.password, data['password']):
        # Check if user is active
        if not user.active:
            log_audit_event(
                category=AuditCategory.AUTHENTICATION,
                action="Login attempt - inactive account",
                severity=AuditSeverity.WARNING,
                details={
                    'username': data['username'],
                    'ip': request.remote_addr
                }
            )
            return jsonify({
                'success': False,
                'message': 'Account is inactive'
            }), 403
        
        # Login user
        login_user(user)
        
        # Update last login time
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Log successful login
        log_audit_event(
            category=AuditCategory.AUTHENTICATION,
            action="Login successful",
            severity=AuditSeverity.INFO,
            user_id=user.id,
            details={
                'username': user.username,
                'ip': request.remote_addr
            }
        )
        
        # Format response
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'roles': [{'id': role.id, 'name': role.name} for role in user.roles],
            'permissions': user.get_permissions()
        }
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': user_data
        })
    else:
        # Log failed login
        log_audit_event(
            category=AuditCategory.AUTHENTICATION,
            action="Login failed - invalid credentials",
            severity=AuditSeverity.WARNING,
            details={
                'username': data.get('username'),
                'ip': request.remote_addr
            }
        )
        
        return jsonify({
            'success': False,
            'message': 'Invalid username or password'
        }), 401

@users_bp.route('/auth/logout', methods=['POST'])
@login_required
@write_endpoint()
def logout():
    """User logout endpoint."""
    # Log the logout event
    log_audit_event(
        category=AuditCategory.AUTHENTICATION,
        action="Logout",
        severity=AuditSeverity.INFO,
        user_id=current_user.id,
        details={
            'username': current_user.username,
            'ip': request.remote_addr
        }
    )
    
    # Logout the user
    logout_user()
    
    return jsonify({
        'success': True,
        'message': 'Logout successful'
    })

@users_bp.route('/auth/profile', methods=['GET'])
@login_required
@read_endpoint()
def get_profile():
    """Get current user profile."""
    # Format response
    user_data = {
        'id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'first_name': current_user.first_name,
        'last_name': current_user.last_name,
        'roles': [{'id': role.id, 'name': role.name} for role in current_user.roles],
        'permissions': current_user.get_permissions(),
        'last_login': current_user.last_login.isoformat() if current_user.last_login else None
    }
    
    return jsonify({
        'success': True,
        'user': user_data
    })

@users_bp.route('/auth/profile', methods=['PUT'])
@login_required
@write_endpoint()
def update_profile():
    """Update current user profile."""
    data = request.get_json()
    user = current_user
    
    # Limit fields that can be updated by the user
    allowed_fields = ['first_name', 'last_name', 'email', 'password']
    update_fields = {}
    
    for field in allowed_fields:
        if field in data:
            update_fields[field] = data[field]
    
    # Update email if changed
    if 'email' in update_fields and update_fields['email'] != user.email:
        # Check if new email already exists
        if User.query.filter_by(email=update_fields['email']).first():
            return jsonify({
                'success': False,
                'message': 'Email already exists'
            }), 409
        user.email = update_fields['email']
    
    # Update other fields
    if 'first_name' in update_fields:
        user.first_name = update_fields['first_name']
    
    if 'last_name' in update_fields:
        user.last_name = update_fields['last_name']
    
    # Update password if provided
    if 'password' in update_fields:
        # Verify current password if provided
        if 'current_password' not in data:
            return jsonify({
                'success': False,
                'message': 'Current password is required to change password'
            }), 400
        
        if not check_password_hash(user.password, data['current_password']):
            return jsonify({
                'success': False,
                'message': 'Current password is incorrect'
            }), 403
        
        user.password = generate_password_hash(update_fields['password'])
    
    # Save to database
    try:
        db.session.commit()
        
        # Log the event
        log_audit_event(
            category=AuditCategory.USER_MANAGEMENT,
            action="Profile updated",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            details={
                'updated_fields': list(update_fields.keys())
            }
        )
        
        # Format response
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'updated_at': datetime.utcnow().isoformat()
        }
        
        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'user': user_data
        })
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Database error occurred'
        }), 500

# Permissions API Routes
@users_bp.route('/permissions', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@read_endpoint()
def get_permissions():
    """Get all available permissions."""
    # Format response with all permission flags
    permissions = [
        {'name': name, 'value': value}
        for name, value in vars(Permission).items()
        if not name.startswith('_') and isinstance(value, int)
    ]
    
    return jsonify({
        'success': True,
        'permissions': permissions
    })
